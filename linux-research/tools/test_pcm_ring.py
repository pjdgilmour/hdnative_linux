#!/usr/bin/env python3
"""Exercise the driver's actual C ring helper. No PCI or sound-device access."""
import ctypes as C
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
class Ring(C.Structure):
    _fields_ = [('queued', C.c_ulonglong), ('consumed', C.c_ulonglong),
                ('appl', C.c_ulong), ('hw', C.c_uint)]

class RingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='native-ring-')
        p = Path(cls.tmp.name)
        (p/'ring.c').write_text('''
#include <errno.h>
#include <string.h>
#include "native_pcm_ring.h"
int push(struct native_pcm_ring *r, unsigned char *tx, unsigned char *pcm,
         unsigned long appl, unsigned long boundary) {
    return native_ring_push(r, tx, pcm, appl, boundary);
}
int advance(struct native_pcm_ring *r, unsigned char *tx, unsigned int hw, int drain) {
    return native_ring_advance(r, tx, hw, drain);
}
''')
        subprocess.run(['gcc', '-shared', '-fPIC', '-std=c11', '-O2', '-g',
                        '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
                        '-fno-sanitize-recover=all', '-I'+str(ROOT/'kernel'),
                        str(p/'ring.c'), '-o', str(p/'ring.so')], check=True)
        cls.lib = C.CDLL(str(p/'ring.so'))
        cls.lib.push.argtypes = [C.POINTER(Ring), C.c_void_p, C.c_void_p, C.c_ulong, C.c_ulong]
        cls.lib.advance.argtypes = [C.POINTER(Ring), C.c_void_p, C.c_uint, C.c_int]
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
    def setUp(self):
        self.r = Ring()
        self.tx = (C.c_ubyte * (8192*256))()
        self.pcm = (C.c_ubyte * (4096*6))()
    def push(self, ptr, boundary=16384):
        return self.lib.push(C.byref(self.r), self.tx, self.pcm, ptr, boundary)
    def advance(self, count, drain=0):
        return self.lib.advance(C.byref(self.r), self.tx, (self.r.hw+count)%8192, drain)
    def test_packed_signed_vectors_and_zero_padding(self):
        samples = bytes.fromhex('ffff7f000080 010000ffffff 000000000000')
        self.pcm[:len(samples)] = samples
        self.assertEqual(self.push(3), 3)
        for i in range(3):
            self.assertEqual(bytes(self.tx[i*256:(i+1)*256]),
                             bytes(4)+samples[i*6:(i+1)*6]+bytes(246))
        self.assertEqual(self.advance(3), 3)
        self.assertEqual(bytes(self.tx), bytes(len(self.tx)))
    def test_overfill_and_rewind_are_atomic_failures(self):
        self.assertEqual(self.push(4096), 4096)
        old = bytes(self.r), bytes(self.tx)
        self.assertEqual(self.push(4097), -32)
        self.assertEqual(self.push(4095), -32)
        self.assertEqual((bytes(self.r), bytes(self.tx)), old)
    def test_underrun_and_eof(self):
        self.assertEqual(self.push(77), 77)
        old = bytes(self.r)
        self.assertEqual(self.advance(80), -32)
        self.assertEqual(bytes(self.r), old)
        self.assertEqual(self.advance(80, drain=1), 77)
        self.assertEqual(self.r.consumed, 77)
        self.assertEqual(self.r.hw, 80)
    def test_invalid_boundary_and_hw(self):
        for ptr, boundary in [(0,0), (0,100), (16384,16384)]:
            self.assertEqual(self.push(ptr,boundary), -22)
        self.assertEqual(self.lib.advance(C.byref(self.r), self.tx, 8192, 0), -22)
    def test_large_alsa_boundary_wrap(self):
        boundary = (1 << 62)
        self.r.appl = boundary-7
        self.assertEqual(self.push(5, boundary), 12)
        self.assertEqual(self.r.appl, 5)
    def test_many_wraps_no_repeats_missing_frames_or_channel_swaps(self):
        rng = random.Random(0xD400)
        submitted = consumed = 0
        def frame(n):
            return (n & 0xffffff).to_bytes(3,'little') + ((~n)&0xffffff).to_bytes(3,'little')
        for _ in range(3000):
            n = rng.randrange(1, min(4096-(submitted-consumed), 512)+1)
            for i in range(n):
                off = ((submitted+i)%4096)*6
                self.pcm[off:off+6] = frame(submitted+i)
            submitted += n
            self.assertEqual(self.push(submitted%16384), n)
            n = rng.randrange(1, submitted-consumed+1)
            # Verify all hardware frames about to be consumed, not just endpoints.
            for i in range(n):
                off = ((consumed+i)%8192)*256
                self.assertEqual(bytes(self.tx[off:off+256]), bytes(4)+frame(consumed+i)+bytes(246))
            self.assertEqual(self.advance(n), n)
            consumed += n
            self.assertEqual((self.r.queued,self.r.consumed), (submitted, consumed))
        self.assertGreater(consumed, 700000)
        self.assertGreater(consumed//8192, 80)
    def test_empty_poll_and_short_write(self):
        self.assertEqual(self.push(0),0)
        self.assertEqual(self.advance(0),0)
        self.assertEqual(self.push(1),1)
        self.assertEqual(self.advance(1),1)
        self.assertEqual(self.push(2),1)
        self.assertEqual(self.advance(1),1)

if __name__ == '__main__':
    unittest.main(verbosity=2)
