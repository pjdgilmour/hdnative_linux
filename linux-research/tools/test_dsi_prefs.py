#!/usr/bin/env python3
import struct,unittest
from inspect_dsi_prefs import inspect,MAX_BYTES

def fixture(entries):
    payload=struct.pack('<I',len(entries))+b''.join(struct.pack('<IQ',len(v),k)+v for k,v in entries)
    return b'DSETUP'+struct.pack('<HI',1,len(payload))+payload
class PrefsTests(unittest.TestCase):
    def test_candidates_remain_unverified(self):
        payload=bytearray(108);payload[31:34]=b'\x04\x82\x00'
        r=inspect(fixture([(1,b'abc'),(2,payload)]))
        self.assertEqual(r['record_count'],2)
        c=r['candidates_108_bytes'][0]
        self.assertEqual(c['candidate_digital_bytes'],'04 82 00')
        self.assertFalse(c['verified_192_record']);self.assertFalse(c['verified_current_hardware_state'])
    def test_empty_valid(self):self.assertEqual(inspect(fixture([]))['record_count'],0)
    def test_truncation(self):
        d=fixture([(1,b'x'*108)])
        for n in range(len(d)):
            with self.assertRaises(ValueError):inspect(d[:n])
    def test_bad_magic_and_limits(self):
        for d in [b'X'*16,b'DSETUP'+b'\0'*10,b'DSETUP'+b'\0'*MAX_BYTES]:
            with self.assertRaises(ValueError):inspect(d)
    def test_forged_record_size_and_count(self):
        d=bytearray(fixture([(1,b'abc')]))
        struct.pack_into('<I',d,16,0xffffffff)
        with self.assertRaises(ValueError):inspect(d)
        d=bytearray(fixture([]));struct.pack_into('<I',d,12,0xffffffff)
        with self.assertRaises(ValueError):inspect(d)
    def test_duplicate_keys(self):
        with self.assertRaises(ValueError):inspect(fixture([(1,b'a'),(1,b'b')]))
    def test_trailing_bytes_visible(self):self.assertEqual(inspect(fixture([])+b'xx')['trailing_file_bytes'],2)
if __name__=='__main__':unittest.main(verbosity=2)
