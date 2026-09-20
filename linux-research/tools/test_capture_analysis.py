#!/usr/bin/env python3
"""Known stereo fixtures: silence/DC cannot pass the loopback pattern check."""
import math,unittest
from analyze_capture import analyze,RATE
class AnalysisTests(unittest.TestCase):
    def test_silence(self):
        r=analyze(bytes(RATE*10*6),True)
        self.assertFalse(r['loopback_pattern_matched'])
        self.assertFalse(r['nonzero_both_channels'])
    def test_dc(self):
        r=analyze((10000).to_bytes(3,'little',signed=True)*RATE*10*2,True)
        self.assertTrue(r['nonzero_both_channels'])
        self.assertFalse(r['loopback_pattern_matched'])
    def test_truncated(self):
        with self.assertRaises(ValueError): analyze(bytes(42))
    def test_known_pattern_and_swapped_channels(self):
        data=bytearray(RATE*10*6)
        for start,end,channels in [(RATE,3*RATE,[0]),(4*RATE,6*RATE,[1]),(7*RATE,9*RATE,[0,1])]:
            for frame in range(start,end):
                for ch in channels:
                    v=round(70000*math.sin(2*math.pi*(750 if ch==0 else 1500)*frame/RATE))
                    at=frame*6+ch*3;data[at:at+3]=v.to_bytes(3,'little',signed=True)
        self.assertTrue(analyze(data,True)['loopback_pattern_matched'])
        for i in range(0,len(data),6):data[i:i+6]=data[i+3:i+6]+data[i:i+3]
        self.assertFalse(analyze(data,True)['loopback_pattern_matched'])
if __name__=='__main__':unittest.main(verbosity=2)
