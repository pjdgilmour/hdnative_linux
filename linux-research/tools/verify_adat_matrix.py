#!/usr/bin/env python3
"""Verify a complete 4x4 enclosure experiment and exact aligned tone samples.
Read-only for session artifacts; requires cc but no root or hardware access.
Usage: verify_adat_matrix.py REPORT_DIR ... (16 directories); JSON on stdout.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from adat_result import passed

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include "native_adat_ring.h"
int main(void) {
 unsigned char *tx=calloc(NC_TX_FRAMES,256);
 if(!tx)return 1;
 for(unsigned frame=0;frame<480000;frame+=1024){
  unsigned n=480000-frame;if(n>1024)n=1024;
  nc_tx_fill(tx,frame,n,1);
  for(unsigned i=0;i<n;i++)if(fwrite(tx+((frame+i)%NC_TX_FRAMES)*256+4,1,6,stdout)!=6)return 2;
 }
 free(tx);return 0;
}
'''

def exact_return(raw, reference):
    def onset(data):
        return next(i for i in range(0, len(data), 6) if any(data[i:i+6])) // 6
    lag = onset(raw) - onset(reference)
    assert 0 <= lag < 1024, 'Unexpected alignment'
    assert not any(raw[:lag*6]), 'Nonzero startup'
    assert raw[lag*6:] == reference[:len(raw)-lag*6], 'PCM differs at unity gain after alignment'
    return {'alignment_frames': lag, 'exact_compared_frames': len(raw)//6-lag}

def verify(directories):
    assert len(directories) == 16, 'Exactly 16 sessions required'
    build = json.loads((ROOT/'reports/adat-build.json').read_text())
    header = ROOT/'kernel/native_adat_ring.h'
    assert hashlib.sha256(header.read_bytes()).hexdigest() == build['sha256']['kernel/native_adat_ring.h']
    with tempfile.TemporaryDirectory(prefix='adat-reference-') as tmp:
        tmp = Path(tmp)
        (tmp/'reference.c').write_text(GENERATOR)
        subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
                        '-I',str(ROOT/'kernel'),str(tmp/'reference.c'),'-o',str(tmp/'reference')], check=True)
        reference = subprocess.check_output([str(tmp/'reference')])
    assert len(reference) == 480000*6
    rows = []; combinations = set()
    for directory in directories:
        d = Path(directory)
        s = json.loads((d/'session.json').read_text())
        p = json.loads((d/'profile.json').read_text())
        a = json.loads((d/'capture.json').read_text())
        stats = dict(line.split('=',1) for line in (d/'stats.txt').read_text().splitlines())
        assert stats == s['stats'] and a == s['analysis']
        assert all(s.get(k) == v for k,v in p.items())
        assert p['windows_state'] and p['optical_path'] == 'enclosure'
        assert p['module_sha256'] == build['sha256']['kernel/avid_native_adat.ko']
        assert s['passed'] and passed(p,a,stats,0,s['pci_header_restored'],s['pci_unbound'],s['module_removed'])
        assert (d/'pci-before.bin').read_bytes() == (d/'pci-after.bin').read_bytes()
        pair = (p['output_pair'], p['input_pair'])
        assert pair not in combinations; combinations.add(pair)
        raw = (d/'capture.raw').read_bytes()
        assert len(raw) == 480000*6
        sha = hashlib.sha256(raw).hexdigest(); assert sha == s['raw_sha256']
        row = {'session':d.name,'output_pair':pair[0],'input_pair':pair[1],
               'raw_sha256':sha,'max_poll_us':int(stats['max_poll_us'])}
        if pair[0] == pair[1]:
            assert p['expectation'] == 'loopback'
            row.update(exact_return(raw,reference))
        else:
            assert p['expectation'] == 'isolation' and not any(raw), 'Nonzero isolation capture'
            row['all_samples_zero'] = True
        rows.append(row)
    assert combinations == {(o,i) for o in range(1,5) for i in range(1,5)}
    return {'matrix_passed':True,'rate':48000,'format':'S24_3LE','frames_per_session':480000,
            'windows_state':True,'optical_path':'enclosure',
            'module_sha256':build['sha256']['kernel/avid_native_adat.ko'],
            'ring_header_sha256':build['sha256']['kernel/native_adat_ring.h'],
            'reference_sha256':hashlib.sha256(reference).hexdigest(),
            'scope':'pairs sequentially; exact comparison only on aligned overlap, no gain adjustment',
            'sessions':rows}

if __name__ == '__main__':
    print(json.dumps(verify(sys.argv[1:]),indent=2))
