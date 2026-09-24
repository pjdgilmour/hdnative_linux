#!/usr/bin/env python3
"""Inventory embedded DigiTest resources without executing or extracting firmware.
Usage: inspect_digitest_resources.py /path/to/DigiTest.exe
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
from pe_evidence import PE

def inspect(path):
    pe = PE(path)
    data = pe.data
    rva, size = pe.dirs[2]
    assert rva and size, 'No PE resources'
    base = pe.offset(rva)
    seen = set()
    resources = []
    def region(off, length):
        assert 0 <= off <= size and 0 <= length <= size-off, 'Invalid resource bounds'
        assert base+off+length <= len(data), 'Truncated resource'
        return base+off
    def walk(off, path=()):
        assert off not in seen and len(path) < 8, 'Resource cycle or excessive depth'
        seen.add(off)
        at = region(off,16)
        names, ids = struct.unpack_from('<HH', data, at+12)
        region(off+16,8*(names+ids))
        for i in range(names+ids):
            key,value = struct.unpack_from('<II',data,at+16+8*i)
            if key & 0x80000000:
                string_off=key & 0x7fffffff
                length=struct.unpack_from('<H',data,region(string_off,2))[0]
                text_at=region(string_off+2,2*length)
                key=data[text_at:text_at+2*length].decode('utf-16le')
            if value & 0x80000000:
                walk(value & 0x7fffffff,path+(key,))
            else:
                addr,n,codepage,_=struct.unpack_from('<IIII',data,region(value,16))
                start=pe.offset(addr)
                assert n and pe.offset(addr+n-1)==start+n-1, 'Resource crosses unbacked data'
                payload=data[start:start+n]
                assert len(payload)==n
                row={'path':list(path+(key,)),'rva':hex(addr),'size':n,
                     'sha256':hashlib.sha256(payload).hexdigest()}
                if path and path[0]==16:
                    fixed=payload.find(bytes.fromhex('bd04effe'))
                    if 0 <= fixed <= n-16:
                        hi,lo=struct.unpack_from('<II',payload,fixed+8)
                        row['file_version']=[hi>>16,hi&65535,lo>>16,lo&65535]
                resources.append(row)
    walk(0)
    return {'file':str(Path(path)), 'sha256':hashlib.sha256(data).hexdigest(),
            'image_base':hex(pe.base),'resources':resources,
            'scope':'resource inventory only; labels do not establish installed firmware or hardware compatibility'}

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit(__doc__)
    print(json.dumps(inspect(sys.argv[1]),indent=2))
