#!/usr/bin/env python3
"""Analyze selected analog pairs, distinguishing loopback from isolation."""
import argparse,json,math,wave
from pathlib import Path
from analyze_capture import analyze,db

def assess(result, expectation):
    if expectation == 'loopback':
        return result.get('loopback_pattern_matched') is True
    if expectation != 'isolation':
        raise ValueError('Unknown expectation')
    if (result.get('frames'),result.get('rate'),result.get('format')) != (480000,48000,'S24_3LE'):
        return False
    spectra=result.get('spectral_windows',[])
    channels=result.get('channels',[])
    if len(spectra)!=3 or len(channels)!=2 or any(len(row)!=2 for row in spectra):return False
    for row in spectra:
        for c in row:
            amp=c.get('amplitude')
            if not isinstance(amp,(int,float)) or not math.isfinite(amp) or not 0<=amp<1e-4:return False
    # Keep whole-recording clipping protection, including startup/shutdown.
    if any(c.get('near_clip_samples')!=0 for c in channels):return False
    steady=result.get('isolation_windows',{}).get('steady',{})
    if steady.get('start_seconds')!=1 or steady.get('end_seconds')!=9:return False
    levels=steady.get('channels',[])
    if len(levels)!=2:return False
    for c in levels:
        if 'rms_dbfs' not in c:return False
        rms=c['rms_dbfs']
        if rms is not None and (not isinstance(rms,(int,float)) or not math.isfinite(rms) or rms>=-65):return False
    return result.get('loopback_pattern_matched') is False

def analyze_pair(data):
    result=analyze(data,True)
    # Tone schedule starts at 1 s and ends at 9 s. Measure ALL that interval,
    # not just the narrow spectral windows; report excluded edges separately.
    windows={}
    for label,start,end in [('startup',0,1),('steady',1,9),('ending',9,10)]:
        channels=[]
        for ch in range(2):
            samples=[int.from_bytes(data[i+ch*3:i+ch*3+3],'little',signed=True)/8388608
                     for i in range(start*48000*6,end*48000*6,6)]
            channels.append({'rms_dbfs':db(math.sqrt(sum(v*v for v in samples)/len(samples))),
                             'peak_dbfs':db(max(map(abs,samples)))})
        windows[label]={'start_seconds':start,'end_seconds':end,'channels':channels}
    result.update(analysis_version=2,isolation_windows=windows)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('raw',type=Path);p.add_argument('--input-pair',required=True,type=int,choices=range(1,5))
    p.add_argument('--expectation',choices=('loopback','isolation'),required=True)
    a=p.parse_args();data=a.raw.read_bytes();result=analyze_pair(data)
    result.update(expectation=a.expectation,expectation_met=assess(result,a.expectation),
                  input_pair=a.input_pair,input_channels=[2*a.input_pair-1,2*a.input_pair])
    if a.expectation=='isolation':
        result['isolation_limits']={'tone_amplitude_below_dbfs':-80,'steady_rms_below_dbfs':-65,'steady_start_seconds':1,'steady_end_seconds':9}
    with wave.open(str(a.raw.with_suffix('.wav')),'wb') as w:
        w.setnchannels(2);w.setsampwidth(3);w.setframerate(48000);w.writeframes(data)
    a.raw.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
    for ch,metrics in enumerate(result['channels'],1):
        print(f'PCM_CHANNEL_{ch} expected_analog_input={2*a.input_pair-2+ch}: '+json.dumps(metrics))
    if a.expectation=='isolation':
        print('ISOLATION_WINDOWS='+json.dumps(result['isolation_windows']))
    print('LOOPBACK_PATTERN_MATCHED='+('yes' if result['loopback_pattern_matched'] else 'no'))
    print('EXPECTED_RESULT='+a.expectation)
    print('EXPECTED_RESULT_MET='+('yes' if result['expectation_met'] else 'no'))
    print('WAV='+str(a.raw.with_suffix('.wav')))
    print('Os números físicos são o roteamento solicitado; dependem da ligação conhecida do cabo.')
if __name__=='__main__':main()
