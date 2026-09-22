#!/usr/bin/env python3
"""Actual Windows control guard and independent logical 9-16 TX/RX mapping; no hardware."""
from pathlib import Path
import subprocess,tempfile,os
from adat_result import passed
root=Path(__file__).resolve().parents[1]
driver=(root/'kernel/avid_native_adat.c').read_text()
selectors='\n'.join(line for line in driver.splitlines() if line.startswith(('#define NC_RX_OFFSET ', '#define NC_TX_OFFSET ')))
assert len(selectors.splitlines())==2
source=r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "native_192_adat_control.h"
#define native_capture_ring ref_capture_ring
#define nc_ack ref_ack
#define nc_pull ref_pull
#define nc_tx_fill ref_tx_fill
#include "native_capture_ring.h"
#undef native_capture_ring
#undef nc_ack
#undef nc_pull
#undef nc_tx_fill
static unsigned windows_state, input_pair, output_pair;
ACTUAL_DRIVER_SELECTORS
#include "native_adat_ring.h"
struct sim {unsigned tx,rx,regs[256],badreg,reads;unsigned long long time;};
static unsigned rd(void *p,unsigned off){struct sim*s=p;return off==0x7001c?s->tx:s->rx;}
static void wr(void *p,unsigned off,unsigned cmd){
 struct sim*s=p;assert(off==0x7001c);assert(!(cmd&0x800000));
 s->tx=cmd;if(!cmd){s->rx=0;return;}
 unsigned reg=(cmd>>8)&255; s->reads++;
 assert(reg<=3||(reg>=0x10&&reg<=0x17)||(reg>=0x40&&reg<=0x5d));
 s->rx=cmd | (s->regs[reg] ^ (reg==s->badreg?1:0));
}
static unsigned long long now(void*p){return ((struct sim*)p)->time;}
static void pause_sim(void*p){((struct sim*)p)->time+=100;}
static void init(struct sim*s,struct native_192*n){
 memset(s,0,sizeof(*s));s->badreg=256;
 s->regs[0]=0;s->regs[1]=0x80;s->regs[0x10]=1;s->regs[0x11]=0x49;s->regs[0x12]=3;s->regs[0x13]=1;
 s->regs[0x14]=0x14;s->regs[0x15]=0x13;s->regs[0x16]=0x15;s->regs[0x17]=0x13;
 unsigned routes[30]={0,9,10,11,12,25,26,27,28,0,0,0,0,1,2,3,4,0,0,0,0,0,0,0,0,5,6,7,8,1};
 for(unsigned i=0;i<30;i++)s->regs[0x40+i]=routes[i];
 *n=(struct native_192){.ctx=s,.read=rd,.write=wr,.now_us=now,.pause=pause_sim,
 .windows_state=1,.input_pair=1,.output_pair=1,.optical_path=1,.route_enabled=1,.before=-1,.route_before=-1};
}
static void controls(void){
 struct sim s;struct native_192 n;init(&s,&n);unsigned saved[256];memcpy(saved,s.regs,sizeof(saved));
 assert(!n192_preflight(&n));assert(n.before==0&&n.route_before==5);
 assert(!n192_route_enable(&n));assert(!n192_unmute(&n));assert(!n192_check_unmuted(&n));
 assert(!n192_check_route(&n,1,&n.route_during));assert(n.route_during==5);
 assert(!n192_restore(&n));assert(!n192_route_restore(&n));assert(n.after==0&&n.route_after==5);
 assert(n.restored&&n.route_restored&&!n.restore_required&&!n.route_restore_required);
 assert(!n.write_attempted&&!n.route_write_attempted&&!memcmp(saved,s.regs,sizeof(saved)));
 for(unsigned reg=0;reg<256;reg++)for(unsigned v=0;v<256;v++){
   unsigned value=v;unsigned reads=s.reads;
   assert(n192_xfer(&n,reg,1,&value)==-EINVAL);assert(s.reads==reads);
 }
 unsigned regs[]={0,1,2,3,0x10,0x11,0x12,0x13,0x14,0x15,0x16,0x17};
 for(unsigned i=0;i<sizeof(regs)/sizeof(regs[0]);i++){
   init(&s,&n);s.badreg=regs[i];assert(n192_preflight(&n)==-EPROTO);assert(n.check_reg==regs[i]);
 }
 for(unsigned reg=0x40;reg<=0x5d;reg++){
   init(&s,&n);s.badreg=reg;assert(n192_preflight(&n)==-EPROTO);
   assert(n192_route_restore(&n)==-EPROTO&&n.route_restore_required&&!n.route_restored);
 }
 init(&s,&n);assert(!n192_preflight(&n));s.regs[1]=0;
 assert(n192_restore(&n)==-EPROTO&&n.restore_required&&!n.restored);
 for(unsigned inp=1;inp<=4;inp++)for(unsigned out=1;out<=4;out++){
  init(&s,&n);n.input_pair=inp;n.output_pair=out;
  assert(!n192_preflight(&n)&&n.route_before==(int)(4+out));
  assert(!n192_route_enable(&n)&&n.route_during==(int)(4+out));
  assert(!n192_unmute(&n));assert(!n192_restore(&n));
  assert(!n192_route_restore(&n)&&n.route_after==(int)(4+out));
  for(unsigned reg=0;reg<256;reg++)for(unsigned v=0;v<256;v++){
   unsigned value=v;assert(n192_xfer(&n,reg,1,&value)==-EINVAL);
  }
 }
 for(unsigned invalid=0;invalid<=5;invalid+=5){
  init(&s,&n);n.input_pair=invalid;assert(n192_preflight(&n)==-EINVAL);
  init(&s,&n);n.output_pair=invalid;assert(n192_preflight(&n)==-EINVAL);
 }
 init(&s,&n);n.optical_path=2;assert(n192_preflight(&n)==-EINVAL);
 puts("PASS: exact Windows state, all 65536 peripheral writes forbidden, each state/route mismatch rejected, cleanup verifies preservation");
}
static void geometry(void){
 const unsigned expected[64]={
  4,7,10,13,16,19,22,25,36,39,42,45,48,51,54,57,
  68,71,74,77,80,83,86,89,100,103,106,109,112,115,118,121,
  132,135,138,141,144,147,150,153,164,167,170,173,176,179,182,185,
  196,199,202,205,208,211,214,217,228,231,234,237,240,243,246,249
 };
 for(unsigned ch=0;ch<64;ch++)assert(NC_CHANNEL_OFFSET(ch)==expected[ch]);
 unsigned char *rx=calloc(NC_RX_FRAMES,256),pcm[NC_ALSA_FRAMES*6]={0};
 assert(rx);windows_state=1;input_pair=output_pair=1;
 /* Non-PCM metadata at the exact position wrongly used in E1eorI. */
 const unsigned char metadata[6]={0,0,0x80,0,0x7f,0x3a};
 const unsigned char samples[6]={0xae,0x47,1,0x52,0xb8,0xfe};
 memcpy(rx+28,metadata,6);memcpy(rx+36,samples,6);
 struct native_capture_ring ring={0};
 assert(nc_pull(&ring,rx,pcm,1)==1);
 assert(!memcmp(pcm,samples,6));assert(memcmp(pcm,metadata,6));
 assert(memcmp(rx+28,samples,6)); /* The previous extractor fails this fixture. */
 free(rx);
 puts("PASS: independent 64-channel group table; channel 8/9 boundary; metadata at 28 rejected, PCM at 36 extracted");
}
static void packets(void){
 unsigned char *tx=calloc(NC_TX_FRAMES,256),*ref=calloc(NC_TX_FRAMES,256),*rx=calloc(NC_RX_FRAMES,256),*pcm=calloc(NC_ALSA_FRAMES,6);
 assert(tx&&ref&&rx&&pcm);
 unsigned starts[]={0,48000,96000,191999,335997,427888};
 const unsigned offsets[4]={36,42,48,54}; /* independent fixture positions */
 for(unsigned profile=0;profile<17;profile++){
  windows_state=profile!=0;
  input_pair=profile?1+(profile-1)/4:1;
  output_pair=profile?1+(profile-1)%4:1;
  const unsigned rx_offset=profile?offsets[input_pair-1]:4;
  const unsigned tx_offset=profile?offsets[output_pair-1]:4;
  assert(NC_RX_OFFSET==rx_offset);assert(NC_TX_OFFSET==tx_offset);
  for(unsigned j=0;j<sizeof(starts)/sizeof(starts[0]);j++){
   nc_tx_fill(tx,starts[j],NC_TX_FRAMES,1);ref_tx_fill(ref,starts[j],NC_TX_FRAMES,1);
   for(unsigned i=0;i<NC_TX_FRAMES;i++){
    assert(!memcmp(tx+i*256+tx_offset,ref+i*256+4,6));
    for(unsigned k=0;k<256;k++)if(k<tx_offset||k>=tx_offset+6)assert(tx[i*256+k]==0);
   }
  }
  struct native_capture_ring ring={0};
  for(unsigned batch=0;batch<2000;batch++){
   unsigned old=ring.hw;
   for(unsigned i=0;i<1024;i++){
    unsigned frame=(old+i)%NC_RX_FRAMES;
    memset(rx+frame*256,0xa5,256);
    for(unsigned k=0;k<6;k++)rx[frame*256+rx_offset+k]=(batch+i+k)&255;
   }
   assert(nc_pull(&ring,rx,pcm,(old+1024)%NC_RX_FRAMES)==1024);
   for(unsigned i=0;i<1024;i++)for(unsigned k=0;k<6;k++)
    assert(pcm[((ring.produced-1024+i)%NC_ALSA_FRAMES)*6+k]==((batch+i+k)&255));
   assert(!nc_ack(&ring,ring.produced%16384,16384));
  }
 }
 free(tx);free(ref);free(rx);free(pcm);
 puts("PASS: all 16 independent ADAT TX/RX pair combinations and legacy, offsets 4/36/42/48/54, other TX channels zero, 34.816M RX frames with wraps");
}
int main(void){controls();geometry();packets();return 0;}
'''
with tempfile.TemporaryDirectory(prefix='adat-windows-') as tmp:
 p=Path(tmp);(p/'test.c').write_text(source.replace('ACTUAL_DRIVER_SELECTORS',selectors))
 subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(root/'kernel'),str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
profile={'windows_state':True,'allow_idle_dma':True,'transport_channels':[9,10],'output_transport_channels':[9,10],'input_register':'0x45','output_selector':5,'optical_path':'enclosure','input_pair':1,'output_pair':1,'input_selector':25,'output_register':'0x59','expectation':'loopback'}
analysis={'expectation_met':True,'expectation':'loopback','input_pair':1,'optical_path':'enclosure','frames':480000,'rate':48000,'format':'S24_3LE'}
stats={'starts':'1','stops':'1','xruns':'0','last_error':'0','mute_restored':'Y','route_restored':'Y'}
assert passed(profile,analysis,stats,0,True,True,True)
for key,value in [('input_register','0x41'),('output_selector',1),('transport_channels',[1,2]),('allow_idle_dma',False),('optical_path','module')]:
 assert not passed({**profile,key:value},analysis,stats,0,True,True,True)
print('PASS: acceptance rejects inconsistent Windows-profile transport mapping')

for inp in range(1,5):
 for out in range(1,5):
  mode='loopback' if inp==out else 'isolation'
  candidate={**profile,'input_pair':inp,'output_pair':out,'transport_channels':[7+2*inp,8+2*inp],
     'output_transport_channels':[7+2*out,8+2*out], 'input_register':hex(0x44+inp),
     'output_selector':4+out,'input_selector':24+inp,'output_register':hex(0x58+out),'expectation':mode}
  result={**analysis,'input_pair':inp,'expectation':mode}
  assert passed(candidate,result,stats,0,True,True,True)
  for key,value in [('transport_channels',[1,2]),('output_transport_channels',[1,2]),
                    ('input_register','0x41'),('output_selector',1)]:
   assert not passed({**candidate,key:value},result,stats,0,True,True,True)
print('PASS: all 16 pair profiles including asymmetric isolation; TX/RX mapping errors rejected')
