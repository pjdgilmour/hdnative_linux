#!/usr/bin/env python3
"""Offline evidence for the observed 192/48k profile. Never accesses hardware."""
import argparse,hashlib,json,struct
from pathlib import Path
from pe_evidence import PE
from inspect_dsi_prefs import inspect
DSI_SHA256='60af3e71ee24002b62ef1ab8535c0a3bd344b0c3d61e3e6d7ebdb5f73e642f34'

def analyze(dsi,prefs):
    pe=PE(dsi)
    if hashlib.sha256(pe.data).hexdigest()!=DSI_SHA256:
        raise ValueError('DSI build differs: the RVA evidence must be reviewed')
    def ptr(rva):return struct.unpack_from('<Q',pe.data,pe.offset(rva))[0]-pe.base
    # Secondary interface is installed at primary+8. Public master-status
    # uses +0x28; setter at +0x30; dispatcher at +0xb0.
    if [ptr(0x778390+n) for n in (0x28,0x30,0xb0)]!=[0x1a4b80,0x1a5a80,0x1afef0]:
        raise ValueError('Unexpected 192 vtable')
    begin,end=ptr(0x9aec68),ptr(0x9aec70)
    if (begin,end)!=(0x9aebf0,0x9aec68):raise ValueError('Unexpected sync table')
    table=[struct.unpack_from('<III',pe.data,pe.offset(rva)) for rva in range(begin,end,12)]
    saved=inspect(Path(prefs).read_bytes())
    configs=saved['saved_k016_text_configurations']
    if len(configs)!=1 or not configs[0]['decoded']:raise ValueError('Expected one known K016 profile')
    config=configs[0]['configuration'];c=config['common_fields'];d=config['digital_saved_fields']
    # Only this observed configuration has been traced through all relevant
    # branches. Other enum combinations may normalize fields before encoding.
    if config['card_fields'][2]!=[0,0,3,15,1] or c['syncMode']!=0 or c['slaveModeSelect']!=1:
        raise ValueError('Saved profile differs from the traced 48k/internal/master + ADAT/SRC profile')
    entry=next(x for x in table if x[0]==c['syncMode'])
    common1=0 | ((entry[1]&15)<<3) | ((c['slaveModeSelect']==1)<<7)
    # 1b1640 writes local registers in 0,1,2 order. 1af740 translates
    # local index as 0x20 + slot*8 + local. Slot2 is the digital card.
    local0=(d['object_18']&7)|((d['object_1c']&15)<<4)
    local1=({2:0,3:1,4:2}[d['source_enum']] |
            ((d['src_pair_mask']^15)<<2) |
            (int(d['src_pair_mask']==0)<<6) | (int(d['src_pair_mask']==15)<<7))
    local2=d['object_28']^1
    return {'dsi_sha256':DSI_SHA256,'prefs_sha256':saved['file_sha256'],
            'scope':'Offline candidate command bytes from saved software fields; NOT current readback or an initialization recipe. No hardware access.',
            'sample_rate_assumption_hz':48000,
            'common_control1':f'0x{common1:02x}',
            'common_control1_fields':{'rate_bits_0_2':0,'sync_bits_3_6':entry[1],
                                      'master_status_bit7':True},
            'sync_table':table,'digital_saved_fields':d,
            'candidate_module_registers':{f'0x{0x30+i:02x}':f'0x{v:02x}' for i,v in enumerate((local0,local1,local2))},
            'hardware_module_register_readback':'unavailable in previous 0x30..0x32 queries',
            'module_configuration_written':False,
            'rvas':{'master_status_export':'0x088ec0','master_getter':'0x1a4b80',
                    'master_setter':'0x1a5a80','sample_rate_encoder':'0x1a5050',
                    'common_writer':'0x1afbc0','digital_class_vtable':'0x7787d0',
                    'digital_writer':'0x1b1640','module_register_address':'0x1af740'}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dsi',type=Path);parser.add_argument('prefs',type=Path)
    args=parser.parse_args()
    try:result=analyze(args.dsi,args.prefs)
    except (ValueError,OSError) as e:parser.exit(1,str(e)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
