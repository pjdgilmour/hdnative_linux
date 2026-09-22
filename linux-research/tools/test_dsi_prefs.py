#!/usr/bin/env python3
import struct,unittest
from inspect_dsi_prefs import inspect,inspect_k016,MAX_BYTES

TEXT = ('syncMode 0 spdifCompatibilityDA30 0 meterOutputNotInput 0 '
        'slaveModeSelect 1 userSyncOutRate 0 sc 3 4 5 4 1 1 0 0 xp '
        '0 9 10 11 12 25 26 27 28 0 0 0 0 1 2 3 4 5 6 7 8 '
        '0 0 0 0 0 0 0 0 1 card 0 0 0 255 0 card 1 0 '
        'card 2 0 0 3 15 1 card 3 0 leg 0 0 ')

def padded(text):return text.encode('ascii').ljust(1024,b'\0')

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
    def test_saved_text_does_not_become_hardware_state(self):
        r=inspect(fixture([(0x4b30313600002200,padded(TEXT))]))
        entry=r['saved_k016_text_configurations'][0]
        self.assertTrue(entry['decoded'])
        c=entry['configuration']
        self.assertEqual(c['digital_saved_fields']['source_enum'],3)
        self.assertEqual(c['digital_saved_fields']['src_pair_mask'],15)
        self.assertEqual(c['routes'][5:9],[25,26,27,28])
        self.assertEqual(c['card_fields'][0],[0,0,255,0])
        self.assertFalse(c['verified_current_hardware_state'])
        self.assertFalse(c['verified_adat_audio'])
        self.assertEqual(r['candidates_108_bytes'],[])
    def test_other_key_is_not_promoted_by_text_alone(self):
        self.assertEqual(inspect(fixture([(1,padded(TEXT))]))['saved_k016_text_configurations'],[])
    def test_text_malformed_layout_rejected(self):
        for s in (TEXT.replace('sc 3 4 5 4','sc 3 4 4 5'),
                  TEXT.replace('card 2','card 1'), TEXT.replace('25 26','30 26'),
                  TEXT.replace('3 15 1 card','3 16 1 card'),
                  TEXT.replace('0 xp','xp'), TEXT+'unknown 0',
                  TEXT.replace('syncMode 0','syncMode 4294967296'),
                  TEXT.replace('syncMode 0','syncMode -1'),
                  TEXT.replace('card 2 0 0 3','card 2 0 0 9')):
            with self.subTest(text=s),self.assertRaises(ValueError):inspect_k016(padded(s))
    def test_each_text_token_truncation_rejected(self):
        words=TEXT.split()
        for n in range(len(words)):
            with self.subTest(n=n),self.assertRaises(ValueError):inspect_k016(padded(' '.join(words[:n])))
    def test_text_binary_boundaries(self):
        for d in (padded(TEXT)[:-1],b'x'*1024,padded(TEXT)[:-1]+b'x',b'\xff'+padded(TEXT)[1:]):
            with self.assertRaises(ValueError):inspect_k016(d)
    def test_unsupported_text_record_reported_without_losing_inventory(self):
        r=inspect(fixture([(0x4b30313600002200,b'x'),(1,b'abc')]))
        self.assertEqual(r['record_count'],2)
        self.assertFalse(r['saved_k016_text_configurations'][0]['decoded'])
if __name__=='__main__':unittest.main(verbosity=2)
