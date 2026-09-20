#!/usr/bin/env python3
"""Run the actual trigger, poll and per-stream stop against simulated DMA."""
from pathlib import Path
import subprocess,tempfile,os
ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/'kernel/avid_native_duplex.c').read_text()
def part(a,b): return src[src.index(a):src.index(b)]
code=part('static int stop_stream(', 'static int configure_engine(')+part('static int native_trigger(', 'static const struct snd_pcm_ops native_ops=')+part('static void stream_fault(', 'static int native_poll(')
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "native_duplex_ring.h"
#include "native_capture_ring.h"
typedef uint32_t u32;typedef unsigned long long u64;typedef int64_t s64;typedef int64_t ktime_t;
enum {PLAY,CAP,SNDRV_PCM_TRIGGER_START,SNDRV_PCM_TRIGGER_STOP,SNDRV_PCM_TRIGGER_SUSPEND,SNDRV_PCM_STATE_DRAINING};
#define READ_ONCE(x) (x)
#define TX_BYTES (8192*256)
#define DMA_CTL 0x42004
#define DL_CTL 0x70000
#define CTL 0x10
#define DL_STATUS 0x70004
#define DMA_ENABLE 0x400040
#define STREAM_ENABLE 0x400
#define dev_err(...) do {} while(0)
static u32 registers[0x71000/4];static ktime_t now;
static unsigned starts,stops,playback_starts,playback_stops,capture_starts,capture_stops,xruns,playback_xruns,capture_xruns,max_stream_seconds;
static u64 last_frames,total_frames,ring_wraps,rx_discarded,capture_frames,max_poll_us;
static int last_error;
typedef unsigned long snd_pcm_uframes_t;
struct snd_pcm_runtime {int state;long delay;};
struct native_stream {bool prepared,active,notify,xrun;unsigned char *area;struct snd_pcm_runtime *runtime;u64 notified;};
struct native_alsa {
    struct native_stream streams[2];struct nd_play play;struct native_capture_ring capture;
    unsigned char *tx,*rx;u32 tx_hw,rx_hw;u64 tx_consumed,tx_queued;
    bool running,configured,faulted,dead;ktime_t last_poll,last_progress,last_rx_progress,started;
    int io_lock;void *pdev;
};
struct snd_pcm_substream {struct native_alsa *chip;unsigned stream;struct snd_pcm_runtime *runtime;};
static struct native_alsa *snd_pcm_substream_chip(struct snd_pcm_substream *s){return s->chip;}
static void mutex_lock(int *p){(void)p;}static void mutex_unlock(int *p){(void)p;}
static void dma_wmb(void){}static void dma_rmb(void){}static void dma_mb(void){}
static void pci_set_master(void *p){(void)p;}static void usleep_range(int a,int b){(void)a;(void)b;}
static ktime_t ktime_get(void){return now;}static s64 ktime_us_delta(ktime_t a,ktime_t b){return a-b;}
static s64 ktime_ms_delta(ktime_t a,ktime_t b){return (a-b)/1000;}
static u32 rd(struct native_alsa *e,u32 off){(void)e;return registers[off/4];}
static void wr(struct native_alsa *e,u32 off,u32 v){(void)e;registers[off/4]=v;}
static void flush(struct native_alsa *e){(void)e;}
static int finish_engine(struct native_alsa *e){if(e->running)stops++;e->running=e->configured=false;return 0;}
static int configure_engine(struct native_alsa *e){
    if(e->configured)return 0;
    memset(registers,0,sizeof(registers));registers[DL_STATUS/4]=0x101;
    e->tx_queued=e->tx_consumed=0;e->tx_hw=e->rx_hw=0;e->configured=true;return 0;
}
'''
suffix=r'''
static struct snd_pcm_runtime runtime[2];static unsigned char pcm[2][4096*6];
static void prepare_fake(struct native_alsa *e,unsigned dir){
    e->streams[dir]=(struct native_stream){.prepared=true,.area=pcm[dir],.runtime=&runtime[dir]};
    runtime[dir].state=0;
    if(dir==PLAY){memset(&e->play,0,sizeof(e->play));assert(!nd_ack(&e->play,4096,32768));}
    else memset(&e->capture,0,sizeof(e->capture));
}
static void cycles(struct native_alsa *e,unsigned n){
    for(unsigned i=0;i<n;i++){
        u64 old=e->play.played;unsigned advance=73;
        if(e->tx_queued-e->tx_consumed<advance)advance=e->tx_queued-e->tx_consumed;
        registers[0x41058/4]=(registers[0x41058/4]+advance)%8192;
        registers[0x40818/4]=(registers[0x40818/4]+73)%16384;
        now+=1520;poll_engine(e);
        assert(e->running&&!e->faulted&&!last_error&&!xruns);
        if(e->streams[PLAY].active&&e->play.played!=old)
            assert(!nd_ack(&e->play,(e->play.appl+e->play.played-old)%32768,32768));
        if(e->streams[CAP].active)
            assert(!nc_ack(&e->capture,e->capture.produced%32768,32768));
    }
}
int main(void){
    struct native_alsa e={0};struct snd_pcm_substream p={&e,PLAY,&runtime[PLAY]},c={&e,CAP,&runtime[CAP]};
    e.tx=calloc(8192,256);e.rx=calloc(16384,256);assert(e.tx&&e.rx);
    prepare_fake(&e,CAP);assert(!native_trigger(&c,SNDRV_PCM_TRIGGER_START));cycles(&e,1000);
    assert(starts==1&&capture_frames>70000);
    prepare_fake(&e,PLAY);assert(!native_trigger(&p,SNDRV_PCM_TRIGGER_START));
    assert(!native_pointer(&p)&&runtime[PLAY].delay>0&&runtime[PLAY].delay<=4096);
    cycles(&e,10000);native_pointer(&p);assert(!runtime[PLAY].delay);
    assert(playback_starts==1&&starts==1&&total_frames>700000);
    assert(!native_trigger(&p,SNDRV_PCM_TRIGGER_STOP));cycles(&e,1000);assert(!stops);
    prepare_fake(&e,PLAY);assert(!native_trigger(&p,SNDRV_PCM_TRIGGER_START));cycles(&e,1000);
    assert(!native_trigger(&c,SNDRV_PCM_TRIGGER_STOP));cycles(&e,1000);assert(!stops);
    prepare_fake(&e,CAP);assert(!native_trigger(&c,SNDRV_PCM_TRIGGER_START));cycles(&e,1000);
    assert(starts==1&&playback_starts==2&&capture_starts==2);
    assert(!native_trigger(&p,SNDRV_PCM_TRIGGER_STOP));assert(!native_trigger(&c,SNDRV_PCM_TRIGGER_STOP));assert(stops==1);
    puts("PASS actual driver: capture-first, join, >1M frames, stop/reopen each direction, last stop only");
    /* Delayed capture reader: overrun stops capture while playback continues. */
    prepare_fake(&e,PLAY);assert(!native_trigger(&p,SNDRV_PCM_TRIGGER_START));
    prepare_fake(&e,CAP);assert(!native_trigger(&c,SNDRV_PCM_TRIGGER_START));
    e.capture.produced=4090;e.capture.taken=0;
    registers[0x40818/4]=100;registers[0x41058/4]=100;now+=2000;poll_engine(&e);
    assert(e.running&&e.streams[PLAY].active&&!e.streams[CAP].active&&e.streams[CAP].xrun);
    assert(capture_xruns==1&&last_error==-EPIPE);
    last_error=0;xruns=0;cycles(&e,100);
    puts("PASS actual driver: capture overrun leaves playback running");
    /* Shared fault must stop both and prevent automatic prepare/restart. */
    prepare_fake(&e,CAP);assert(!native_trigger(&c,SNDRV_PCM_TRIGGER_START));
    now+=80001;poll_engine(&e);assert(e.faulted&&!e.running&&!e.streams[PLAY].active&&!e.streams[CAP].active);
    assert(last_error==-ETIMEDOUT);puts("PASS actual driver: shared watchdog stops both");
    free(e.tx);free(e.rx);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'t.c').write_text(prefix+code+suffix)
 subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(ROOT/'kernel'),str(p/'t.c'),'-o',str(p/'t')],check=True)
 subprocess.run([str(p/'t')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
