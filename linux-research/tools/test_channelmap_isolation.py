#!/usr/bin/env python3
"""Counter-tests must reject leaked/swapped tones and must not count as coverage."""
import copy,json,math,subprocess,sys,tempfile,unittest
from pathlib import Path
from analyze_capture import analyze,RATE
from analyze_channelmap import assess,analyze_pair
from channelmap_coverage import summarize
class IsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quiet=analyze_pair(bytes(RATE*10*6))
        # Opposite frequencies in the two channels: loopback pattern fails,
        # but this is not silence and MUST NOT pass the isolation check.
        frame=bytearray()
        for i in range(64):
            for freq in (1500,750):
                frame+=round(70000*math.sin(2*math.pi*freq*i/RATE)).to_bytes(3,'little',signed=True)
        cls.swapped=analyze_pair(frame*(RATE*10//64))
    def test_quiet_only_passes_isolation(self):
        self.assertTrue(assess(self.quiet,'isolation'))
        self.assertFalse(assess(self.quiet,'loopback'))
    def test_failed_pattern_is_not_sufficient(self):
        self.assertFalse(self.swapped['loopback_pattern_matched'])
        self.assertFalse(assess(self.swapped,'isolation'))
    def test_small_coherent_leak_rejected(self):
        d=copy.deepcopy(self.quiet);d['spectral_windows'][0][0]['amplitude']=0.0002
        self.assertFalse(assess(d,'isolation'))
    def test_nonfinite_and_incomplete_rejected(self):
        d=copy.deepcopy(self.quiet);d['spectral_windows'][1][1]['amplitude']=float('nan')
        self.assertFalse(assess(d,'isolation'))
        self.assertFalse(assess({},'isolation'))
        d=copy.deepcopy(self.quiet);d['isolation_windows']['steady']['channels'][1]['rms_dbfs']=float('nan')
        self.assertFalse(assess(d,'isolation'))
    def test_startup_transient_is_reported_separately(self):
        data=bytearray(RATE*10*6)
        # Decaying transient confined to first second, not a hidden PCM tone.
        for frame in range(RATE//10,RATE):
            v=round(100000*math.exp(-(frame-RATE//10)/(RATE*.08)))
            data[frame*6:frame*6+3]=v.to_bytes(3,'little',signed=True)
        r=analyze_pair(data)
        self.assertGreater(r['channels'][0]['rms_dbfs'],-65)
        self.assertTrue(assess(r,'isolation'))
        self.assertGreater(r['isolation_windows']['startup']['channels'][0]['peak_dbfs'],-50)
        # A burst outside the narrow spectral windows but INSIDE the entire
        # 1..9 s interval must still be rejected by broadband RMS.
        data[3*RATE*6:4*RATE*6]=data[:RATE*6]
        self.assertFalse(assess(analyze_pair(data),'isolation'))
    def test_clipping_in_excluded_startup_is_rejected(self):
        d=copy.deepcopy(self.quiet);d['channels'][0]['near_clip_samples']=1
        self.assertFalse(assess(d,'isolation'))
    def test_legacy_report_requires_reanalysis(self):
        d=copy.deepcopy(self.quiet);del d['isolation_windows']
        self.assertFalse(assess(d,'isolation'))
    def test_isolation_excluded_from_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'session.json'
            p.write_text(json.dumps({'passed':True,'pci_header_restored':True,'pci_unbound':True,
                'expectation':'isolation','input_pair':1,'output_pair':2,
                'analysis':{'loopback_pattern_matched':True},
                'stats':{'starts':'1','stops':'1','xruns':'0','last_error':'0','mute_restored':'Y','route_restored':'Y'}}))
            self.assertEqual(summarize([p])['analog_outputs_passed'],[])
    def test_cli_labels_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'capture.raw';p.write_bytes(bytes(RATE*10*6))
            run=subprocess.run([sys.executable,str(Path(__file__).with_name('analyze_channelmap.py')),str(p),
                '--input-pair','2','--expectation','isolation'],check=True,text=True,capture_output=True)
            self.assertIn('PCM_CHANNEL_1 expected_analog_input=3',run.stdout)
            self.assertIn('PCM_CHANNEL_2 expected_analog_input=4',run.stdout)
            self.assertIn('EXPECTED_RESULT_MET=yes',run.stdout)
            report=json.loads(p.with_suffix('.json').read_text())
            self.assertEqual(report['expectation'],'isolation')
            self.assertTrue(report['expectation_met']);self.assertTrue(p.with_suffix('.wav').exists())
if __name__=='__main__':unittest.main(verbosity=2)
