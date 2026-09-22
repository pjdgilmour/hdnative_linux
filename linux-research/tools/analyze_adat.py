#!/usr/bin/env python3
"""Assess a bounded optical loopback; never infer hardware format from preferences."""
import argparse,json,math,wave
from pathlib import Path
from analyze_channelmap import analyze_pair,assess

def assess_adat(result, expectation):
    if not assess(result, expectation):
        return False
    if expectation == 'isolation':
        return True
    # A digital return of the -40 dBFS generator should be close to unity.
    # Reject a faint correlated leak as a valid pair; no bit-perfect claim.
    for ch in range(2):
        for window in (ch, 2):
            amplitude = result['spectral_windows'][window][ch]['amplitude']
            if not math.isfinite(amplitude) or not 10**(-43/20) <= amplitude <= 10**(-37/20):
                return False
    return True

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--optical-path',required=True,choices=('enclosure','module'));
    p.add_argument('raw',type=Path);p.add_argument('--input-pair',required=True,type=int,choices=range(1,5))
    p.add_argument('--expectation',choices=('loopback','isolation'),required=True)
    a=p.parse_args();data=a.raw.read_bytes();result=analyze_pair(data)
    result.update(expectation=a.expectation,expectation_met=assess_adat(result,a.expectation),
                  optical_path=a.optical_path,format_control_written=False,clock_control_written=False,
                  input_pair=a.input_pair,input_channels=[2*a.input_pair-1,2*a.input_pair])
    result['on_tone_amplitude_limits_dbfs']=[-43,-37]
    if a.expectation=='isolation':
        result['isolation_limits']={'tone_amplitude_below_dbfs':-80,'steady_rms_below_dbfs':-65,'steady_start_seconds':1,'steady_end_seconds':9}
    with wave.open(str(a.raw.with_suffix('.wav')),'wb') as w:
        w.setnchannels(2);w.setsampwidth(3);w.setframerate(48000);w.writeframes(data)
    a.raw.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
    for ch,metrics in enumerate(result['channels'],1):
        print(f'PCM_CHANNEL_{ch} optical_path={a.optical_path} expected_optical_input={2*a.input_pair-2+ch}: '+json.dumps(metrics))
    if a.expectation=='isolation':
        print('ISOLATION_WINDOWS='+json.dumps(result['isolation_windows']))
    print('LOOPBACK_PATTERN_MATCHED='+('yes' if result['loopback_pattern_matched'] else 'no'))
    print('EXPECTED_RESULT='+a.expectation)
    print('EXPECTED_RESULT_MET='+('yes' if result['expectation_met'] else 'no'))
    print('WAV='+str(a.raw.with_suffix('.wav')))
    print('O caminho físico depende do cabo informado. Ausência de tons não prova defeito nem seleção ADAT.')
if __name__=='__main__':main()
