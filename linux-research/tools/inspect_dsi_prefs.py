#!/usr/bin/env python3
"""Read a DSIPrefs copy offline. Candidate saved state is NOT hardware readback."""
import argparse,hashlib,json,re,struct
from pathlib import Path
MAX_BYTES=16*1024*1024

def inspect_k016(payload):
    """Decode only the observed AD/DA/digital/DA text layout, never hardware state.

    DSI RVAs: 1a5380 loads K + model into 1024 bytes, 1aeae0 reads sc/xp/cards,
    1b1240 reads the five digital fields. Unknown layouts fail closed.
    """
    if len(payload) != 1024:
        raise ValueError('Unsupported K016 record size')
    text, separator, padding = payload.partition(b'\0')
    if not separator or any(padding):
        raise ValueError('Expected NUL-terminated, zero-padded K016 text')
    try:
        tokens = text.decode('ascii').split()
    except UnicodeDecodeError as e:
        raise ValueError('Non-ASCII K016 text') from e
    position = 0

    def literal(expected):
        nonlocal position
        if position >= len(tokens) or tokens[position] != expected:
            raise ValueError('Unexpected K016 token; expected ' + expected)
        position += 1

    def number():
        nonlocal position
        if position >= len(tokens) or not re.fullmatch(r'[0-9]{1,10}', tokens[position]):
            raise ValueError('Missing or invalid K016 unsigned integer')
        value = int(tokens[position]); position += 1
        if value > 0xffffffff:
            raise ValueError('K016 integer overflow')
        return value

    common = {}
    for label in ('syncMode', 'spdifCompatibilityDA30', 'meterOutputNotInput',
                  'slaveModeSelect', 'userSyncOutRate'):
        literal(label); common[label] = number()
    literal('sc'); sc = [number() for _ in range(8)]
    if sc[:4] != [3, 4, 5, 4]:
        raise ValueError('Unsupported K016 module layout')
    literal('xp'); routes = [number() for _ in range(30)]
    if any(value > 29 for value in routes):
        raise ValueError('K016 route outside the 30-entry domain')
    cards = []
    for index, field_count in enumerate((4, 1, 5, 1)):
        literal('card')
        if number() != index:
            raise ValueError('Unexpected K016 card order')
        cards.append([number() for _ in range(field_count)])
    literal('leg'); legacy = [number(), number()]
    if position != len(tokens):
        raise ValueError('Unexpected trailing K016 tokens')
    digital = cards[2]
    if digital[2] not in (2, 3, 4) or digital[3] > 15 or digital[4] > 1:
        raise ValueError('Unsupported K016 digital field values')
    return {
        'layout': 'K016 text, observed AD/DA/digital/DA topology',
        'common_fields': common, 'sc_fields': sc, 'routes': routes,
        'card_fields': cards, 'legacy_fields': legacy,
        'digital_saved_fields': {
            'object_18': digital[0], 'object_1c': digital[1],
            'source_enum': digital[2], 'src_pair_mask': digital[3],
            'object_28': digital[4],
        },
        'verified_current_hardware_state': False,
        'verified_adat_audio': False,
        'scope': 'Saved software fields, not register bytes or a hardware initialization script. '
                 'Source enum 3 correlates with ADAT in the supplied screenshot; '
                 'this parser does not independently identify the physical connector.',
    }

def inspect(data):
    if not 16 <= len(data) <= MAX_BYTES or data[:6]!=b'DSETUP':
        raise ValueError('Expected bounded DSETUP preferences file')
    version,size=struct.unpack_from('<HI',data,6)
    end=12+size
    if size<4 or end>len(data):raise ValueError('Truncated preferences payload')
    count=struct.unpack_from('<I',data,12)[0]
    if count>10000 or count>(size-4)//12:raise ValueError('Invalid record count')
    pos=16;records=[];keys=set();candidates=[];text_configs=[]
    for index in range(count):
        if pos+12>end:raise ValueError('Truncated record header')
        length,key=struct.unpack_from('<IQ',data,pos);pos+=12
        if length>end-pos:raise ValueError('Truncated record data')
        if key in keys:raise ValueError('Duplicate record key: ambiguous saved state')
        keys.add(key);payload=data[pos:pos+length]
        records.append({'index':index,'key':f'{key:016x}','size':length})
        if key >> 32 == 0x4b303136:  # ASCII K016, model-specific preference key.
            entry={'index':index,'key':f'{key:016x}','offset':pos,
                   'sha256':hashlib.sha256(payload).hexdigest()}
            try:
                entry['configuration']=inspect_k016(payload)
                entry['decoded']=True
            except ValueError as e:
                entry.update(decoded=False, error=str(e))
            text_configs.append(entry)
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
        'saved_k016_text_configurations':text_configs,
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
