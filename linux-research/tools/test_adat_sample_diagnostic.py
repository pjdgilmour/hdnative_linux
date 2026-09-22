#!/usr/bin/env python3
"""Verify diagnostic reference against actual C generator, and alignment failures."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
import numpy as np
from adat_sample_diagnostic import expected_samples, decode, compare, FRAMES

HEADER = Path(os.environ.get('HDNATIVE_CAPTURE_HEADER', str(Path(__file__).resolve().parent.parent/'kernel/native_capture_ring.h')))

class SampleDiagnosticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = expected_samples(HEADER.read_text())

    def test_reference_matches_actual_c_generator(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p/'native_capture_ring.h').write_bytes(HEADER.read_bytes())
            (p/'test.c').write_text('''#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "native_capture_ring.h"
static unsigned char tx[NC_TX_FRAMES*256];
int main(void) {
 for(unsigned int f=0;f<480000;f++) {
  nc_tx_fill(tx,f,1,1);
  if(fwrite(tx+(f%NC_TX_FRAMES)*256+4,1,6,stdout)!=6) return 1;
 }
 return 0;
}
''')
            subprocess.run(['cc','-O2',str(p/'test.c'),'-o',str(p/'test')],check=True)
            actual = decode(subprocess.run([str(p/'test')],check=True,capture_output=True).stdout)
            np.testing.assert_array_equal(actual,self.reference)

    def test_clean_delay_and_bit_corruption(self):
        actual = np.zeros_like(self.reference)
        actual[16:] = self.reference[:-16]
        clean = compare(actual,self.reference)
        self.assertEqual(clean['best_offsets_frames'],[16])
        for ch in clean['channels']:
            self.assertEqual(ch['exact_nonzero_reference_samples'],ch['nonzero_reference_samples'])
            self.assertEqual(sum(ch['cleared_bits_0_to_23']),0)
            self.assertEqual(sum(ch['added_bits_0_to_23']),0)
        actual[:,0] &= ~(1<<20)
        broken = compare(actual,self.reference)
        self.assertEqual(broken['best_offsets_frames'],[16])
        self.assertGreater(broken['channels'][0]['cleared_bits_0_to_23'][20],0)
        self.assertEqual(sum(broken['channels'][0]['added_bits_0_to_23']),0)

    def test_silence_has_no_alignment(self):
        result = compare(np.zeros_like(self.reference),self.reference)
        self.assertEqual(result['alignment_status'],'unavailable_or_ambiguous')
        self.assertNotIn('channels',result)

    def test_truncated_input_rejected(self):
        with self.assertRaises(ValueError):decode(bytes(FRAMES*6-1))

if __name__=='__main__': unittest.main(verbosity=2)
