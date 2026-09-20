#!/usr/bin/env python3
"""Run one ALSA playback, monitor progress and retain a JSON result.

The supervisor never opens PCI resources. The kernel driver remains responsible
for stopping DMA and restoring the peripheral when the player closes.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

KEYS = ('starts', 'stops', 'xruns', 'last_error', 'total_frames', 'ring_wraps',
        'rx_discarded', 'max_poll_us', 'mute_restored', 'route_restored')

def read_stats(directory):
    result = {}
    for key in KEYS:
        value = (directory/key).read_text().strip()
        result[key] = value if key.endswith('_restored') else int(value)
    return result

def supervise(command, directory, output, expected_frames, timeout_seconds,
              interval=10.0, tick=0.25, stall_seconds=3.0):
    report = {'command': command, 'expected_frames': expected_frames,
              'timeout_seconds': timeout_seconds, 'samples': [], 'success': False}
    child = None
    interrupted = 0
    handlers = {}
    started = time.monotonic()
    def on_signal(signum, frame):
        nonlocal interrupted
        interrupted = signum
    def sample(stats, elapsed):
        report['samples'].append({'elapsed_seconds': round(elapsed,3), **stats})
        print(f"PROGRESS seconds={elapsed:.1f} frames={stats['total_frames']-before['total_frames']} "
              f"wraps={stats['ring_wraps']-before['ring_wraps']} "
              f"xruns={stats['xruns']} max_poll_us={stats['max_poll_us']}", flush=True)
    try:
        before = read_stats(directory)
        report['before'] = before
        if before['last_error'] or before['xruns']:
            raise RuntimeError('driver já informa erro antes da reprodução')
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            handlers[signum] = signal.signal(signum, on_signal)
        child = subprocess.Popen(command, start_new_session=True)
        started = progress_time = time.monotonic()
        next_sample = interval
        previous_frames = before['total_frames']
        while True:
            code = child.poll()
            now = time.monotonic()
            elapsed = now-started
            current = read_stats(directory)
            if interrupted:
                raise RuntimeError(f'interrompido por sinal {interrupted}')
            if current['last_error'] or current['xruns']:
                raise RuntimeError(f"driver error={current['last_error']} xruns={current['xruns']}")
            if current['total_frames'] < previous_frames:
                raise RuntimeError('contador de quadros retrocedeu')
            if current['total_frames'] != previous_frames:
                progress_time = now
                previous_frames = current['total_frames']
            if elapsed >= next_sample:
                sample(current, elapsed)
                next_sample = elapsed + interval
            if code is not None:
                report['player_returncode'] = code
                if code:
                    raise RuntimeError(f'aplay terminou com código {code}')
                break
            if elapsed >= timeout_seconds:
                raise RuntimeError('tempo máximo excedido')
            if now-progress_time >= stall_seconds:
                raise RuntimeError('sem avanço de quadros por 3 segundos')
            time.sleep(tick)
        final = read_stats(directory)
        sample(final, elapsed)
        frames = final['total_frames']-before['total_frames']
        report['transferred_frames'] = frames
        # aplay added one 1024-frame period in the first verified run.
        # Permit only that bounded tail; do not accept missing source frames.
        if not expected_frames <= frames <= expected_frames+1024:
            raise RuntimeError(f'contagem inesperada: {frames}; arquivo={expected_frames}')
        if final['starts']-before['starts'] != 1 or final['stops']-before['stops'] != 1:
            raise RuntimeError('partida/parada não corresponde a uma sessão')
        if final['mute_restored'] != 'Y' or final['route_restored'] != 'Y':
            raise RuntimeError('restauração do mute/rota não confirmada')
        if elapsed < expected_frames/48000 * 0.95:
            raise RuntimeError('reprodução terminou muito antes do tempo nominal')
        report['success'] = True
    except Exception as error:
        report['error'] = str(error)
        print(f'PLAYBACK_FAILED={error}', flush=True)
    finally:
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    report['player_still_running'] = True
                    report['success'] = False
            except ProcessLookupError:
                child.wait(timeout=3)
        report['elapsed_seconds'] = round(time.monotonic()-started,3)
        if child is not None:
            report['player_returncode'] = child.poll()
        report['interrupted_signal'] = interrupted
        try:
            report['after'] = read_stats(directory)
        except (OSError, ValueError) as error:
            report['final_stats_error'] = str(error)
            report['success'] = False
        output.write_text(json.dumps(report, indent=2)+'\n')
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
    print(f"PLAYBACK_VERIFIED={'yes' if report['success'] else 'no'} report={output}", flush=True)
    return 0 if report['success'] else 1

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device', required=True)
    p.add_argument('--audio', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--timeout', type=float, required=True)
    args = p.parse_args()
    size = args.audio.stat().st_size
    if not size or size % 6 or size > 48000*320*6:
        p.error('arquivo PCM fora dos limites do experimento')
    if not 1 <= args.timeout <= 350:
        p.error('timeout deve estar entre 1 e 350 segundos')
    command = ['/usr/bin/aplay', '-D', args.device, '-t', 'raw', '-f', 'S24_3LE',
               '-c','2','-r','48000','--period-size=1024','--buffer-size=4096',
               '--fatal-errors',str(args.audio)]
    return supervise(command, Path('/sys/module/avid_native_alsa/parameters'),
                     args.report, size//6, args.timeout)

if __name__ == '__main__':
    raise SystemExit(main())
