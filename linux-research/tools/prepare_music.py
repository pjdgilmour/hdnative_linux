#!/usr/bin/env python3
"""Decode a local track to verified low-level stereo PCM for the ALSA prototype."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import numpy as np

RATE = 48000

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def prepare(source, output, report):
    source=source.resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    source_hash=digest(source)
    with tempfile.TemporaryDirectory(prefix='native-music-') as d:
        intermediate=Path(d)/'decoded.f32'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(source),
                        '-map','0:a:0','-vn','-ac','2','-ar',str(RATE),
                        '-c:a','pcm_f32le','-f','f32le',str(intermediate)],check=True)
        size=intermediate.stat().st_size
        if not size or size%8 or size>RATE*320*8:
            raise ValueError('Faixa fora do limite de 320 segundos do teste.')
        frames=size//8
        pcm=np.memmap(intermediate,dtype='<f4',mode='r')
        peak=0.0
        for start in range(0,len(pcm),1048576):
            block=pcm[start:start+1048576]
            if not np.all(np.isfinite(block)):
                raise ValueError('Amostra não finita no áudio decodificado.')
            peak=max(peak,float(np.max(np.abs(block))))
        del pcm
        if peak==0:
            raise ValueError('Arquivo sem sinal de áudio.')
        # Reserve quantization margin; never amplify a quiet source.
        gain=min(1.0,(83884/8388608)/peak)
        fade=min(2400,frames//4)
        filters=(f'volume={gain:.17g}:precision=double,'
                 f'afade=t=in:ss=0:ns={fade},'
                 f'afade=t=out:ss={frames-fade}:ns={fade}')
        subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror',
                        '-f','f32le','-ar',str(RATE),'-ac','2','-i',str(intermediate),
                        '-af',filters,'-c:a','pcm_s24le','-f','s24le','-y',str(output)],check=True)
    assert output.stat().st_size==frames*6
    peaks=[0,0]
    with output.open('rb') as f:
        while raw:=f.read(6*65536):
            b=np.frombuffer(raw,dtype=np.uint8).reshape(-1,3).astype(np.int32)
            v=b[:,0] | (b[:,1]<<8) | (b[:,2]<<16)
            v=((v^0x800000)-0x800000).reshape(-1,2)
            for channel in range(2):
                peaks[channel]=max(peaks[channel],int(np.max(np.abs(v[:,channel]))))
    assert max(peaks)<=83886 and min(peaks)>0,peaks
    assert digest(source)==source_hash,'Source changed during preparation'
    result={'source':str(source),'source_sha256':source_hash,
            'output':str(output.resolve()),'output_sha256':digest(output),
            'format':'S24_3LE','channels':2,'rate':RATE,'frames':frames,
            'duration_seconds':frames/RATE,'gain_db':20*math.log10(gain),
            'peaks_s24':peaks,'peak_dbfs':20*math.log10(max(peaks)/8388607),
            'fade_frames':fade,'timeout_seconds':math.ceil(frames/RATE)+15,
            'prepared_only':True}
    report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    prepare(a.source,a.output,a.report)
