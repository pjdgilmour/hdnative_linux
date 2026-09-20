#!/usr/bin/env python3
"""Analyze 10 s stereo S24_3LE; write a WAV and report without playback."""
import argparse,json,math,wave
from pathlib import Path
RATE=48000
SCALE=8388608

def db(value):
    return round(20*math.log10(value),2) if value>0 else None

def analyze(data,loopback=False):
    if len(data)!=RATE*10*6:
        raise ValueError(f'Expected 480000 stereo frames, got {len(data)} bytes')
    channels=[[int.from_bytes(data[i+c*3:i+c*3+3],'little',signed=True)/SCALE
               for i in range(0,len(data),6)] for c in range(2)]
    result={'frames':len(data)//6,'rate':RATE,'format':'S24_3LE','channels':[],'loopback':loopback}
    for samples in channels:
        mean=sum(samples)/len(samples)
        rms=math.sqrt(sum(v*v for v in samples)/len(samples))
        result['channels'].append({'peak_dbfs':db(max(map(abs,samples))), 'rms_dbfs':db(rms),
            'dc':mean,'nonzero_samples':sum(v!=0 for v in samples),
            'near_clip_samples':sum(abs(v)>=0.999 for v in samples)})
    result['nonzero_both_channels']=all(c['nonzero_samples'] for c in result['channels'])
    if loopback:
        windows=[(1.5,2.5),(4.5,5.5),(7.5,8.5)]
        spectra=[]
        for start,end in windows:
            row=[]
            for ch,freq in enumerate((750,1500)):
                s=channels[ch][int(start*RATE):int(end*RATE)]
                co=[math.cos(2*math.pi*freq*i/RATE) for i in range(64)]
                si=[math.sin(2*math.pi*freq*i/RATE) for i in range(64)]
                amp=2*math.hypot(sum(v*co[i%64] for i,v in enumerate(s)),sum(v*si[i%64] for i,v in enumerate(s)))/len(s)
                rms=math.sqrt(sum(v*v for v in s)/len(s))
                row.append({'frequency':freq,'amplitude':amp,'amplitude_dbfs':db(amp),'tone_fraction':amp/(math.sqrt(2)*rms) if rms else 0})
            spectra.append(row)
        passed=True
        for ch in range(2):
            on=spectra[ch][ch]; off=spectra[1-ch][ch]; both=spectra[2][ch]
            passed &= on['amplitude']>1e-5 and on['tone_fraction']>0.8 and both['tone_fraction']>0.8
            passed &= on['amplitude']>10*off['amplitude'] and both['amplitude']>1e-5
        passed &= all(c['near_clip_samples']==0 for c in result['channels'])
        result.update(loopback_pattern_matched=bool(passed),spectral_windows=spectra)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('raw',type=Path);p.add_argument('--loopback',action='store_true')
    a=p.parse_args();data=a.raw.read_bytes();result=analyze(data,a.loopback)
    with wave.open(str(a.raw.with_suffix('.wav')),'wb') as w:
        w.setnchannels(2);w.setsampwidth(3);w.setframerate(RATE);w.writeframes(data)
    a.raw.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
    for ch,metrics in enumerate(result['channels'],1): print(f'INPUT_{ch}: '+json.dumps(metrics))
    print('CAPTURE_FILE_COMPLETE=yes')
    if a.loopback: print('LOOPBACK_PATTERN_MATCHED='+('yes' if result['loopback_pattern_matched'] else 'no'))
    print('WAV='+str(a.raw.with_suffix('.wav')))
    print('Dados não nulos, isoladamente, não confirmam sinal analógico nem o par físico.')
if __name__=='__main__':main()
