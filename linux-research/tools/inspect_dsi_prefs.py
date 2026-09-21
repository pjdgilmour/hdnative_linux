#!/usr/bin/env python3
"""Read a DSIPrefs copy offline. Candidate saved state is NOT hardware readback."""
import argparse,hashlib,json,struct
from pathlib import Path
MAX_BYTES=16*1024*1024

def inspect(data):
    if not 16 <= len(data) <= MAX_BYTES or data[:6]!=b'DSETUP':
        raise ValueError('Expected bounded DSETUP preferences file')
    version,size=struct.unpack_from('<HI',data,6)
    end=12+size
    if size<4 or end>len(data):raise ValueError('Truncated preferences payload')
    count=struct.unpack_from('<I',data,12)[0]
    if count>10000 or count>(size-4)//12:raise ValueError('Invalid record count')
    pos=16;records=[];keys=set();candidates=[]
    for index in range(count):
        if pos+12>end:raise ValueError('Truncated record header')
        length,key=struct.unpack_from('<IQ',data,pos);pos+=12
        if length>end-pos:raise ValueError('Truncated record data')
        if key in keys:raise ValueError('Duplicate record key: ambiguous saved state')
        keys.add(key);payload=data[pos:pos+length]
        records.append({'index':index,'key':f'{key:016x}','size':length})
        # DSI 1aea30 requests 0x6c bytes; module 2 is buffer+0x0f+2*8.
        # Size alone is not identification: never promote these to verified state.
        if length==0x6c:
            candidates.append({'index':index,'key':f'{key:016x}','offset':pos,
                'sha256':hashlib.sha256(payload).hexdigest(),
                'candidate_digital_bytes':payload[0x1f:0x22].hex(' '),
                'verified_192_record':False,'verified_current_hardware_state':False})
        pos+=length
    return {'file_sha256':hashlib.sha256(data).hexdigest(),'header_version':version,
        'record_count':count,'records':records,'candidates_108_bytes':candidates,
        'unused_payload_bytes':end-pos,'trailing_file_bytes':len(data)-end,
        'scope':'Saved preferences only; record identity, model, freshness and format selection remain unverified. No hardware access or writes.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('file',type=Path)
    a=p.parse_args()
    try:
        with a.file.open('rb') as f:data=f.read(MAX_BYTES+1)
        print(json.dumps(inspect(data),indent=2))
    except (OSError,ValueError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
