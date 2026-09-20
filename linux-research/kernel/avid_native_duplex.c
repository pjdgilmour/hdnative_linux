// SPDX-License-Identifier: GPL-2.0
/* Independent duplex PCM streams over one shared DMA engine.
 * Same PCI/DigiLink/DMA transport; standard ALSA permissions, no default
 * session duration limit. PipeWire converts application formats to S24_3LE.
 * Manual loading only; no firmware or clock programming.
 */
#include <linux/module.h>
#include <linux/pci.h>
#include <linux/dma-mapping.h>
#include <linux/delay.h>
#include <linux/ktime.h>
#include <linux/slab.h>
#include <linux/kthread.h>
#include <linux/mutex.h>
#include <sound/core.h>
#include <sound/pcm.h>
#include <sound/pcm_params.h>
#include "native_192_capture_control.h"
#define nc_tx_fill __maybe_unused nd_unused_tone
#include "native_capture_ring.h"
#undef nc_tx_fill
#include "native_duplex_ring.h"
#define DRV "avid_native_duplex"
static bool enable_experimental;
module_param(enable_experimental, bool, 0400);
static uint max_stream_seconds;
module_param(max_stream_seconds, uint, 0400);
MODULE_PARM_DESC(max_stream_seconds, "0 = continuous playback (default); optional 30..360 second session limit");
static char *bdf = "0000:81:00.0";
module_param(bdf, charp, 0400);
static bool bound, pci_restored, mute_restored, route_restored;
module_param(bound, bool, 0444);
module_param(pci_restored, bool, 0444);
module_param(mute_restored, bool, 0444);
module_param(route_restored, bool, 0444);
static uint starts, stops, xruns;
static uint playback_starts, playback_stops, capture_starts, capture_stops;
static uint playback_xruns, capture_xruns;
static unsigned long long capture_frames;
module_param(playback_starts, uint, 0444);
module_param(playback_stops, uint, 0444);
module_param(capture_starts, uint, 0444);
module_param(capture_stops, uint, 0444);
module_param(playback_xruns, uint, 0444);
module_param(capture_xruns, uint, 0444);
module_param(capture_frames, ullong, 0444);
module_param(starts, uint, 0444);
module_param(stops, uint, 0444);
module_param(xruns, uint, 0444);
static int last_error;
module_param(last_error, int, 0444);
static unsigned long long total_frames, last_frames, ring_wraps, rx_discarded, max_poll_us;
module_param(total_frames, ullong, 0444);
module_param(last_frames, ullong, 0444);
module_param(ring_wraps, ullong, 0444);
module_param(rx_discarded, ullong, 0444);
module_param(max_poll_us, ullong, 0444);
#define CTL 0x10
#define RESET 0x20
#define DMA_CTL 0x42004
#define DL_CTL 0x70000
#define DL_STATUS 0x70004
#define DL_IRQ_MASK 0x70018
#define DMA_ENABLE 0x400040
#define CORE_ENABLE 0x10f0000
#define STREAM_ENABLE 0x400
#define TX_BYTES 0x201100
#define RX_BYTES 0x401100
#define STATUS_BYTES 0x1000


static const u32 saved_offsets[] = {
    CTL, RESET, 0x44, DL_CTL, DL_IRQ_MASK, DMA_CTL, 0x42008,
    0x40918, 0x40958, 0x41118, 0x41158, 0x4093c, 0x4097c,
    0x40818, 0x40858, 0x40898, 0x408d8, 0x40000,
    0x41018, 0x41058, 0x41098, 0x410d8, 0x40400,
    0x4083c, 0x4087c, 0x408bc, 0x408fc, 0x40004, 0x40404, 0x40008,
};

enum { PLAY = SNDRV_PCM_STREAM_PLAYBACK, CAP = SNDRV_PCM_STREAM_CAPTURE };
struct native_stream {
    bool prepared, active, notify, xrun;
    unsigned char *area;
    struct snd_pcm_runtime *runtime;
    u64 notified;
};
struct native_alsa {
    struct pci_dev *pdev;
    struct snd_card *card;
    struct snd_pcm *pcm;
    struct task_struct *worker;
    struct mutex io_lock;
    void __iomem *bar;
    void *tx, *rx, *status;
    dma_addr_t tx_dma, rx_dma, status_dma;
    u16 command;
    u32 saved[ARRAY_SIZE(saved_offsets)];
    bool enabled, regions, configured, prepared, running, dead, faulted, quarantined;
    struct native_192 peripheral;
    struct native_stream streams[2];
    struct nd_play play;
    struct native_capture_ring capture;
    u32 tx_hw, rx_hw;
    u64 tx_consumed, tx_queued;
    ktime_t last_poll, last_progress, last_rx_progress, started;
};
static u32 rd(struct native_alsa *e, u32 off)
{
    return readl(e->bar + off);
}
static void wr(struct native_alsa *e, u32 off, u32 value)
{
    writel(value, e->bar + off);
}
static void flush(struct native_alsa *e)
{
    (void)rd(e, 0); /* Complete posted register writes. */
}

static unsigned int peripheral_read(void *ctx, unsigned int off)
{
    return rd(ctx, off);
}
static void peripheral_write(void *ctx, unsigned int off, unsigned int value)
{
    wr(ctx, off, value);
    flush(ctx);
}
static unsigned long long peripheral_now(void *ctx)
{
    (void)ctx;
    return ktime_to_us(ktime_get());
}
static void peripheral_pause(void *ctx)
{
    (void)ctx;
    usleep_range(50, 100);
}

static void setup_dma(struct native_alsa *e)
{
    /* Capture, playback, and four 256-byte status records; all zeroed.
     * Addresses are Linux DMA addresses, never CPU physical addresses.
     */
    wr(e, DL_IRQ_MASK, 0);
    wr(e, 0x42008, 0);
    wr(e, 0x44, 0);
    wr(e, DMA_CTL, 0);
    wr(e, 0x40918, lower_32_bits(e->rx_dma));
    wr(e, 0x40958, upper_32_bits(e->rx_dma));
    wr(e, 0x41118, lower_32_bits(e->tx_dma));
    wr(e, 0x41158, upper_32_bits(e->tx_dma));
    wr(e, 0x4093c, lower_32_bits(e->status_dma));
    wr(e, 0x4097c, upper_32_bits(e->status_dma));
    wr(e, 0x40818, 0);
    wr(e, 0x40858, 0);
    wr(e, 0x40898, 0);
    wr(e, 0x408d8, (rd(e, 0x408d8) & 0xfffc3fff) | 0x3fff);
    wr(e, 0x40000, 0x40);
    wr(e, 0x41018, 0);
    wr(e, 0x41058, 0);
    wr(e, 0x41098, 0);
    wr(e, 0x410d8, (rd(e, 0x410d8) & 0xfffc1fff) | 0x1fff);
    wr(e, 0x40400, 0x40);
    wr(e, 0x4083c, 0);
    wr(e, 0x4087c, 0);
    wr(e, 0x408bc, 0);
    wr(e, 0x408fc, (rd(e, 0x408fc) & 0xfffc0003) | 3);
    wr(e, 0x40004, 0x8000);
    wr(e, 0x40404, 0);
    wr(e, 0x40008, 0);
    wr(e, RESET, 0x80008000);
    flush(e);
    usleep_range(1000, 1500);
    wr(e, RESET, 0);
    wr(e, DMA_CTL, 0x8000);
    wr(e, CTL, rd(e, CTL) | CORE_ENABLE);
    flush(e);
}


static bool stop_dma(struct native_alsa *e)
{
    wr(e, CTL, rd(e, CTL) & ~STREAM_ENABLE);
    wr(e, DL_IRQ_MASK, 0);
    wr(e, DMA_CTL, rd(e, DMA_CTL) & ~DMA_ENABLE);
    wr(e, DL_CTL, rd(e, DL_CTL) & ~0xf00);
    wr(e, RESET, 0x400040);
    flush(e);
    usleep_range(1000, 1500);
    wr(e, RESET, 0);
    wr(e, CTL, rd(e, CTL) & ~(CORE_ENABLE | STREAM_ENABLE));
    wr(e, DMA_CTL, 0);
    flush(e);
    pci_clear_master(e->pdev);
    /* Preserve allocations if outstanding PCIe transactions will not drain. */
    if (!pci_wait_for_pending_transaction(e->pdev)) return false;
    msleep(20);
    return true;
}

/* Driver mutex serializes MMIO, DigiLink and DMA memory. When both are
 * required, ALSA's nonatomic stream mutex precedes this mutex. Never call
 * back into ALSA while holding io_lock: period/stop can invoke our ops.
 */
static void init_peripheral(struct native_alsa *e)
{
    e->peripheral = (struct native_192) {
        .ctx = e, .read = peripheral_read, .write = peripheral_write,
        .now_us = peripheral_now, .pause = peripheral_pause,
        .before = -1, .during = -1, .after = -1, .route_enabled = 1,
        .route_before = -1, .route_during = -1, .route_after = -1,
    };
}

static int quiet_state(struct native_alsa *e)
{
    unsigned int i;
    if (rd(e, 0) != 0xd400 || rd(e, 4) != 0x01050040 ||
        (rd(e, DL_STATUS) & 0x101) != 0x101)
        return -ENOLINK;
    if (rd(e, CTL) != 0xa00 || rd(e, RESET) || rd(e, DL_CTL) ||
        rd(e, DMA_CTL) || rd(e, DL_IRQ_MASK) || rd(e, 0x42008))
        return -EBUSY;
    for (i = 7; i <= 12; i++)
        if (rd(e, saved_offsets[i]))
            return -EBUSY;
    return 0;
}

/* io_lock held. No ALSA callbacks while holding it. The stream callbacks
 * detach area/runtime before managed buffers may be freed; the poller only
 * accesses these cached pointers under io_lock. ALSA appl_ptr publication via
 * ack separates user copies from hardware copies in both directions.
 * Notifications acquire one ALSA stream lock AFTER releasing io_lock. */
static int finish_engine(struct native_alsa *e)
{
    int i, mute_err, route_err, err = 0;
    bool drained = true;
    bool had = e->configured || e->peripheral.write_attempted || e->peripheral.route_write_attempted;
    if (e->running) stops++;
    e->running = false;
    if (e->quarantined) return -EBUSY;
    if (e->configured) drained = stop_dma(e);
    mute_err = n192_restore(&e->peripheral);
    route_err = n192_route_restore(&e->peripheral);
    if (mute_err || route_err) { e->faulted=true; err=mute_err ? mute_err : route_err; }
    if (!drained) {
        e->quarantined=e->faulted=true;
        __module_get(THIS_MODULE); pci_dev_get(e->pdev);
        dev_err(&e->pdev->dev,"DMA drain failed; buffers/module pinned; reboot required.\n");
        err=-EBUSY;
    } else if (e->configured) {
        for (i=ARRAY_SIZE(saved_offsets)-1;i>=0;i--) wr(e,saved_offsets[i],e->saved[i]);
        flush(e); e->configured=false;
    }
    if (had) {
        mute_restored=!e->peripheral.restore_required && !mute_err;
        route_restored=!e->peripheral.route_restore_required && !route_err;
        dev_info(&e->pdev->dev,"engine stopped: TX=%llu RX=%u restored=%u/%u error=%d\n",
                 e->tx_consumed,e->rx_hw,mute_restored,route_restored,err);
        if (!err) init_peripheral(e);
    }
    if (err) last_error=err;
    return err;
}

static int stop_stream(struct native_alsa *e, unsigned int dir)
{
    struct native_stream *s=&e->streams[dir];
    if (s->active) {
        if (dir==PLAY) { playback_stops++; last_frames=e->play.played; }
        else capture_stops++;
    }
    s->active=s->prepared=s->notify=s->xrun=false;
    s->area=NULL; s->runtime=NULL;
    if (!e->streams[PLAY].active && !e->streams[CAP].active)
        return finish_engine(e);
    if (dir==PLAY && e->running) {
        /* Drop remaining output while capture continues. No RX reset/route change. */
        memset(e->tx,0,TX_BYTES);
        dma_wmb();
    }
    return 0;
}

static int configure_engine(struct native_alsa *e)
{
    unsigned int i;
    int err;
    if (e->configured) return 0;
    if (e->faulted || e->dead) return -EIO;
    err=quiet_state(e); if (err) return err;
    memset(e->tx,0,TX_BYTES); memset(e->rx,0,RX_BYTES); memset(e->status,0,STATUS_BYTES);
    e->tx_hw=e->rx_hw=0; e->tx_queued=e->tx_consumed=0;
    for (i=0;i<ARRAY_SIZE(saved_offsets);i++) e->saved[i]=rd(e,saved_offsets[i]);
    init_peripheral(e); mute_restored=route_restored=false;
    err=n192_route_enable(&e->peripheral); if (err) goto fail;
    err=n192_unmute(&e->peripheral); if (err) goto fail;
    msleep(20); e->configured=true; setup_dma(e);
    err=n192_check_unmuted(&e->peripheral);
    if (!err) err=n192_check_route(&e->peripheral,1,&e->peripheral.route_during);
    if (!err) return 0;
fail:
    finish_engine(e); return err;
}
static const struct snd_pcm_hardware native_hardware = {
    .info=SNDRV_PCM_INFO_INTERLEAVED | SNDRV_PCM_INFO_BATCH | SNDRV_PCM_INFO_NO_REWINDS,
    .formats=SNDRV_PCM_FMTBIT_S24_3LE, .rates=SNDRV_PCM_RATE_48000,
    .rate_min=48000,.rate_max=48000,.channels_min=2,.channels_max=2,
    .buffer_bytes_max=ND_ALSA*6,.period_bytes_min=ND_PERIOD*6,.period_bytes_max=ND_PERIOD*6,
    .periods_min=4,.periods_max=4,
};
static int native_open(struct snd_pcm_substream *ss)
{
    struct native_alsa *e=snd_pcm_substream_chip(ss);
    int err=0;
    mutex_lock(&e->io_lock);
    if (e->dead || e->faulted) err=-EIO; else ss->runtime->hw=native_hardware;
    mutex_unlock(&e->io_lock); return err;
}
static int native_hw_free(struct snd_pcm_substream *ss)
{
    struct native_alsa *e=snd_pcm_substream_chip(ss);
    int err;
    mutex_lock(&e->io_lock); err=stop_stream(e,ss->stream); mutex_unlock(&e->io_lock);
    return err;
}
static int native_prepare(struct snd_pcm_substream *ss)
{
    struct native_alsa *e=snd_pcm_substream_chip(ss);
    struct snd_pcm_runtime *r=ss->runtime;
    struct native_stream *s=&e->streams[ss->stream];
    int err;
    mutex_lock(&e->io_lock);
    err=stop_stream(e,ss->stream);
    if (err || e->faulted || e->dead) {err=err ? err : -EIO; goto out;}
    if (r->format!=SNDRV_PCM_FORMAT_S24_3LE || r->rate!=48000 || r->channels!=2 ||
        r->buffer_size!=ND_ALSA || r->period_size!=ND_PERIOD || !r->dma_area) {
        err=-EINVAL; goto out;
    }
    err=configure_engine(e); if (err) goto out;
    if (ss->stream==PLAY) memset(&e->play,0,sizeof(e->play));
    else memset(&e->capture,0,sizeof(e->capture));
    r->delay=0;
    *s=(struct native_stream){.prepared=true,.area=r->dma_area,.runtime=r};
out:
    if (err) last_error=err;
    mutex_unlock(&e->io_lock); return err;
}
static int native_ack(struct snd_pcm_substream *ss)
{
    struct native_alsa *e=snd_pcm_substream_chip(ss);
    struct snd_pcm_runtime *r=ss->runtime;
    int err;
    mutex_lock(&e->io_lock);
    if (!e->streams[ss->stream].prepared || e->dead || e->faulted) err=-EIO;
    else if (ss->stream==PLAY) err=nd_ack(&e->play,READ_ONCE(r->control->appl_ptr),r->boundary);
    else err=nc_ack(&e->capture,READ_ONCE(r->control->appl_ptr),r->boundary);
    if (err) last_error=err;
    mutex_unlock(&e->io_lock); return err;
}
static int native_trigger(struct snd_pcm_substream *ss,int cmd)
{
    struct native_alsa *e=snd_pcm_substream_chip(ss);
    struct native_stream *s=&e->streams[ss->stream];
    int err=0;
    mutex_lock(&e->io_lock);
    switch (cmd) {
    case SNDRV_PCM_TRIGGER_START:
        if (!s->prepared || s->active || e->faulted || e->dead ||
            (ss->stream==PLAY && !e->play.accepted)) {err=-EIO; break;}
        err=configure_engine(e); if (err) break;
        if (ss->stream==PLAY) e->play.base=e->tx_queued;
        else {
            /* Capture begins at the current producer, not at old discarded data. */
            e->rx_hw=rd(e,0x40818)&(ND_RX-1);
            e->capture.hw=e->rx_hw;
            dma_mb(); wr(e,0x40858,e->rx_hw); flush(e);
        }
        s->active=true;
        if (!e->running) {
            err=nd_refill(&e->play,e->tx,e->streams[PLAY].area,&e->tx_queued,
                          e->tx_consumed,e->streams[PLAY].active,0);
            if (err) {s->active=false; finish_engine(e); break;}
            dma_wmb(); pci_set_master(e->pdev);
            wr(e,0x41018,e->tx_queued&(ND_TX-1));
            wr(e,DMA_CTL,rd(e,DMA_CTL)|DMA_ENABLE);
            wr(e,DL_CTL,rd(e,DL_CTL)|0x100); flush(e); usleep_range(50,100);
            wr(e,CTL,rd(e,CTL)|STREAM_ENABLE); flush(e);
            e->last_poll=e->last_progress=e->last_rx_progress=e->started=ktime_get();
            e->running=true; starts++;
        }
        if (ss->stream==PLAY) playback_starts++; else capture_starts++;
        break;
    case SNDRV_PCM_TRIGGER_STOP:
    case SNDRV_PCM_TRIGGER_SUSPEND:
        err=stop_stream(e,ss->stream); break;
    default: err=-EINVAL;
    }
    if (err) last_error=err;
    mutex_unlock(&e->io_lock); return err;
}
static snd_pcm_uframes_t native_pointer(struct snd_pcm_substream *ss)
{
    struct native_alsa *e=snd_pcm_substream_chip(ss);
    snd_pcm_uframes_t pos;
    mutex_lock(&e->io_lock);
    /* A playback stream joining capture may have queued silence ahead of it.
     * Expose that extra lead separately from ALSA's unconsumed PCM frames. */
    ss->runtime->delay=(ss->stream==PLAY && e->streams[PLAY].active &&
                       e->play.base>e->tx_consumed) ? e->play.base-e->tx_consumed : 0;
    pos=(ss->stream==PLAY ? e->play.played : e->capture.produced)%ND_ALSA;
    mutex_unlock(&e->io_lock); return pos;
}
static const struct snd_pcm_ops native_ops={
    .open=native_open,.close=native_hw_free,.ioctl=snd_pcm_lib_ioctl,.hw_free=native_hw_free,
    .prepare=native_prepare,.trigger=native_trigger,.pointer=native_pointer,.ack=native_ack,
};
static void stream_fault(struct native_alsa *e,unsigned int dir,int err)
{
    bool active=e->streams[dir].active;
    stop_stream(e,dir);
    if (active) {
        dev_err(&e->pdev->dev,"%s stream fault=%d; peer active=%u\n",
                dir==PLAY ? "playback" : "capture",err,e->streams[1-dir].active);
        e->streams[dir].xrun=true; xruns++;
        if (dir==PLAY) playback_xruns++; else capture_xruns++;
    }
    last_error=err;
}
static void poll_engine(struct native_alsa *e)
{
    struct native_stream *p=&e->streams[PLAY],*c=&e->streams[CAP];
    ktime_t now=ktime_get();
    s64 elapsed=ktime_us_delta(now,e->last_poll);
    u32 tx=rd(e,0x41058)&(ND_TX-1),rx=rd(e,0x40818)&(ND_RX-1);
    u32 delta=(tx-e->tx_hw)&(ND_TX-1),rx_delta=(rx-e->rx_hw)&(ND_RX-1);
    int err=0,draining=0;
    e->last_poll=now;
    if (elapsed>0 && (u64)elapsed>max_poll_us) max_poll_us=elapsed;
    if (elapsed<0 || elapsed>=80000 || ktime_ms_delta(now,e->last_progress)>=100 ||
        ktime_ms_delta(now,e->last_rx_progress)>=100) err=-ETIMEDOUT;
    else if (max_stream_seconds && ktime_ms_delta(now,e->started)>=(s64)max_stream_seconds*1000) err=-ETIME;
    else if ((rd(e,DL_STATUS)&0x101)!=0x101) err=-ENOLINK;
    else if (delta>e->tx_queued-e->tx_consumed) err=-EPIPE;
    if (err) goto common_fault;
    e->tx_hw=tx; e->tx_consumed+=delta;
    if (delta) e->last_progress=now;
    if (rx_delta) e->last_rx_progress=now;
    if (p->active) {
        u64 before=e->play.played;
        draining=READ_ONCE(p->runtime->state)==SNDRV_PCM_STATE_DRAINING;
        err=nd_position(&e->play,e->tx_consumed);
        total_frames+=e->play.played-before;
        ring_wraps+=e->play.played/ND_TX-before/ND_TX;
        if (!err && e->play.played==e->play.accepted && !draining) err=-EPIPE;
        if (err) stream_fault(e,PLAY,err);
        else {
            p->notify |= e->play.played/ND_PERIOD!=p->notified || (draining && e->play.played==e->play.accepted);
            p->notified=e->play.played/ND_PERIOD;
        }
    }
    if (!e->running) return;
    if (c->active) {
        u64 before=e->capture.produced;
        dma_rmb(); err=nc_pull(&e->capture,e->rx,c->area,rx);
        if (err<0) stream_fault(e,CAP,err);
        else {
            capture_frames+=e->capture.produced-before;
            c->notify |= e->capture.produced/ND_PERIOD!=c->notified;
            c->notified=e->capture.produced/ND_PERIOD;
        }
    } else rx_discarded+=rx_delta;
    if (!e->running) return;
    e->rx_hw=rx;
    err=nd_refill(&e->play,e->tx,p->area,&e->tx_queued,e->tx_consumed,p->active,draining);
    if (err) goto common_fault;
    dma_mb(); wr(e,0x40858,rx); wr(e,0x41018,e->tx_queued&(ND_TX-1)); flush(e);
    return;
common_fault:
    dev_err(&e->pdev->dev,"shared transport fault=%d gap_us=%lld tx=%u rx=%u\n",err,elapsed,tx,rx);
    /* A shared transport failure must not invite endless automatic restart. */
    e->faulted=true;
    stream_fault(e,PLAY,err); stream_fault(e,CAP,err);
}
static int native_poll(void *data)
{
    struct native_alsa *e=data;
    while (!kthread_should_stop()) {
        unsigned int dir;
        mutex_lock(&e->io_lock);
        if (e->running && !e->dead) poll_engine(e);
        mutex_unlock(&e->io_lock);
        for (dir=0;dir<2;dir++) {
            struct snd_pcm_substream *ss=e->pcm->streams[dir].substream;
            bool xrun,notify;
            snd_pcm_stream_lock(ss);
            mutex_lock(&e->io_lock);
            xrun=e->streams[dir].xrun;
            notify=e->streams[dir].notify && e->streams[dir].active;
            e->streams[dir].xrun=e->streams[dir].notify=false;
            mutex_unlock(&e->io_lock);
            if (xrun) snd_pcm_stop(ss,SNDRV_PCM_STATE_XRUN);
            else if (notify) snd_pcm_period_elapsed_under_stream_lock(ss);
            snd_pcm_stream_unlock(ss);
        }
        usleep_range(1000,1500);
    }
    return 0;
}

static void release_resources(struct native_alsa *e)
{
    u16 command = 0;
    if (e->quarantined)
        return;
    if (e->status)
        dma_free_coherent(&e->pdev->dev, STATUS_BYTES, e->status, e->status_dma);
    if (e->rx)
        dma_free_coherent(&e->pdev->dev, RX_BYTES, e->rx, e->rx_dma);
    if (e->tx)
        dma_free_coherent(&e->pdev->dev, TX_BYTES, e->tx, e->tx_dma);
    if (e->bar)
        pci_iounmap(e->pdev, e->bar);
    if (e->regions)
        pci_release_regions(e->pdev);
    if (e->enabled) {
        pci_disable_device(e->pdev);
        pci_write_config_word(e->pdev, PCI_COMMAND, e->command);
        pci_restored = !pci_read_config_word(e->pdev, PCI_COMMAND, &command) && command == e->command;
        dev_info(&e->pdev->dev, "PCI_COMMAND_RESTORED=%u command=%04x expected=%04x\n",
                 pci_restored, command, e->command);
    }
    kfree(e);
}

static int native_probe(struct pci_dev *pdev, const struct pci_device_id *id)
{
    struct native_alsa *e;
    int err;
    if (strcmp(pci_name(pdev), bdf) || pdev->subsystem_vendor != 0x11af ||
        pdev->subsystem_device != 0xef80 || pci_resource_len(pdev, 0) != 0x400000)
        return -ENODEV;
    e = kzalloc(sizeof(*e), GFP_KERNEL);
    if (!e)
        return -ENOMEM;
    e->pdev = pdev;
    mutex_init(&e->io_lock);
    init_peripheral(e);
    err = pci_read_config_word(pdev, PCI_COMMAND, &e->command);
    if (err) { err = -EIO; goto fail; }
    if (e->command & PCI_COMMAND_MASTER) { err = -EBUSY; goto fail; }
    err = pci_enable_device_mem(pdev);
    if (err)
        goto fail;
    e->enabled = true;
    pci_clear_master(pdev);
    pci_intx(pdev, 0);
    err = pci_request_regions(pdev, DRV);
    if (err)
        goto fail;
    e->regions = true;
    e->bar = pci_iomap(pdev, 0, 0x71000);
    if (!e->bar) { err = -ENOMEM; goto fail; }
    err = quiet_state(e);
    if (err)
        goto fail;
    err = n192_preflight(&e->peripheral);
    if (err)
        goto fail;
    err = dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(32));
    if (err)
        goto fail;
    e->tx = dma_alloc_coherent(&pdev->dev, TX_BYTES, &e->tx_dma, GFP_KERNEL);
    e->rx = dma_alloc_coherent(&pdev->dev, RX_BYTES, &e->rx_dma, GFP_KERNEL);
    e->status = dma_alloc_coherent(&pdev->dev, STATUS_BYTES, &e->status_dma, GFP_KERNEL);
    if (!e->tx || !e->rx || !e->status) { err = -ENOMEM; goto fail; }
    if ((e->tx_dma | e->rx_dma | e->status_dma) & 255) { err = -EINVAL; goto fail; }
    err = snd_card_new(&pdev->dev, -1, "AvidDuplex", THIS_MODULE, 0, &e->card);
    if (err)
        goto fail;
    strscpy(e->card->driver, "AvidDuplex");
    strscpy(e->card->shortname, "Avid HD Native + 192 Duplex");
    snprintf(e->card->longname, sizeof(e->card->longname), "HD Native PCIe + 192 at %s (duplex, experimental)", pci_name(pdev));
    err = snd_pcm_new(e->card, "192 analog 1-2", 0, 1, 1, &e->pcm);
    if (err)
        goto fail;
    e->pcm->private_data = e;
    e->pcm->nonatomic = true;
    strscpy(e->pcm->name, "192 analog 1-2");
    snd_pcm_set_ops(e->pcm, SNDRV_PCM_STREAM_PLAYBACK, &native_ops);
    snd_pcm_set_ops(e->pcm, SNDRV_PCM_STREAM_CAPTURE, &native_ops);
    err = snd_pcm_set_managed_buffer_all(e->pcm, SNDRV_DMA_TYPE_VMALLOC, NULL, 0, 0);
    if (err)
        goto fail;
    e->worker = kthread_run(native_poll, e, "avid-duplex-pcm");
    if (IS_ERR(e->worker)) { err = PTR_ERR(e->worker); e->worker = NULL; goto fail; }
    err = snd_card_register(e->card);
    if (err)
        goto fail;
    pci_set_drvdata(pdev, e);
    bound = true;
    dev_info(&pdev->dev, "ALSA ready: card=%d id=%s; 48 kHz S24_3LE stereo, stream limit=%u s (0=continuous); experimental duplex\n",
             e->card->number, e->card->id, max_stream_seconds);
    return 0;
fail:
    last_error = err;
    dev_err(&pdev->dev, "probe failed: %d\n", err);
    if (e->worker)
        kthread_stop(e->worker);
    if (e->card)
        snd_card_free(e->card);
    release_resources(e);
    return err;
}

static void native_remove(struct pci_dev *pdev)
{
    struct native_alsa *e = pci_get_drvdata(pdev);
    snd_card_disconnect(e->card);
    kthread_stop(e->worker);
    snd_card_free(e->card); /* Waits for open PCM handles; their close cleans up. */
    mutex_lock(&e->io_lock);
    e->dead = true;
    stop_stream(e,PLAY);
    stop_stream(e,CAP);
    mutex_unlock(&e->io_lock);
    pci_set_drvdata(pdev, NULL);
    bound = false;
    release_resources(e);
}

static void native_shutdown(struct pci_dev *pdev)
{
    struct native_alsa *e = pci_get_drvdata(pdev);
    mutex_lock(&e->io_lock);
    e->dead = true;
    stop_stream(e,PLAY);
    stop_stream(e,CAP);
    mutex_unlock(&e->io_lock);
}

static int native_suspend(struct device *dev)
{
    dev_warn(dev, "Unload the experimental driver before suspending/hibernating.\n");
    return -EBUSY;
}
static const struct dev_pm_ops native_pm = {
    .suspend = native_suspend, .freeze = native_suspend, .poweroff = native_suspend,
};
static const struct pci_device_id native_ids[] = {
    { PCI_DEVICE(0x11af, 0xef80) }, { 0 }
};
/* No MODULE_DEVICE_TABLE: explicit loading while cold-boot support is unverified. */
static struct pci_driver native_driver = {
    .name = DRV, .id_table = native_ids, .probe = native_probe,
    .remove = native_remove, .shutdown = native_shutdown,
    .driver.pm = &native_pm,
};
static int __init native_init(void)
{
    int err;
    if (!enable_experimental || (max_stream_seconds &&
        (max_stream_seconds < 30 || max_stream_seconds > 360)))
        return -EINVAL;
    pr_info(DRV ": begin duplex ALSA session\n");
    err = pci_register_driver(&native_driver);
    if (err)
        return err;
    if (!bound) {
        pci_unregister_driver(&native_driver);
        return last_error ? last_error : -ENODEV;
    }
    return 0;
}
static void __exit native_exit(void)
{
    pci_unregister_driver(&native_driver);
}
module_init(native_init);
module_exit(native_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("HD Native PCIe + 192 duplex ALSA, 48 kHz stereo, experimental");
