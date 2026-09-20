#!/usr/bin/env python3
"""Exercise the real desktop manager with a disposable fake host; no root/PCI."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import manage_duplex as m

ORIGINAL_ROOT=m.ROOT
class DesktopManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='avid-desktop-test-')
        root=Path(self.temp.name)
        self.patches=[]
        for key,value in {'ROOT':root,'PCI':root/'pci','PARAMS':root/'params',
            'RULE_SOURCE':root/'desktop/rule.conf','RULE_TARGET':root/'etc/rule.conf',
            'STATE_DIR':root/'state','STATE_FILE':root/'state/state.json'}.items():
            p=patch.object(m,key,value);p.start();self.patches.append(p)
        for d in ('pci','kernel','reports','desktop','etc'): (root/d).mkdir()
        self.original=bytes.fromhex('000000000001')+bytes(58)
        (m.PCI/'config').write_bytes(self.original)
        m.RULE_SOURCE.write_bytes((ORIGINAL_ROOT/'desktop/91-avid-native-duplex.conf').read_bytes())
        self.ko=root/'kernel/avid_native_duplex.ko';self.ko.write_bytes(b'fake module')
        (root/'reports/duplex-build.json').write_text(json.dumps({'load_files_sha256':{
            'kernel/avid_native_duplex.ko':hashlib.sha256(self.ko.read_bytes()).hexdigest()}}))
        self.wp=True;self.source_default='yamaha_input';self.default='yamaha';self.fail_insmod=False;self.fail_rmmod=False
        self.calls=[]
        for p in (patch.object(m,'run',self.fake_run),patch.object(m,'user_command',self.user),
                  patch.dict(os.environ,{'SUDO_UID':'1000'})):
            p.start();self.patches.append(p)
        self.out=io.StringIO()
        for c in (contextlib.redirect_stdout(self.out),contextlib.redirect_stderr(self.out)):
            c.__enter__();self.patches.append(c)
    def tearDown(self):
        for p in reversed(self.patches):
            if hasattr(p,'stop'):p.stop()
            else:p.__exit__(None,None,None)
        self.temp.cleanup()
    def result(self,args,code=0,out='',err='',check=True):
        if code and check:raise RuntimeError(err or 'simulated failure')
        return subprocess.CompletedProcess(args,code,out,err)
    def fake_run(self,args,check=True,**kwargs):
        args=list(map(str,args));self.calls.append(args)
        if args[0].endswith('/modinfo'):
            return self.result(args,out=os.uname().release+' SMP')
        if args[0].endswith('/insmod'):
            if self.fail_insmod:raise RuntimeError('injected probe failure')
            m.PARAMS.mkdir();(m.PCI/'driver').write_text(m.MODULE)
            (m.PCI/'config').write_bytes(bytes(64))
            for k in m.KEYS:(m.PARAMS/k).write_text('Y' if k in ('bound','mute_restored','route_restored') else '0')
        if args[0].endswith('/rmmod'):
            if self.fail_rmmod:return self.result(args,1,err='busy',check=check)
            shutil.rmtree(m.PARAMS);(m.PCI/'driver').unlink()
            (m.PCI/'config').write_bytes(self.original)
        return self.result(args)
    def user(self,uid,args,check=True,**kwargs):
        self.calls.append(list(args))
        if args[:2]==['systemctl','--user']:
            action=args[2]
            if action=='is-active':return self.result(args,0 if self.wp else 3,check=check)
            self.wp=action!='stop'
        if args==['pactl','get-default-source']:return self.result(args,out=self.source_default)
        if args[:2]==['pactl','set-default-source']:self.source_default=args[2]
        if args==['pactl','--format=json','list','sources']:
            data=[{'name':'yamaha_input'}]
            if self.wp and m.PARAMS.exists():data.append({'name':m.SOURCE})
            return self.result(args,out=json.dumps(data))
        if args==['pactl','get-default-sink']:return self.result(args,out=self.default)
        if args[:2]==['pactl','set-default-sink']:self.default=args[2]
        if args==['pactl','--format=json','list','sinks']:
            data=[{'name':'yamaha'}]
            if self.wp and m.PARAMS.exists():data.append({'name':m.SINK})
            return self.result(args,out=json.dumps(data))
        return self.result(args)
    def test_start_and_stop_preserve_default_and_restore_pci(self):
        m.start()
        self.assertTrue(m.PARAMS.exists());self.assertTrue(m.RULE_TARGET.exists())
        self.assertEqual(self.default,'yamaha')
        self.assertIn(['pactl','set-sink-volume',m.SINK,'-40dB'],self.calls)
        log=Path(m.read_state()['log_directory'])
        self.default=m.SINK
        self.assertEqual(self.source_default,"yamaha_input")
        self.assertIn(["pactl","set-source-volume",m.SOURCE,"100%"],self.calls)
        self.source_default=m.SOURCE
        m.stop()
        self.assertEqual(self.source_default,"yamaha_input")
        self.assertEqual(self.default,'yamaha');self.assertTrue(self.wp)
        self.assertFalse(m.PARAMS.exists());self.assertFalse(m.RULE_TARGET.exists())
        self.assertFalse(m.STATE_FILE.exists())
        self.assertEqual((m.PCI/'config').read_bytes(),self.original)
        self.assertTrue(json.loads((log/'session.json').read_text())['pci_restored'])
        self.assertIn('bound',json.loads((log/'module-stats.json').read_text()))
    def test_probe_failure_rolls_back_rule_and_service(self):
        self.fail_insmod=True
        with self.assertRaisesRegex(RuntimeError,'probe'):m.start()
        self.assertFalse(m.RULE_TARGET.exists());self.assertFalse(m.STATE_FILE.exists())
        self.assertTrue(self.wp)
    def test_busy_module_retains_recoverable_state_and_restarts_wp(self):
        m.start();self.fail_rmmod=True
        with self.assertRaisesRegex(RuntimeError,'busy'):m.stop()
        self.assertTrue(m.STATE_FILE.exists());self.assertTrue(m.PARAMS.exists())
        self.assertTrue(m.RULE_TARGET.exists());self.assertTrue(self.wp)
    def test_foreign_rule_is_never_overwritten(self):
        m.RULE_TARGET.write_text('user configuration')
        with self.assertRaisesRegex(RuntimeError,'configuração diferente'):m.start()
        self.assertEqual(m.RULE_TARGET.read_text(),'user configuration')
        self.assertFalse(m.STATE_FILE.exists())
    def test_altered_module_is_rejected_before_mutation(self):
        self.ko.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'Artefato mudou'):m.start()
        self.assertFalse(m.RULE_TARGET.exists());self.assertFalse(m.STATE_FILE.exists())
    def test_preexisting_matching_rule_is_preserved(self):
        m.RULE_TARGET.write_bytes(m.RULE_SOURCE.read_bytes())
        m.start();m.stop()
        self.assertTrue(m.RULE_TARGET.exists())
    def test_diagnostic_failure_does_not_prevent_unload(self):
        m.start()
        with patch.object(m,'diagnostics',side_effect=OSError('disk full')):m.stop()
        self.assertFalse(m.PARAMS.exists());self.assertTrue(self.wp)
    def test_peripheral_restore_failure_is_reported_after_unload(self):
        m.start()
        (m.PARAMS/'starts').write_text('1')
        (m.PARAMS/'mute_restored').write_text('N')
        with self.assertRaisesRegex(RuntimeError,'mute/rota'):m.stop()
        self.assertFalse(m.PARAMS.exists());self.assertTrue(self.wp)
        self.assertTrue(m.read_state()['cleanup_errors'])
    def test_missing_sink_rolls_back_loaded_module(self):
        with patch.object(m,'find_sink',return_value=None), \
             patch.object(m.time,'monotonic',side_effect=range(0,50,5)), \
             patch.object(m.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'saída PipeWire'):m.start()
        self.assertFalse(m.PARAMS.exists());self.assertFalse(m.STATE_FILE.exists())
        self.assertTrue(self.wp)

    def test_missing_physical_input_rolls_back(self):
        with patch.object(m,'find_source',return_value=None), \
             patch.object(m.time,'monotonic',side_effect=range(0,50,5)), \
             patch.object(m.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'entrada física'):m.start()
        self.assertFalse(m.PARAMS.exists());self.assertFalse(m.STATE_FILE.exists())
        self.assertTrue(self.wp)
    def test_monitor_source_is_not_physical_input(self):
        with patch.object(m,'sources',return_value=[{'name':m.SINK+'.monitor'}]):
            self.assertIsNone(m.find_source(1000))

if __name__=='__main__':unittest.main(verbosity=2)
