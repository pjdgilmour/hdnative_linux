#!/usr/bin/env python3
"""Only successful restored physical sessions contribute to coverage."""
import copy,json,tempfile,unittest
from pathlib import Path
from channelmap_coverage import summarize
class Coverage(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.good={'passed':True,'pci_header_restored':True,'pci_unbound':True,
          'analysis':{'loopback_pattern_matched':True},
          'stats':{'xruns':'0','last_error':'0','mute_restored':'Y','route_restored':'Y', 'starts':'1','stops':'1'},
          'output_pair':1,'input_pair':1}
    def put(self,n,data):
        p=self.root/str(n)/'session.json';p.parent.mkdir();p.write_text(json.dumps(data));return p
    def test_banks(self):
        paths=[]
        for o in range(1,9):
            d=copy.deepcopy(self.good);d.update(output_pair=o,input_pair=(o-1)%4+1)
            paths.append(self.put(o,d))
        a=summarize(paths)
        self.assertEqual(a['analog_outputs_passed'],list(range(1,17)))
        self.assertEqual(a['analog_inputs_passed'],list(range(1,9)))
        self.assertFalse(a['analog_inputs_pending']);self.assertFalse(a['analog_outputs_pending'])
    def test_failures_excluded(self):
        cases=[]
        for key in ('passed','pci_header_restored','pci_unbound'):
            d=copy.deepcopy(self.good);d[key]=False;cases.append(d)
        d=copy.deepcopy(self.good);d['analysis']['loopback_pattern_matched']=False;cases.append(d)
        for k,v in [('xruns','1'),('last_error','-5'),('mute_restored','N'),('route_restored','N'),('starts','0'),('stops','0')]:
            d=copy.deepcopy(self.good);d['stats'][k]=v;cases.append(d)
        for k,v in [('input_pair',5),('output_pair',9),('output_pair',True)]:
            d=copy.deepcopy(self.good);d[k]=v;cases.append(d)
        cases += [None,[],{'passed':True,'pci_header_restored':True,'pci_unbound':True,'analysis':None}]
        paths=[self.put(i,d) for i,d in enumerate(cases)]
        p=self.root/'bad.json';p.write_text('{');paths.append(p)
        self.assertFalse(summarize(paths)['analog_outputs_passed'])
    def test_partial_and_duplicate(self):
        d=copy.deepcopy(self.good);d.update(output_pair=7,input_pair=3)
        a=summarize([self.put(1,d),self.put(2,d)])
        self.assertEqual(a['analog_outputs_passed'],[13,14])
        self.assertEqual(a['analog_inputs_passed'],[5,6])
        self.assertEqual(len(a['analog_outputs_pending']),14)
if __name__=='__main__':unittest.main()
