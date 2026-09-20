#!/usr/bin/env python3
"""Generate/verify 8 s of stereo S24_3LE, peak -40 dBFS; no device access."""
import argparse
import math
from pathlib import Path
RATE = 48000
FRAMES = RATE * 8
PEAK = 83886
SEGMENTS = ((24000,120000,(440,0)), (144000,240000,(0,660)),
            (264000,360000,(440,660)))

def generate():
    data = bytearray(FRAMES*6)
    for start, end, freqs in SEGMENTS:
        for frame in range(start,end):
            ramp = min(frame-start, end-1-frame, 480)/480
            for channel,freq in enumerate(freqs):
                value = round(PEAK*ramp*math.sin(2*math.pi*freq*(frame-start)/RATE)) if freq else 0
                off = frame*6+channel*3
                data[off:off+3] = value.to_bytes(3,'little',signed=True)
    return data

def verify(data):
    assert len(data) == FRAMES*6
    peaks = [0,0]
    energy = [[0,0] for _ in SEGMENTS]
    for frame in range(FRAMES):
        active = next((i for i,(start,end,_) in enumerate(SEGMENTS) if start <= frame < end), None)
        for channel in range(2):
            off = frame*6+channel*3
            v = int.from_bytes(data[off:off+3],'little',signed=True)
            assert abs(v) <= PEAK
            peaks[channel] = max(peaks[channel],abs(v))
            if active is None or not SEGMENTS[active][2][channel]:
                assert v == 0
            if active is not None:
                energy[active][channel] += v*v
    assert peaks == [PEAK,PEAK]
    assert energy[0][0] and not energy[0][1]
    assert energy[1][1] and not energy[1][0]
    assert energy[2][0] and energy[2][1]
    for start,end,_ in SEGMENTS:
        assert data[start*6:(start+1)*6] == bytes(6)
        assert data[(end-1)*6:end*6] == bytes(6)
    # Independent fixed steady-state vectors at selected positive peaks.
    for frame,ch,freq,start in [(24000+600,0,440,24000),(144000+600,1,660,144000)]:
        v = int.from_bytes(data[frame*6+ch*3:frame*6+ch*3+3],'little',signed=True)
        assert abs(v-round(PEAK*math.sin(2*math.pi*freq*(frame-start)/RATE))) <= 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeat', type=int, choices=range(1,41), default=1,
                        metavar='1..40', help='Repeat the verified 8-second sequence in one file')
    args = parser.parse_args()
    data = generate()
    verify(data)
    with args.output.open('wb') as out:
        for _ in range(args.repeat):
            out.write(data)
    assert args.output.stat().st_size == FRAMES * args.repeat * 6
    print(f'TONE_VERIFIED=yes frames={FRAMES * args.repeat} format=S24_3LE rate=48000 channels=2 peak=-40dBFS repeat={args.repeat}')
