#!/usr/bin/env python3
"""Fault-inject actual idle-DMA guards/setup/readback and restore six old addresses."""
from pathlib import Path
import ast,os,re,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'kernel/avid_native_adat.c').read_text()
def function(name):
    m=re.search(r'static (?:int|void) '+name+r'\([^\n]+\)\n\{',s)
    assert m,name
    start=m.start();p=s.index('{',m.start());depth=1;i=p+1
    while depth:
        depth+=(s[i]=='{')-(s[i]=='}');i+=1
    return s[start:i]+'\n'
offsets=s[s.index('static const u32 saved_offsets[]'):s.index('struct native_alsa {')]
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;typedef uint16_t u16;
#define CTL 0x10
#define RESET 0x20
#define DMA_CTL 0x42004
#define DL_CTL 0x70000
#define DL_STATUS 0x70004
#define DL_IRQ_MASK 0x70018
#define DMA_ENABLE 0x400040
#define CORE_ENABLE 0x10f0000
#define STREAM_ENABLE 0x400
#define PCI_COMMAND 4
#define PCI_COMMAND_MASTER 4
#define lower_32_bits(x) ((u32)(x))
#define upper_32_bits(x) ((u32)((uint64_t)(x)>>32))
#define dev_info(...) do {} while(0)
struct native_alsa { void *pdev; uint64_t rx_dma,tx_dma,status_dma; };
static bool allow_idle_dma;
static u32 mmio[0x71000/4];
static u16 command;
static int config_error, pending_ok, writes, wait_calls;
static unsigned drop, mutate, sleeps;
static u32 rd(struct native_alsa *e,unsigned off){(void)e;return mmio[off/4];}
static void wr(struct native_alsa *e,unsigned off,u32 v){(void)e;assert(!(command&4));writes++;if(off!=drop)mmio[off/4]=v;}
static void flush(struct native_alsa *e){(void)e;}
static void usleep_range(int a,int b){(void)a;(void)b;sleeps++;if(mutate)mmio[mutate/4]^=0x100;}
static int pci_read_config_word(void *p,int reg,u16 *v){(void)p;assert(reg==4);*v=command;return config_error;}
static int pci_wait_for_pending_transaction(void *p){(void)p;wait_calls++;return pending_ok;}
static void reset(void){
 memset(mmio,0,sizeof(mmio));mmio[0]=0xd400;mmio[1]=0x01050040;mmio[CTL/4]=0xa00;mmio[DL_STATUS/4]=0x9e180101;
 command=0x102;config_error=0;pending_ok=1;writes=wait_calls=sleeps=0;drop=mutate=0;allow_idle_dma=false;
}
static void residual(void){mmio[0x40918/4]=0x79062000;mmio[0x41118/4]=0x78e60000;mmio[0x4093c/4]=0x79464000;}
'''
suffix=r'''
int main(void){
 struct native_alsa e={.rx_dma=0x100000,.tx_dma=0x600000,.status_dma=0x900000};
 reset();assert(quiet_state(&e)==0 && writes==0);
 residual();assert(quiet_state(&e)==-EBUSY && writes==0);
 allow_idle_dma=true;assert(quiet_state(&e)==0 && writes==0);
 unsigned active[]={CTL,RESET,DL_CTL,DMA_CTL,DL_IRQ_MASK,0x42008};
 for(unsigned i=0;i<6;i++){reset();residual();allow_idle_dma=true;mmio[active[i]/4]^=1;assert(quiet_state(&e)==-EBUSY && writes==0);}
 reset();residual();allow_idle_dma=true;command|=4;assert(quiet_state(&e)==-EBUSY && !wait_calls && !writes);
 reset();residual();allow_idle_dma=true;pending_ok=0;assert(quiet_state(&e)==-EBUSY && !writes);
 reset();residual();allow_idle_dma=true;config_error=1;assert(quiet_state(&e)==-EIO && !writes);
 reset();residual();allow_idle_dma=true;mutate=0x40918;assert(quiet_state(&e)==-EBUSY && !writes);
 reset();residual();allow_idle_dma=true;mmio[0x40958/4]=1;assert(quiet_state(&e)==-EBUSY && !writes);
 reset();residual();allow_idle_dma=true;mmio[0x40918/4]|=1;assert(quiet_state(&e)==-EBUSY && !writes);
 reset();residual();allow_idle_dma=true;mmio[0x41118/4]=0;assert(quiet_state(&e)==-EBUSY && !writes);
 reset();residual();allow_idle_dma=true;assert(quiet_state(&e)==0);setup_dma(&e);assert(verify_dma_buffers(&e)==0 && !(command&4));
 for(unsigned i=7;i<=12;i++){
   reset();residual();allow_idle_dma=true;
   /* High words begin at zero, inject stale high value to simulate bad programming. */
   mmio[saved_offsets[i]/4]=0xdeadbe00;drop=saved_offsets[i];setup_dma(&e);
   assert(verify_dma_buffers(&e)==-EIO && !(command&4));
 }
 reset();setup_dma(&e);command|=4;assert(verify_dma_buffers(&e)==-EBUSY);
 reset();setup_dma(&e);mmio[DMA_CTL/4]|=DMA_ENABLE;assert(verify_dma_buffers(&e)==-EBUSY);
 puts("PASS: opt-in only, idle/stable/PCI guards, pending refusal, all six DMA addresses replaced and verified before enabling master");
 return 0;
}
'''
# Verify structural integration: the tested guard is called before the existing
# setup completion and before the sole bus-master enable in the START path.
trigger=s[s.index('static int native_trigger('):s.index('static snd_pcm_uframes_t native_pointer')]
assert trigger.index('verify_dma_buffers(e)')<trigger.index('pci_set_master(e->pdev)')
assert s.count('pci_set_master(e->pdev)')==1
prepare=s[s.index('static int native_prepare('):s.index('static int native_ack(')]
assert prepare.index('quiet_state(e)')<prepare.index('setup_dma(e)')<prepare.index('verify_dma_buffers(e)')<prepare.index('e->prepared = true')
with tempfile.TemporaryDirectory(prefix='adat-idle-dma-') as tmp:
 p=Path(tmp)
 def run(name,source):
  (p/(name+'.c')).write_text(source)
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p/(name+'.c')),'-o',str(p/name)],check=True)
  subprocess.run([str(p/name)],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
 run('handoff',prefix+offsets+function('setup_dma')+function('quiet_state')+function('verify_dma_buffers')+suffix)
 # Reuse the cleanup fault harness with the actual six residual DMA registers.
 tree=ast.parse((root/'tools/test_adat_lifecycle.py').read_text());literals={}
 for node in tree.body:
  if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('prefix','suffix'):
   literals[node.targets[0].id]=ast.literal_eval(node.value)
 pre=literals['prefix'].replace('{0x10,0x20,0x42004}', '{0x40918,0x40958,0x41118,0x41158,0x4093c,0x4097c}').replace('unsigned saved[3]','unsigned saved[6]').replace('2-writes','5-writes').replace('.saved={10,20,30}', '.saved={0x79062000,0,0x78e60000,0,0x79464000,0}')
 post=literals['suffix'].replace('writes==3','writes==6')
 cleanup=s[s.index('static int finish_session('):s.index('static const struct snd_pcm_hardware')]
 run('restore',pre+cleanup+post)
 print('PASS: original six residual address values restored in reverse order after drain; lost ACK and drain failure tests preserved')
