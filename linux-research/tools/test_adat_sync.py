#!/usr/bin/env python3
"""Fault-inject control1 A/B experiment, using the actual peripheral helper."""
from pathlib import Path
import subprocess,tempfile
from adat_result import passed
root=Path(__file__).resolve().parents[1]
source=r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "native_192_adat_control.h"
struct sim {unsigned tx,rx,regs[256],saved[256],writes,fault; unsigned long long time;};
static unsigned rd(void*p,unsigned off){struct sim*s=p;return off==0x7001c?s->tx:s->rx;}
static void wr(void*p,unsigned off,unsigned cmd){
 struct sim*s=p;assert(off==0x7001c);s->tx=cmd;if(!cmd){s->rx=0;return;}
 unsigned reg=(cmd>>8)&255,v=cmd&255;
 if(cmd&0x800000){
  assert((reg==0&&(v==0||v==2))||(reg==1&&(v==0||v==128))||
         (reg==0x41&&(v==0||v==17))||(reg==0x51&&v<=1));
  if(reg==1) assert(s->regs[0]==2); /* no clock-role transition while unmuted */
  if(reg==0&&v==0) assert(s->regs[1]==128);
  s->writes++;
  if(!(reg==1&&((s->fault==2&&v)||(s->fault==3&&!v))))s->regs[reg]=v;
  if(reg==1&&v&&s->fault==1)return; /* lost ACK after applying */
  s->rx=cmd&0xffff00;
 }else s->rx=cmd|s->regs[reg];
}
static unsigned long long now(void*p){return ((struct sim*)p)->time;}
static void pause_sim(void*p){((struct sim*)p)->time+=100;}
static void init(struct sim*s,struct native_192*n){
 memset(s,0,sizeof(*s));s->regs[0]=2;s->regs[0x10]=1;s->regs[0x11]=0x49;s->regs[0x12]=s->regs[0x13]=1;
 s->regs[0x14]=0x14;s->regs[0x15]=0x13;s->regs[0x16]=0x15;s->regs[0x17]=0x13;
 memcpy(s->saved,s->regs,sizeof(s->regs));
 *n=(struct native_192){.ctx=s,.read=rd,.write=wr,.now_us=now,.pause=pause_sim,
 .sync_profile=1,.optical_path=2,.input_pair=1,.output_pair=1,.route_enabled=1,
 .before=-1,.route_before=-1,.sync_before=-1};
}
int main(void){
 struct sim s;struct native_192 n;
 init(&s,&n);assert(!n192_route_enable(&n));assert(!n192_unmute(&n));
 assert(s.regs[1]==128&&n.sync_active&&n.sync_restore_required);
 assert(!n192_check_route(&n,1,&n.route_during));
 assert(!n192_restore(&n)&&!n192_route_restore(&n)&&!n192_sync_restore(&n));
 assert(n.sync_restored&&!n.sync_restore_required&&!n.sync_active);
 assert(!memcmp(s.saved,s.regs,sizeof(s.regs)));unsigned count=s.writes;
 assert(!n192_sync_restore(&n)&&s.writes==count);
 for(unsigned fault=1;fault<=3;fault++){
  init(&s,&n);s.fault=fault;assert(!n192_route_enable(&n));
  int ret=n192_unmute(&n);
  if(fault<3){assert(ret&&s.regs[0]==2&&!n.write_attempted);}
  else assert(!ret);
  assert(n.sync_restore_required&&n.sync_write_attempted);
  assert(!n192_restore(&n)&&!n192_route_restore(&n));
  ret=n192_sync_restore(&n);
  if(fault==3)assert(ret&&!n.sync_restored&&n.sync_restore_required);
  else assert(!ret&&n.sync_restored&&!memcmp(s.saved,s.regs,sizeof(s.regs)));
 }
 init(&s,&n);assert(!n192_route_enable(&n)&&!n192_unmute(&n));
 unsigned before=s.writes;
 assert(n192_sync_restore(&n)==-EPROTO&&s.writes==before&&n.sync_restore_required);
 assert(!n192_restore(&n)&&!n192_route_restore(&n)&&!n192_sync_restore(&n));
 for(unsigned reg=0;reg<256;reg++)for(unsigned v=0;v<256;v++){
  int allowed=(reg==0&&(v==0||v==2))||(reg==1&&(v==0||v==128))||
     (reg==0x41&&(v==0||v==17))||(reg==0x51&&v<=1);
  if(!allowed){init(&s,&n);unsigned value=v;assert(n192_xfer(&n,reg,1,&value)==-EINVAL&&!s.writes);}
 }
 for(unsigned reg=0;reg<=3;reg++){
  init(&s,&n);s.regs[reg]^=1;assert(n192_route_enable(&n)==-EPROTO&&!s.writes);
 }
 for(unsigned reg=0x40;reg<=0x5d;reg++){
  init(&s,&n);s.regs[reg]=1;assert(n192_route_enable(&n)==-EPROTO&&!s.writes);
 }
 for(unsigned k=0;k<4;k++){
  init(&s,&n);if(k==0)n.windows_state=1;if(k==1)n.module_route=1;
  if(k==2)n.optical_path=1;
  if(k==3)n.input_pair=2;
  assert(n192_route_enable(&n)==-EINVAL&&!s.writes);
 }
 init(&s,&n);n.sync_profile=0;unsigned v=128;
 assert(n192_xfer(&n,1,1,&v)==-EINVAL&&!s.writes);
 init(&s,&n);s.tx=123;assert(n192_route_enable(&n)==-EBUSY&&!s.writes);
 puts("PASS: control1 bit7 allowlist; exact muted baseline; ACK loss, ignored writes, rollback failure; no unmute on failure; original profile restored");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(source)
 subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(root/'kernel'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
p={'sync_profile':True,'optical_path':'module','input_pair':1,'output_pair':1,'expectation':'loopback','input_selector':17,'output_register':'0x51'}
a={'expectation_met':True,'expectation':'loopback','input_pair':1,'optical_path':'module','frames':480000,'rate':48000,'format':'S24_3LE'}
s={'starts':'1','stops':'1','xruns':'0','last_error':'0','mute_restored':'Y','route_restored':'Y','sync_restored':'Y'}
assert passed(p,a,s,0,True,True,True)
for value in ('N',None): assert not passed(p,a,{**s,'sync_restored':value},0,True,True,True)
for k,v in [('input_pair',2),('output_pair',2),('windows_state',True),('allow_idle_dma',True),('module_route',True),('optical_path','enclosure')]:
 assert not passed({**p,k:v},a,s,0,True,True,True)
print('PASS: sync profile acceptance requires rollback and bounded profile')
