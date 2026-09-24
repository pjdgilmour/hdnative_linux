#!/usr/bin/env python3
"""Actual two-route warm module helper: fault injection, restore and allowlist."""
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
struct sim{unsigned tx,rx,regs[256],saved[256],writes,fault,reg,inp,out;unsigned long long time;};
static unsigned rd(void*p,unsigned off){struct sim*s=p;return off==0x7001c?s->tx:s->rx;}
static void wr(void*p,unsigned off,unsigned cmd){
 struct sim*s=p;assert(off==0x7001c);s->tx=cmd;if(!cmd){s->rx=0;return;}
 unsigned reg=(cmd>>8)&255,v=cmd&255;
 if(cmd&0x800000){
  assert((reg==0x44+s->inp&&(v==16+s->inp||v==24+s->inp))||
         (reg==0x50+s->out&&(v==0||v==4+s->out)));
  s->writes++;
  int enabling=(reg==0x44+s->inp?v==16+s->inp:v!=0);
  if(!(reg==s->reg&&((s->fault==2&&enabling)||(s->fault==3&&!enabling))))s->regs[reg]=v;
  if(reg==s->reg&&s->fault==1&&enabling)return; /* applied with lost ACK */
  s->rx=cmd&0xffff00;
 }else s->rx=cmd|s->regs[reg];
}
static unsigned long long now(void*p){return ((struct sim*)p)->time;}
static void pause_sim(void*p){((struct sim*)p)->time+=100;}
static void init(struct sim*s,struct native_192*n,unsigned inp,unsigned out){
 memset(s,0,sizeof(*s));s->inp=inp;s->out=out;
 s->regs[1]=0x80;s->regs[0x10]=1;s->regs[0x11]=0x49;s->regs[0x12]=1;s->regs[0x13]=1;
 s->regs[0x14]=0x14;s->regs[0x15]=0x13;s->regs[0x16]=0x15;s->regs[0x17]=0x13;
 unsigned routes[30]={0,9,10,11,12,25,26,27,28,0,0,0,0,1,2,3,4,0,0,0,0,0,0,0,0,5,6,7,8,1};
 for(unsigned i=0;i<30;i++)s->regs[0x40+i]=routes[i];memcpy(s->saved,s->regs,sizeof(s->regs));
 *n=(struct native_192){.ctx=s,.read=rd,.write=wr,.now_us=now,.pause=pause_sim,
 .windows_state=1,.module_route=1,.optical_path=2,.input_pair=inp,.output_pair=out,
 .route_enabled=1,.before=-1,.route_before=-1};
}
int main(void){
 struct sim s;struct native_192 n;
 for(unsigned inp=1;inp<=4;inp++)for(unsigned out=1;out<=4;out++){
  init(&s,&n,inp,out);assert(!n192_route_enable(&n));assert(s.writes==2&&n.route_before==0);
  assert(s.regs[0x44+inp]==16+inp&&s.regs[0x50+out]==4+out);
  assert(!n192_unmute(&n)&&!n192_check_route(&n,1,&n.route_during));assert(s.writes==2);
  assert(!n192_restore(&n)&&!n192_route_restore(&n));assert(s.writes==4);
  assert(!memcmp(s.saved,s.regs,sizeof(s.regs))&&n.restored&&n.route_restored);
  assert(!n192_route_restore(&n)&&s.writes==4);
  for(unsigned which=0;which<2;which++)for(unsigned fault=1;fault<=3;fault++){
   init(&s,&n,inp,out);s.reg=which?0x50+out:0x44+inp;s.fault=fault;
   if(fault==3){
    assert(!n192_route_enable(&n));assert(n192_route_restore(&n));
    assert(n.route_restore_required&&!n.route_restored);
   }else{
    assert(n192_route_enable(&n));assert(n.route_restore_required);
    assert(!n192_route_restore(&n));assert(!memcmp(s.saved,s.regs,sizeof(s.regs)));
   }
  }
  init(&s,&n,inp,out);
  for(unsigned reg=0;reg<256;reg++)for(unsigned v=0;v<256;v++){
   int allowed=(reg==0x44+inp&&(v==16+inp||v==24+inp))||(reg==0x50+out&&(v==0||v==4+out));
   if(!allowed){unsigned value=v;assert(n192_xfer(&n,reg,1,&value)==-EINVAL);assert(!s.writes);}
  }
  for(unsigned reg=0x40;reg<=0x5d;reg++){
   init(&s,&n,inp,out);s.regs[reg]^=1;assert(n192_route_enable(&n)==-EPROTO);assert(!s.writes);
  }
 }
 init(&s,&n,1,1);s.regs[0x12]=3;assert(n192_route_enable(&n)==-EPROTO&&!s.writes);
 init(&s,&n,1,1);n.windows_state=0;assert(n192_route_enable(&n)==-EINVAL&&!s.writes);
 init(&s,&n,1,1);n.optical_path=1;assert(n192_route_enable(&n)==-EINVAL&&!s.writes);
 init(&s,&n,1,1);s.tx=123;assert(n192_route_enable(&n)==-EBUSY&&!s.writes);
 puts("PASS: 16 warm module profiles, exact base/active route tables, only 2 allowed routes, no control writes, ACK loss/ignored writes/failed restoration, invalid state refused");
 return 0;
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(source)
 subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(root/'kernel'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
p={'optical_path':'module','windows_state':True,'module_route':True,'input_pair':1,'output_pair':1,'transport_channels':[9,10],'output_transport_channels':[9,10],'input_register':'0x45','output_selector':5,'allow_idle_dma':True,'input_selector':17,'output_register':'0x51','expectation':'loopback'}
a={'expectation_met':True,'expectation':'loopback','input_pair':1,'optical_path':'module','frames':480000,'rate':48000,'format':'S24_3LE'}
s={'starts':'1','stops':'1','xruns':'0','last_error':'0','mute_restored':'Y','route_restored':'Y'}
assert passed(p,a,s,0,True,True,True)
for k,v in [('module_route',False),('windows_state',False),('optical_path','enclosure'),('input_selector',25),('route_restored','N')]:
 if k=='route_restored':assert not passed(p,a,{**s,k:v},0,True,True,True)
 else:assert not passed({**p,k:v},a,s,0,True,True,True)
print('PASS: module-route acceptance requires consistent profile and restoration')
