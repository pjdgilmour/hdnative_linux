#!/usr/bin/env python3
"""Exercise actual DigiLink idle handshake with delayed/unstable RX; no hardware."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
source=r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "native_192_adat_control.h"
struct sim {
 unsigned tx, phase, writes, commands, pauses;
 unsigned pre_busy, cleanup_busy, unstable, tx_after_pause, wrong_ack, frozen;
 unsigned long long time, epoch, command_time;
};
static unsigned rd(void *ctx,unsigned off){
 struct sim *s=ctx;
 if(off==0x7001c)return s->tx;
 assert(off==0x70040);
 if(s->phase==1)return s->wrong_ack?0x014000:0x014109;
 unsigned long long elapsed=s->time-s->epoch;
 if(s->phase==0){
  if(s->pre_busy==2)return 0x800000;
  if(s->unstable && elapsed==0)return 0;
  return s->pre_busy && elapsed<400?0x800000:0;
 }
 if(s->cleanup_busy==2)return 0x800000;
 /* A transient zero must not complete cleanup before the later busy header. */
 if(s->cleanup_busy==1)return elapsed>=100&&elapsed<400?0x800000:0;
 return 0;
}
static void wr(void *ctx,unsigned off,unsigned value){
 struct sim *s=ctx;assert(off==0x7001c);s->writes++;
 assert(!(value&0x800000)); /* no peripheral WRITE, even during failures */
 assert((value&0xff000000)==0xab000000); /* preserve TX upper byte */
 if(value&0xffffff){
  assert(!(s->tx&0xffffff));assert(!(rd(s,0x70040)&0xffff00));
  assert(value==0xab014100);s->commands++;s->command_time=s->time;
  s->phase=1;
 }else{s->phase=2;s->epoch=s->time;}
 s->tx=value;
}
static unsigned long long now(void *ctx){return ((struct sim*)ctx)->time;}
static void pause_sim(void *ctx){
 struct sim *s=ctx;s->pauses++;if(!s->frozen)s->time+=100;
 if(s->tx_after_pause)s->tx=0xab010100;
}
static void init(struct sim*s,struct native_192*n){
 memset(s,0,sizeof(*s));s->tx=0xab000000;
 *n=(struct native_192){.ctx=s,.read=rd,.write=wr,.now_us=now,.pause=pause_sim,
  .windows_state=1,.optical_path=1,.input_pair=1,.output_pair=1,.route_enabled=1};
}
int main(void){
 struct sim s;struct native_192 n;unsigned value;
 init(&s,&n);value=123;assert(!n192_xfer(&n,0x41,0,&value));
 assert(value==9&&s.commands==1&&s.writes==2&&s.time==200&&!n.idle_waits);
 init(&s,&n);s.pre_busy=1;value=123;assert(!n192_xfer(&n,0x41,0,&value));
 assert(s.command_time==500&&n.idle_waits==1&&value==9);
 init(&s,&n);s.pre_busy=1;s.unstable=1;value=123;assert(!n192_xfer(&n,0x41,0,&value));
 assert(s.command_time==500&&n.idle_waits==1);
 init(&s,&n);s.pre_busy=2;value=123;assert(n192_xfer(&n,0x41,0,&value)==-EBUSY);
 assert(!s.writes&&value==123&&s.time==100000&&n.idle_rx==0x800000);
 init(&s,&n);s.pre_busy=2;s.frozen=1;value=123;assert(n192_xfer(&n,0x41,0,&value)==-EBUSY);
 assert(!s.writes&&s.pauses<=2001); /* bound even if time source stalls */
 init(&s,&n);s.tx=0xab010100;value=123;assert(n192_xfer(&n,0x41,0,&value)==-EBUSY);
 assert(!s.writes&&!s.pauses&&s.tx==0xab010100);
 init(&s,&n);s.tx_after_pause=1;value=123;assert(n192_xfer(&n,0x41,0,&value)==-EBUSY);
 assert(!s.writes&&s.tx==0xab010100);
 init(&s,&n);s.cleanup_busy=1;value=123;assert(!n192_xfer(&n,0x41,0,&value));
 assert(s.time-s.epoch==500&&s.writes==2&&s.commands==1&&n.idle_waits==1);
 init(&s,&n);s.cleanup_busy=2;value=123;assert(n192_xfer(&n,0x41,0,&value)==-EIO);
 assert(s.writes==2&&s.time-s.epoch==100000&&n.idle_rx==0x800000);
 init(&s,&n);s.wrong_ack=1;value=123;assert(n192_xfer(&n,0x41,0,&value)==-ETIMEDOUT);
 assert(value==123&&s.writes==2&&s.commands==1); /* no blind retry */
 puts("PASS: delayed RX and transient zero settle; stuck RX/active TX refuse without writes; cleanup bounded; exact ACK required; no retries or peripheral writes");
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='adat-mailbox-') as d:
 p=Path(d);(p/'test.c').write_text(source)
 subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(root/'kernel'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
