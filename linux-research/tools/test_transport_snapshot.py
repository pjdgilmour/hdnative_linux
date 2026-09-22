#!/usr/bin/env python3
"""Exercise the actual fixed-read snapshot with a fake MMIO backend, no hardware."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='transport-snapshot-') as tmp:
    p=Path(tmp)
    (p/'native_transport_snapshot.h').write_bytes((ROOT/'native_transport_snapshot.h').read_bytes())
    (p/'test.c').write_text(r'''
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
static unsigned dl_read32(unsigned off);
static int silent_printf(const char *fmt, ...) { (void)fmt; return 0; }
static int silent_puts(const char *s) { (void)s; return 0; }
#define printf silent_printf
#define puts silent_puts
#include "native_transport_snapshot.h"
#undef printf
#undef puts
static unsigned values[TRANSPORT_REGISTER_COUNT], reads;
static unsigned dl_read32(unsigned off) {
    unsigned i=reads++ % TRANSPORT_REGISTER_COUNT;
    assert(off==transport_registers[i].offset);
    return values[i];
}
static void reset(void) {
    reads=0;
    for(unsigned i=0;i<TRANSPORT_REGISTER_COUNT;i++)values[i]=transport_registers[i].expected;
}
int main(void) {
    reset(); assert(native_transport_snapshot()==0);
    assert(reads==2*TRANSPORT_REGISTER_COUNT);
    for(unsigned i=0;i<TRANSPORT_REGISTER_COUNT;i++) {
        for(unsigned bit=0;bit<32;bit++) {
            reset(); values[i]^=1u<<bit;
            unsigned expected=(transport_registers[i].mask & (1u<<bit)) ? 2 : 0;
            assert(native_transport_snapshot()==expected);
            assert(reads==2*TRANSPORT_REGISTER_COUNT);
        }
    }
    puts("PASS: exact read order/bound, each checked bit rejects mismatch, ignored bits preserved; no write backend");
    return 0;
}
''')
    subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
# The special mode exits to shared PCI cleanup before the normal query path.
s=(ROOT/'identify_192.c').read_text()
branch=s[s.index('    if (transport) {'):s.index('    const unsigned status_offsets[]')]
assert 'goto done;' in branch and 'native_transport_snapshot()' in branch
assert 'dl_write32(' not in branch and 'dl_query(' not in branch
print('PASS: snapshot mode reaches PCI restoration without falling through to DigiLink queries')
