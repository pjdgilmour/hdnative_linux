#!/usr/bin/env python3
"""Test process supervision with simulated sysfs and a disposable child; no PCI."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from supervise_alsa import KEYS, supervise

CHILD = r'''
import os, signal, sys, time
from pathlib import Path
p=Path(sys.argv[1]); mode=sys.argv[2]
def put(key,value):
    t=p/(key+'.tmp'); t.write_text(str(value)); t.replace(p/key)
time.sleep(0.06)
if mode=='exit': sys.exit(7)
if mode=='timeout' or mode=='stall': time.sleep(10)
if mode=='signal':
    os.kill(os.getppid(),signal.SIGTERM)
    time.sleep(10)
if mode=='driver_error':
    put('last_error',-110)
    time.sleep(10)
put('starts',1)
put('total_frames', 511 if mode=='short' else 1536)
put('stops',1)
put('mute_restored','N' if mode=='mute' else 'Y')
put('route_restored','Y')
'''
class SupervisorTest(unittest.TestCase):
    def run_case(self, mode, expect_success):
        with tempfile.TemporaryDirectory(prefix='alsa-supervision-') as d:
            root=Path(d); params=root/'params'; params.mkdir()
            for key in KEYS:
                (params/key).write_text('N' if key.endswith('_restored') else '0')
            (root/'child.py').write_text(CHILD)
            report=root/'result.json'
            with contextlib.redirect_stdout(io.StringIO()):
                code=supervise([sys.executable,str(root/'child.py'),str(params),mode],
                               params,report,512,0.3 if mode=='timeout' else 2,
                               interval=.1,tick=.01,
                               stall_seconds=.15 if mode=='stall' else 3)
            result=json.loads(report.read_text())
            self.assertEqual(result['success'], expect_success,result)
            self.assertEqual(code,0 if expect_success else 1)
            self.assertIsNotNone(result['player_returncode'],result)
            self.assertFalse(result.get('player_still_running',False))
            return result
    def test_success_with_aplay_tail(self):
        r=self.run_case('success',True)
        self.assertEqual(r['transferred_frames'],1536)
    def test_driver_error_terminates_child(self):
        r=self.run_case('driver_error',False)
        self.assertIn('driver error=-110',r['error'])
        self.assertEqual(r['player_returncode'],-15)
    def test_timeout_terminates_child(self):
        self.assertIn('tempo máximo',self.run_case('timeout',False)['error'])
    def test_stall_terminates_child(self):
        self.assertIn('sem avanço',self.run_case('stall',False)['error'])
    def test_sigterm_terminates_player_in_separate_session(self):
        r=self.run_case('signal',False)
        self.assertEqual(r['interrupted_signal'],15)
        self.assertEqual(r['player_returncode'],-15)
    def test_nonzero_player_exit(self):
        self.assertEqual(self.run_case('exit',False)['player_returncode'],7)
    def test_missing_source_frames(self):
        self.assertIn('contagem inesperada',self.run_case('short',False)['error'])
    def test_failed_restoration(self):
        self.assertIn('restauração',self.run_case('mute',False)['error'])

if __name__=='__main__':
    unittest.main(verbosity=2)
