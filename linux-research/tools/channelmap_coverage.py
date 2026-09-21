#!/usr/bin/env python3
"""Summarize completed physical pair tests; no hardware access."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def summarize(paths):
    inputs=set();outputs=set();sessions=[]
    for p in paths:
        try:
            s=json.loads(p.read_text())
            if not isinstance(s,dict):continue
            if s.get('expectation','loopback')!='loopback':continue
            if not all(s.get(k) is True for k in ('passed','pci_header_restored','pci_unbound')):continue
            if s.get('analysis',{}).get('loopback_pattern_matched') is not True:continue
            st=s.get('stats',{})
            if not all(st.get(k)=='1' for k in ('starts','stops')):continue
            if not all(st.get(k)=='0' for k in ('xruns','last_error')):continue
            if not all(st.get(k)=='Y' for k in ('mute_restored','route_restored')):continue
            o=s['output_pair'];i=s['input_pair']
            if type(o)!=int or type(i)!=int or not (1<=o<=8 and 1<=i<=4):continue
            inputs.update((2*i-1,2*i));outputs.update((2*o-1,2*o));sessions.append(str(p.parent.name))
        except (OSError,ValueError,KeyError,TypeError,AttributeError):continue
    return {'analog_inputs_passed':sorted(inputs),'analog_outputs_passed':sorted(outputs),
        'analog_inputs_pending':sorted(set(range(1,9))-inputs),'analog_outputs_pending':sorted(set(range(1,17))-outputs),
        'digital_status':'not tested by this analog-only tool','sessions':sessions,
        'scope':'Matching tone tests with requested pair routes at 48 kHz; assumes known physical wiring. Does not independently verify connector numbering, isolation, LEDs or simultaneous multichannel operation.'}
if __name__=='__main__':
    result=summarize(sorted((ROOT/'reports').glob('channelmap-test-*/session.json')))
    print(json.dumps(result,indent=2))
