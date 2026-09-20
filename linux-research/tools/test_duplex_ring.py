#!/usr/bin/env python3
"""Actual duplex TX helper: join timing, independent wraps, drain, backpressure."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
SRC=r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "native_duplex_ring.h"
int main(void) {
    unsigned char *tx=calloc(ND_TX,256),pcm[ND_ALSA*6];
    struct nd_play p={0},saved;unsigned long long q=0,consumed=0;unsigned i,k;
    assert(tx);for(i=0;i<sizeof(pcm);i++)pcm[i]=(unsigned char)(i*13+7);
    assert(!nd_refill(&p,tx,NULL,&q,0,0,0));assert(q==4096);
    for(i=0;i<4096*256;i++)assert(!tx[i]);
    /* Playback joins a running silent capture engine. No pointer advance
     * may be reported while the previously offered silence is consumed. */
    p.base=q;assert(!nd_ack(&p,4096,32768));
    for(consumed=137;consumed<4096;consumed+=137) {
        assert(!nd_position(&p,consumed));assert(!p.played);
        assert(!nd_refill(&p,tx,pcm,&q,consumed,1,0));
    }
    for(i=0;i<20000;i++) {
        unsigned long long previous=p.played;
        assert(!nd_position(&p,consumed));
        if(p.played!=previous) assert(!nd_ack(&p,(p.appl+p.played-previous)%32768,32768));
        assert(!nd_refill(&p,tx,pcm,&q,consumed,1,0));
        assert(q==p.base+p.submitted);assert(p.accepted-p.played==4096);
        for(k=0;k<32;k++) {
            unsigned long long index=consumed+k;
            unsigned char *frame=tx+(index%8192)*256;
            assert(!memcmp(frame+4,pcm+((index-p.base)%4096)*6,6));
            assert(frame[0]==0&&frame[10]==0&&frame[255]==0);
        }
        consumed+=137;
    }
    saved=p;assert(nd_ack(&p,(p.appl+1)%32768,32768)==-EPIPE);assert(!memcmp(&p,&saved,sizeof(p)));
    assert(nd_ack(&p,0,123)==-EINVAL);
    /* EOF: publish silence after the last sample, clamp ALSA pointer. */
    consumed=q;assert(!nd_position(&p,consumed));assert(p.played==p.accepted);
    assert(!nd_refill(&p,tx,pcm,&q,consumed,1,1));
    assert(!nd_position(&p,consumed+800));assert(p.played==p.accepted);
    assert(!nd_ack(&p,(p.appl+1)%32768,32768));
    assert(nd_refill(&p,tx,pcm,&q,consumed+800,1,1)==-EPIPE);
    assert(nd_refill(&p,tx,pcm,&q,q+1,0,0)==-EPIPE);
    /* Fresh playback-only stream, no lead or missing initial samples. */
    memset(&p,0,sizeof(p));q=0;
    assert(!nd_ack(&p,4096,32768));assert(!nd_refill(&p,tx,pcm,&q,0,1,0));
    assert(q==4096&&p.submitted==4096);
    assert(!nd_position(&p,1024)&&p.played==1024);
    free(tx);puts("PASS duplex TX: capture-first lead, >2.7M frames, wraps, content, drain, invalid advances, playback-first");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'t.c').write_text(SRC)
 subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(ROOT/'kernel'),str(p/'t.c'),'-o',str(p/'t')],check=True)
 import os
 subprocess.run([str(p/'t')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
