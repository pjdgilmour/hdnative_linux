#!/usr/bin/env python3
"""Offline comparison with the bounded native_capture_ring TX pattern.

Requires numpy. Does not repair audio, write hardware, or change acceptance.
The alignment is a pattern fit, not an end-to-end latency measurement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import wave
import numpy as np

RATE = 48000
FRAMES = 480000

def expected_samples(header):
    match = re.search(r'sine\[64\] = \{([^}]+)\}', header)
    if not match:
        raise ValueError('Expected native_capture_ring sine table')
    sine = np.array([int(v) for v in match[1].split(',')], dtype=np.int64)
    if len(sine) != 64 or max(abs(sine)) != 83886:
        raise ValueError('Unexpected test tone table')
    result = np.zeros((FRAMES, 2), dtype=np.int32)
    for channel in range(2):
        for begin in (192000 if channel else 48000, 336000):
            end = begin + 96000
            t = np.arange(end-begin)
            ramp = np.minimum(np.minimum(t, end-begin-1-t), 480)
            product = sine[t*(channel+1) % 64]*ramp
            # C signed integer division truncates toward zero.
            result[begin:end, channel] = (np.sign(product)*(abs(product)//480)) & 0xffffff
    return result

def decode(raw):
    if len(raw) != FRAMES*6:
        raise ValueError('Expected exactly 10 s of stereo 48 kHz S24_3LE')
    b = np.frombuffer(raw, dtype=np.uint8).reshape(FRAMES, 2, 3).astype(np.int32)
    return b[:,:,0] | (b[:,:,1]<<8) | (b[:,:,2]<<16)

def compare(actual, expected):
    # Fit the three onset ramps, not the long silent regions or only a
    # steady sinusoid (which would give ambiguous whole-period offsets).
    onset = np.concatenate([np.arange(begin, begin+512) for begin in (48000,192000,336000)])
    target = expected[onset]
    active = target != 0
    scores = [int(np.count_nonzero((actual[onset+d] == target) & active)) for d in range(129)]
    best = max(scores)
    candidates = [i for i,s in enumerate(scores) if s == best]
    result = {'scope':'offline sample comparison only; never a hardware pass',
              'search_offsets_frames':[0,128], 'alignment_score':best,
              'alignment_scored_nonzero_samples':int(active.sum()),
              'best_offsets_frames':candidates,
              'alignment_is_latency_measurement':False}
    if best == 0 or len(candidates) != 1:
        result['alignment_status'] = 'unavailable_or_ambiguous'
        return result
    delay = candidates[0]
    result['alignment_status'] = 'unique_best_pattern_fit'
    a = actual[delay:]
    e = expected[:len(a)]
    result['compared_frames'] = len(a)
    channels = []
    for ch in range(2):
        av,ev = a[:,ch],e[:,ch]
        changed = av ^ ev
        cleared = ev & (~av & 0xffffff)
        added = av & (~ev & 0xffffff)
        active_ch = ev != 0
        examples = []
        for index in np.flatnonzero((changed != 0) & active_ch)[:8]:
            examples.append({'reference_frame':int(index), 'captured_frame':int(index+delay),
                             'expected_hex':f'{ev[index]:06x}', 'captured_hex':f'{av[index]:06x}'})
        windows = []
        for begin,end in ((57600,134400),(201600,278400),(345600,422400)):
            y = ((av[begin:end]^0x800000)-0x800000).astype(np.float64)
            spectrum = abs(np.fft.rfft(y-y.mean()))
            peak = int(np.argmax(spectrum))
            windows.append({'reference_seconds':[begin/RATE,end/RATE],
                            'nonzero_samples':int(np.count_nonzero(y)),
                            'dominant_ac_hz':peak*RATE/len(y) if spectrum[peak] else None,
                            'mean_pcm':float(y.mean()),
                            'exact_samples':int(np.count_nonzero(changed[begin:end] == 0)),
                            'samples':end-begin})
        channels.append({'channel':ch+1,
            'nonzero_reference_samples':int(active_ch.sum()),
            'exact_nonzero_reference_samples':int(np.count_nonzero(active_ch & (changed == 0))),
            'unexpected_nonzero_during_reference_silence':int(np.count_nonzero(~active_ch & (av != 0))),
            'cleared_bits_0_to_23':[int(np.count_nonzero(cleared & (1<<bit))) for bit in range(24)],
            'added_bits_0_to_23':[int(np.count_nonzero(added & (1<<bit))) for bit in range(24)],
            'mismatch_examples':examples,'windows':windows})
    result['channels'] = channels
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path, nargs='?')
    parser.add_argument('--write-reference', type=Path, help='Create a new stereo 24-bit WAV instead of analyzing a capture')
    parser.add_argument('--header', type=Path, default=Path(__file__).resolve().parent.parent/'kernel/native_capture_ring.h')
    args = parser.parse_args()
    if (args.raw is None) == (args.write_reference is None):
        parser.error('Supply one raw input OR --write-reference WAV')
    header = args.header.read_bytes()
    if args.write_reference is not None:
        samples = expected_samples(header.decode())
        packed = np.stack([samples & 255, (samples>>8)&255, (samples>>16)&255], axis=2).astype(np.uint8).tobytes()
        with args.write_reference.open('xb') as out:
            with wave.open(out, 'wb') as wav:
                wav.setnchannels(2)
                wav.setsampwidth(3)
                wav.setframerate(RATE)
                wav.writeframes(packed)
        print(json.dumps({'reference_wav':str(args.write_reference), 'frames':FRAMES,
                          'rate':RATE, 'sample_peak':83886, 'peak_dbfs_approx':-40,
                          'sha256':hashlib.sha256(args.write_reference.read_bytes()).hexdigest()}, indent=2))
        return
    raw = args.raw.read_bytes()
    result = compare(decode(raw), expected_samples(header.decode()))
    result.update(raw_sha256=hashlib.sha256(raw).hexdigest(), reference_header_sha256=hashlib.sha256(header).hexdigest(),
                  reference='native_capture_ring pattern: 10s, stereo 750/1500Hz, -40dBFS, 10ms ramps')
    print(json.dumps(result, indent=2, allow_nan=False))

if __name__ == '__main__':
    main()
