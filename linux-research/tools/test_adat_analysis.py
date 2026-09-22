#!/usr/bin/env python3
"""Optical return acceptance and report/cleanup failure cases, no hardware."""
import copy,json,math,subprocess,sys,tempfile,unittest
from pathlib import Path
from analyze_capture import RATE
from analyze_channelmap import analyze_pair
from analyze_adat import assess_adat
from adat_result import passed

class AdatAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data=bytearray(RATE*10*6)
        for start,end,channels in ((1,3,(0,)),(4,6,(1,)),(7,9,(0,1))):
            for frame in range(start*RATE,end*RATE):
                for ch in channels:
                    value=round(83886*math.sin(2*math.pi*(750 if ch==0 else 1500)*frame/RATE))
                    at=frame*6+ch*3
                    data[at:at+3]=value.to_bytes(3,'little',signed=True)
        cls.data=data
        cls.pattern=analyze_pair(data)
        cls.quiet=analyze_pair(bytes(RATE*10*6))

    def test_known_tones_and_silence(self):
        self.assertTrue(assess_adat(self.pattern,'loopback'))
        self.assertFalse(assess_adat(self.pattern,'isolation'))
        self.assertTrue(assess_adat(self.quiet,'isolation'))
        self.assertFalse(assess_adat(self.quiet,'loopback'))

    def test_faint_correlated_return_rejected(self):
        weak=bytearray(len(self.data))
        for i in range(0,len(weak),3):
            value=int.from_bytes(self.data[i:i+3],'little',signed=True)//100
            weak[i:i+3]=value.to_bytes(3,'little',signed=True)
        self.assertFalse(assess_adat(analyze_pair(weak),'loopback'))

    def test_swapped_channels_rejected(self):
        swapped=bytearray(len(self.data))
        for i in range(0,len(swapped),6):
            swapped[i:i+6]=self.data[i+3:i+6]+self.data[i:i+3]
        self.assertFalse(assess_adat(analyze_pair(swapped),'loopback'))

    def test_cli_labels_preserve_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'capture.raw';raw.write_bytes(self.data)
            run=subprocess.run([sys.executable,str(Path(__file__).with_name('analyze_adat.py')),
                str(raw),'--optical-path','module','--input-pair','4','--expectation','loopback'],
                check=True,text=True,capture_output=True)
            self.assertIn('expected_optical_input=7',run.stdout)
            self.assertNotIn('expected_analog_input',run.stdout)
            result=json.loads(raw.with_suffix('.json').read_text())
            self.assertEqual(result['optical_path'],'module')
            self.assertTrue(result['expectation_met'])
            self.assertFalse(result['format_control_written'])

    def test_cleanup_and_wrong_profile_cannot_pass(self):
        profile={'optical_path':'enclosure','input_pair':1,'output_pair':1,
                 'input_selector':25,'output_register':'0x59','expectation':'loopback'}
        analysis={'expectation_met':True,'expectation':'loopback','input_pair':1,
                  'optical_path':'enclosure','frames':480000,'rate':48000,'format':'S24_3LE'}
        stats={'starts':'1','stops':'1','xruns':'0','last_error':'0','mute_restored':'Y','route_restored':'Y'}
        args=[profile,analysis,stats,0,True,True,True]
        self.assertTrue(passed(*args))
        for position in range(3,7):
            bad=copy.deepcopy(args);bad[position]=1 if position==3 else False
            self.assertFalse(passed(*bad))
        for group,key,value in ((0,'optical_path','module'),(0,'input_selector',9),
                (0,'output_register','0x4d'),(0,'output_pair',5),
                (1,'frames',479999),(1,'optical_path','module'),(1,'input_pair',2),
                (1,'expectation_met',False),(2,'starts','2'),(2,'stops','0'),
                (2,'xruns','1'),(2,'last_error','-110'),(2,'mute_restored','N'),(2,'route_restored','N')):
            bad=copy.deepcopy(args);bad[group][key]=value
            with self.subTest(key=key):self.assertFalse(passed(*bad))
        self.assertFalse(passed({}, {}, {}, 0, True, True, True))

if __name__=='__main__':unittest.main(verbosity=2)
