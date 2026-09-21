#!/usr/bin/env python3
"""Compile and exercise the actual capture helpers, no hardware access."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "native_capture_ring.h"
#include "native_192_channelmap_control.h"
static unsigned input_pair=1,output_pair=1;
static unsigned output_reg(void){return output_pair<=4?0x4c+output_pair:0x50+output_pair;}
struct sim { unsigned tx,rx,regs[256],fault_reg,fault,off[256]; unsigned long long time; };
static unsigned rd(void *p,unsigned off) { struct sim *s=p; return off==0x7001c?s->tx:s->rx; }
static void wr(void *p,unsigned off,unsigned cmd) {
    struct sim *s=p; unsigned reg=(cmd>>8)&255,v=cmd&255;
    assert(off==0x7001c); s->tx=cmd;
    if(!cmd) {s->rx=0;return;}
    if(cmd&0x800000) {
        assert((reg==0&&(v==0||v==2))||(reg==0x41&&(v==0||v==8+input_pair))||(reg==output_reg()&&v<=1));
        if(reg!=0&&v) assert(s->regs[0]==2);
        if(reg!=0&&!v) s->off[reg]++;
        if(!(reg==s->fault_reg&&((s->fault==2&&v)||(s->fault==3&&!v)))) s->regs[reg]=v;
        if(reg==s->fault_reg&&s->fault==1&&v) return; /* applied, ACK lost */
        s->rx=cmd&0xffff00;
    } else s->rx=cmd|s->regs[reg];
}
static unsigned long long now(void *p) {return ((struct sim*)p)->time;}
static void pause_sim(void *p) {((struct sim*)p)->time+=100;}
static void init(struct sim *s,struct native_192 *n) {
    memset(s,0,sizeof(*s));
    s->regs[0]=2; s->regs[0x10]=1;s->regs[0x11]=0x49;s->regs[0x12]=s->regs[0x13]=1;
    s->regs[0x14]=0x14;s->regs[0x15]=0x13;s->regs[0x16]=0x15;s->regs[0x17]=0x13;
    *n=(struct native_192){.ctx=s,.read=rd,.write=wr,.now_us=now,.pause=pause_sim,.route_enabled=1,.input_pair=input_pair,.output_pair=output_pair,.before=-1,.route_before=-1};
}
static void controls(void) {
    struct sim s;struct native_192 n;unsigned reg,f,v;
    init(&s,&n);assert(!n192_route_enable(&n));assert(s.regs[0x41]==8+input_pair&&s.regs[output_reg()]==1);
    assert(!n192_unmute(&n));assert(!n192_restore(&n));assert(!n192_route_restore(&n));
    assert(s.regs[0]==2&&!s.regs[0x41]&&!s.regs[output_reg()]);
    for(unsigned which=0;which<2;which++) for(reg=which?output_reg():0x41;reg;reg=0) for(f=1;f<=3;f++) {
        init(&s,&n);s.fault_reg=reg;s.fault=f;
        if(f==3) {assert(!n192_route_enable(&n));assert(n192_route_restore(&n));assert(n.route_restore_required);assert(s.off[0x41]==3&&s.off[output_reg()]==3);}
        else {assert(n192_route_enable(&n));assert(n.route_restore_required);assert(!n192_route_restore(&n));assert(!s.regs[0x41]&&!s.regs[output_reg()]);}
    }
    init(&s,&n);s.regs[0x42]=4;assert(n192_route_enable(&n));assert(!n.route_write_attempted);
    init(&s,&n);v=8;assert(n192_xfer(&n,0x41,1,&v)==-EINVAL);
    v=9;assert(n192_xfer(&n,0x42,1,&v)==-EINVAL);

}
static void rings(void) {
    unsigned char *rx=malloc(NC_RX_FRAMES*256),*pcm=malloc(NC_ALSA_FRAMES*6),*tx=malloc(NC_TX_FRAMES*256);
    struct native_capture_ring r={0},saved;unsigned i,j,hw=0;
    assert(rx&&pcm&&tx);memset(rx,0xa5,NC_RX_FRAMES*256);
    for(i=0;i<NC_RX_FRAMES;i++) for(j=0;j<6;j++) rx[i*256+4+j]=(unsigned char)(i+j*53);
    /* More than 2 million frames: ALSA and native wrap independently. */
    for(i=0;i<20000;i++) {
        unsigned k; unsigned long long before=r.produced;
        hw=(hw+137)%NC_RX_FRAMES;assert(nc_pull(&r,rx,pcm,hw)==137);
        for(k=0;k<137;k++) for(j=0;j<6;j++) assert(pcm[((before+k)%NC_ALSA_FRAMES)*6+j]==(unsigned char)(((before+k)%NC_RX_FRAMES)+j*53));
        assert(!nc_ack(&r,(unsigned long)(r.produced%32768),32768));
    }
    saved=r;assert(nc_pull(&r,rx,pcm,(r.hw+4096)%NC_RX_FRAMES)==-EPIPE);assert(!memcmp(&r,&saved,sizeof(r)));
    assert(nc_ack(&r,(r.appl+1)%32768,32768)==-EPIPE);
    assert(nc_ack(&r,0,123)==-EINVAL);
    assert(nc_pull(&r,rx,pcm,16384)==-EINVAL);
    for(i=0;i<480000;i+=2048) {
        unsigned k;
        nc_tx_fill(tx,i,2048,1);
        for(k=0;k<2048;k++) {
            unsigned t=(i+k)%480000,ch;unsigned char *p=tx+((i+k)%8192)*256;
            for(j=0;j<256;j++) if(j<4||j>9) assert(!p[j]);
            for(ch=0;ch<2;ch++) {
                unsigned b=ch?192000:48000;int v=p[4+ch*3]|p[5+ch*3]<<8|p[6+ch*3]<<16;
                if(v&0x800000) v-=0x1000000;
                assert(abs(v)<=83886);
                if(!((t>=b&&t<b+96000)||(t>=336000&&t<432000)))assert(!v);
            }
        }
    }
    nc_tx_fill(tx,48000,64,1);assert(tx[(48016%8192)*256+4]==(83886*16/480&255));
    nc_tx_fill(tx,48512,64,1); /* independently known +750 Hz peak */
    {unsigned char *p=tx+(48528%8192)*256+4;assert((p[0]|p[1]<<8|p[2]<<16)==83886);}
    nc_tx_fill(tx,0,8192,0);for(i=0;i<8192*256;i++)assert(!tx[i]);
    free(tx);free(pcm);free(rx);
    puts("PASS PCM: signed packed bytes, 2.74M frames, wraps, backpressure, invalid pointers, tone bounds, silence");
}
int main(void){
    for(input_pair=1;input_pair<=4;input_pair++)for(output_pair=1;output_pair<=8;output_pair++)controls();
    {struct sim s;struct native_192 n;unsigned v=0;
     init(&s,&n);n.input_pair=0;assert(n192_xfer(&n,0,1,&v)==-EINVAL);assert(!s.tx);
     n.input_pair=1;n.output_pair=9;assert(n192_route_enable(&n)==-EINVAL);assert(!s.tx);}
    puts("PASS 32 analog pair profiles: route allowlist, ACK loss, ignored writes, restoration failures, invalid selections");
    rings();return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
    p=Path(d); (p/'test.c').write_text(SOURCE)
    subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'kernel'),str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
