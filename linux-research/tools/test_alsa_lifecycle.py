#!/usr/bin/env python3
"""Fault-inject the actual ALSA driver's cleanup function without hardware."""
from pathlib import Path
import os
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[1]
source = (ROOT/'kernel/avid_native_alsa.c').read_text()
cleanup = source[source.index('static int finish_session('):source.index('static const struct snd_pcm_hardware')]
prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define THIS_MODULE 0
#define dev_info(...) do {} while (0)
#define dev_err(...) do {} while (0)
static unsigned stops;
static int last_error;
static bool mute_restored, route_restored;
static unsigned long long last_frames;
static const unsigned saved_offsets[] = {0x10,0x20,0x42004};
struct native_192 {
    int write_attempted, route_write_attempted, restore_required, route_restore_required;
    int after, route_after;
};
struct native_alsa {
    bool running, prepared, configured, quarantined, faulted;
    struct native_192 peripheral;
    struct {unsigned long long consumed, queued; unsigned hw;} ring;
    unsigned saved[3];
    void *pdev;
};
static int drain_ok, mute_error, route_error, pins, refs, resets, writes;
static char events[100];
static void event(char c) { size_t n=strlen(events); events[n]=c; events[n+1]=0; }
static bool stop_dma(struct native_alsa *e) { (void)e; event('D'); return drain_ok; }
static int n192_restore(struct native_192 *p) {
    event('M'); if (!mute_error) p->restore_required=0; return mute_error;
}
static int n192_route_restore(struct native_192 *p) {
    event('R'); if (!route_error) p->route_restore_required=0; return route_error;
}
static void __module_get(int x) { (void)x; pins++; }
static void pci_dev_get(void *x) { (void)x; refs++; }
static void wr(struct native_alsa *e, unsigned off, unsigned value) {
    assert(off == saved_offsets[2-writes]); assert(value == e->saved[2-writes]); writes++;
}
static void flush(struct native_alsa *e) { (void)e; event('F'); }
static void init_peripheral(struct native_alsa *e) { memset(&e->peripheral,0,sizeof(e->peripheral)); resets++; }
static struct native_alsa fresh(void) {
    struct native_alsa e={.running=true,.prepared=true,.configured=true,
        .peripheral={.write_attempted=1,.route_write_attempted=1,.restore_required=1,.route_restore_required=1},
        .ring={.consumed=12000,.queued=15000,.hw=3808},.saved={10,20,30}};
    stops=0; last_error=0; drain_ok=1; mute_error=route_error=0;
    pins=refs=resets=writes=0; events[0]=0; mute_restored=route_restored=false;
    return e;
}
'''
suffix = r'''
int main(void) {
    struct native_alsa e=fresh();
    assert(finish_session(&e)==0);
    assert(!strcmp(events,"DMRF"));
    assert(!e.running && !e.prepared && !e.configured && !e.faulted);
    assert(stops==1 && writes==3 && resets==1 && last_frames==12000);
    assert(mute_restored && route_restored && !pins && !refs);
    assert(finish_session(&e)==0); /* STOP -> hw_free -> close must be harmless. */
    assert(stops==1 && writes==3 && resets==1);
    puts("PASS: successful cleanup, reverse MMIO restore, repeated close");
    e=fresh(); mute_error=-ETIMEDOUT;
    assert(finish_session(&e)==-ETIMEDOUT);
    assert(!strcmp(events,"DMRF")); /* Route cleanup still attempted. */
    assert(e.faulted && !e.configured && !resets && !mute_restored && route_restored);
    assert(last_error==-ETIMEDOUT);
    puts("PASS: lost mute ACK cannot skip route cleanup or clear failure");
    e=fresh(); route_error=-EPROTO;
    assert(finish_session(&e)==-EPROTO);
    assert(e.faulted && mute_restored && !route_restored && !resets);
    puts("PASS: failed routing restoration prevents a fresh session");
    e=fresh(); drain_ok=0;
    assert(finish_session(&e)==-EBUSY);
    assert(!strcmp(events,"DMR"));
    assert(e.quarantined && e.faulted && e.configured);
    assert(pins==1 && refs==1 && !writes && mute_restored && route_restored);
    assert(finish_session(&e)==-EBUSY);
    assert(pins==1 && refs==1 && !writes && !strcmp(events,"DMR"));
    puts("PASS: failed PCI drain pins memory owner/module once, does not restore DMA addresses");
    e=fresh(); e.running=false; e.configured=false; e.prepared=false;
    assert(finish_session(&e)==0); /* Route/mute failed before setup_dma. */
    assert(!strcmp(events,"MR") && !writes && stops==0 && resets==1);
    puts("PASS: partial prepare cleans the peripheral without touching DMA");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='native-alsa-lifecycle-') as d:
    p=Path(d)
    (p/'test.c').write_text(prefix+cleanup+suffix)
    subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-O2',
                    '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                    str(p/'test.c'),'-o',str(p/'test')],check=True)
    # LeakSanitizer cannot inspect threads under the tool's ptrace sandbox.
    # This harness allocates no heap memory; keep ASan bounds/UB checks active.
    subprocess.run([str(p/'test')],check=True,
                   env={**os.environ, 'ASAN_OPTIONS':'detect_leaks=0'})
