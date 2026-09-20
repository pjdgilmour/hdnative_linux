// SPDX-License-Identifier: GPL-2.0
/* Desktop variant of the validated avid_native_alsa prototype.
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
#include "native_192_control.h"
#include "native_pcm_ring.h"
#define DRV "avid_native_desktop"
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
    struct native_pcm_ring ring;
    u32 rx_hw;
    u64 notified;
    ktime_t last_poll, last_progress, started;
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

/* io_lock held. Safe for repeated STOP, hw_free, close and remove. */
static int finish_session(struct native_alsa *e)
{
    int i, mute_err, route_err, err = 0;
    bool drained = true;
    bool had_session = e->configured || e->peripheral.write_attempted ||
                       e->peripheral.route_write_attempted;
    if (e->running)
        stops++;
    e->running = false;
    e->prepared = false;
    if (e->quarantined)
        return -EBUSY;
    if (e->configured)
        drained = stop_dma(e);
    mute_err = n192_restore(&e->peripheral);
    route_err = n192_route_restore(&e->peripheral);
    if (mute_err || route_err) {
        e->faulted = true; /* Refuse automatic retries after cleanup failure. */
        err = mute_err ? mute_err : route_err;
    }
    if (!drained) {
        /* Do not release memory while the device may still access it. */
        e->quarantined = true;
        e->faulted = true;
        __module_get(THIS_MODULE);
        pci_dev_get(e->pdev);
        dev_err(&e->pdev->dev, "DMA drain failed; allocations and module pinned; reboot required.\n");
        err = -EBUSY;
    } else if (e->configured) {
        for (i = ARRAY_SIZE(saved_offsets) - 1; i >= 0; i--)
            wr(e, saved_offsets[i], e->saved[i]);
        flush(e);
        e->configured = false;
    }
    if (had_session) {
        mute_restored = !e->peripheral.restore_required && !mute_err;
        route_restored = !e->peripheral.route_restore_required && !route_err;
        last_frames = e->ring.consumed;
        dev_info(&e->pdev->dev,
                 "stop: queued=%llu consumed=%llu hw=%u mute=%d route=%d restored=%u/%u error=%d\n",
                 e->ring.queued, e->ring.consumed, e->ring.hw,
                 e->peripheral.after, e->peripheral.route_after,
                 mute_restored, route_restored, err);
        /* Keep pending restoration flags after a failure. */
        if (!err)
            init_peripheral(e);
    }
    if (err)
        last_error = err;
    return err;
}

static const struct snd_pcm_hardware native_hardware = {
    .info = SNDRV_PCM_INFO_INTERLEAVED | SNDRV_PCM_INFO_BATCH |
            SNDRV_PCM_INFO_NO_REWINDS,
    .formats = SNDRV_PCM_FMTBIT_S24_3LE,
    .rates = SNDRV_PCM_RATE_48000,
    .rate_min = 48000, .rate_max = 48000,
    .channels_min = 2, .channels_max = 2,
    .buffer_bytes_max = NATIVE_ALSA_FRAMES * NATIVE_PCM_BYTES,
    .period_bytes_min = NATIVE_PERIOD_FRAMES * NATIVE_PCM_BYTES,
    .period_bytes_max = NATIVE_PERIOD_FRAMES * NATIVE_PCM_BYTES,
    .periods_min = 4, .periods_max = 4,
};

static int native_open(struct snd_pcm_substream *ss)
{
    struct native_alsa *e = snd_pcm_substream_chip(ss);
    int err = 0;
    /* /dev/snd permissions and logind/audio-group policy govern access. */
    mutex_lock(&e->io_lock);
    if (e->faulted || e->dead)
        err = -EIO;
    else
        ss->runtime->hw = native_hardware;
    mutex_unlock(&e->io_lock);
    return err;
}

static int native_hw_free(struct snd_pcm_substream *ss)
{
    struct native_alsa *e = snd_pcm_substream_chip(ss);
    int err;
    mutex_lock(&e->io_lock);
    err = finish_session(e);
    mutex_unlock(&e->io_lock);
    return err;
}

static int native_close(struct snd_pcm_substream *ss)
{
    return native_hw_free(ss);
}

static int native_prepare(struct snd_pcm_substream *ss)
{
    struct native_alsa *e = snd_pcm_substream_chip(ss);
    struct snd_pcm_runtime *r = ss->runtime;
    unsigned int i;
    int err;
    mutex_lock(&e->io_lock);
    err = finish_session(e);
    if (err || e->faulted || e->dead) {
        err = err ? err : -EIO;
        goto out;
    }
    if (r->format != SNDRV_PCM_FORMAT_S24_3LE || r->rate != 48000 ||
        r->channels != 2 || r->buffer_size != NATIVE_ALSA_FRAMES ||
        r->period_size != NATIVE_PERIOD_FRAMES || !r->dma_area) {
        err = -EINVAL;
        goto out;
    }
    err = quiet_state(e);
    if (err)
        goto out;
    memset(&e->ring, 0, sizeof(e->ring));
    e->rx_hw = 0;
    e->notified = 0;
    memset(e->tx, 0, TX_BYTES);
    memset(e->rx, 0, RX_BYTES);
    memset(e->status, 0, STATUS_BYTES);
    for (i = 0; i < ARRAY_SIZE(saved_offsets); i++)
        e->saved[i] = rd(e, saved_offsets[i]);
    init_peripheral(e);
    mute_restored = route_restored = false;
    err = n192_route_enable(&e->peripheral);
    if (err)
        goto cleanup;
    err = n192_unmute(&e->peripheral);
    if (err)
        goto cleanup;
    msleep(20);
    e->configured = true;
    setup_dma(e);
    err = n192_check_unmuted(&e->peripheral);
    if (!err)
        err = n192_check_route(&e->peripheral, 1, &e->peripheral.route_during);
    if (err)
        goto cleanup;
    e->prepared = true;
    dev_info(&e->pdev->dev, "prepared: stereo S24_3LE 48000 Hz buffer=4096 period=1024; route4d=1 control0=0\n");
    goto out;
cleanup:
    finish_session(e);
out:
    if (err)
        last_error = err;
    mutex_unlock(&e->io_lock);
    return err;
}

static int native_ack(struct snd_pcm_substream *ss)
{
    struct native_alsa *e = snd_pcm_substream_chip(ss);
    struct snd_pcm_runtime *r = ss->runtime;
    int err;
    mutex_lock(&e->io_lock);
    if (!e->prepared || e->dead || e->faulted) {
        err = -EIO;
        goto out;
    }
    err = native_ring_push(&e->ring, e->tx, r->dma_area,
                           READ_ONCE(r->control->appl_ptr), r->boundary);
    if (err >= 0) {
        dma_wmb();
        wr(e, 0x41018, e->ring.queued & (NATIVE_HW_FRAMES - 1));
        flush(e);
        err = 0;
    }
out:
    if (err)
        last_error = err;
    mutex_unlock(&e->io_lock);
    return err;
}

static int native_trigger(struct snd_pcm_substream *ss, int cmd)
{
    struct native_alsa *e = snd_pcm_substream_chip(ss);
    int err = 0;
    mutex_lock(&e->io_lock);
    switch (cmd) {
    case SNDRV_PCM_TRIGGER_START:
        if (!e->prepared || e->running || e->dead || e->faulted ||
            !e->ring.queued || e->ring.consumed) {
            err = -EIO;
            break;
        }
        dma_wmb();
        pci_set_master(e->pdev);
        wr(e, 0x41018, e->ring.queued & (NATIVE_HW_FRAMES - 1));
        wr(e, DMA_CTL, rd(e, DMA_CTL) | DMA_ENABLE);
        wr(e, DL_CTL, rd(e, DL_CTL) | 0x100);
        flush(e);
        usleep_range(50, 100);
        wr(e, CTL, rd(e, CTL) | STREAM_ENABLE);
        flush(e);
        e->last_poll = e->last_progress = e->started = ktime_get();
        e->running = true;
        starts++;
        break;
    case SNDRV_PCM_TRIGGER_STOP:
    case SNDRV_PCM_TRIGGER_SUSPEND:
        err = finish_session(e);
        break;
    default:
        err = -EINVAL;
    }
    if (err)
        last_error = err;
    mutex_unlock(&e->io_lock);
    return err;
}

static snd_pcm_uframes_t native_pointer(struct snd_pcm_substream *ss)
{
    struct native_alsa *e = snd_pcm_substream_chip(ss);
    snd_pcm_uframes_t pos;
    mutex_lock(&e->io_lock);
    pos = e->ring.consumed % NATIVE_ALSA_FRAMES;
    mutex_unlock(&e->io_lock);
    return pos;
}

static const struct snd_pcm_ops native_ops = {
    .open = native_open, .close = native_close, .ioctl = snd_pcm_lib_ioctl,
    .hw_free = native_hw_free, .prepare = native_prepare,
    .trigger = native_trigger, .pointer = native_pointer, .ack = native_ack,
};

static int native_poll(void *data)
{
    struct native_alsa *e = data;
    struct snd_pcm_substream *ss = e->pcm->streams[SNDRV_PCM_STREAM_PLAYBACK].substream;
    while (!kthread_should_stop()) {
        bool notify = false;
        int err = 0;
        snd_pcm_stream_lock(ss);
        mutex_lock(&e->io_lock);
        if (e->running && !e->dead) {
            ktime_t now = ktime_get();
            s64 elapsed = ktime_us_delta(now, e->last_poll);
            u32 hw = rd(e, 0x41058) & (NATIVE_HW_FRAMES - 1);
            u32 rx = rd(e, 0x40818) & 0x3fff;
            u64 before = e->ring.consumed;
            int draining = ss->runtime->state == SNDRV_PCM_STATE_DRAINING;
            e->last_poll = now;
            if (elapsed > max_poll_us)
                max_poll_us = elapsed;
            /* Under 1 ALSA ring and 1 native wrap. Refuse ambiguous deltas. */
            if (elapsed >= 80000 || ktime_ms_delta(now, e->last_progress) >= 100)
                err = -ETIMEDOUT;
            else if (max_stream_seconds &&
                     ktime_ms_delta(now, e->started) >= (s64)max_stream_seconds * 1000)
                err = -ETIME;
            else if ((rd(e, DL_STATUS) & 0x101) != 0x101)
                err = -ENOLINK;
            else
                err = native_ring_advance(&e->ring, e->tx, hw, draining);
            if (err < 0) {
                last_error = err;
                xruns++;
                dev_err(&e->pdev->dev, "poll failed=%d hw=%u previous=%u queued=%llu consumed=%llu gap_us=%lld state=%d\n",
                        err, hw, e->ring.hw, e->ring.queued, e->ring.consumed,
                        elapsed, ss->runtime->state);
                finish_session(e);
            } else {
                total_frames += e->ring.consumed - before;
                ring_wraps += e->ring.consumed / NATIVE_HW_FRAMES - before / NATIVE_HW_FRAMES;
                if (e->ring.consumed != before)
                    e->last_progress = now;
                /* DSI 19f060 -> +40858, ring-manager publish 19ecb0.
                 * Discard input; this does NOT implement ALSA capture. */
                rx_discarded += (rx - e->rx_hw) & 0x3fff;
                e->rx_hw = rx;
                dma_wmb();
                wr(e, 0x40858, rx);
                flush(e);
                notify = e->ring.consumed / NATIVE_PERIOD_FRAMES != e->notified ||
                         (draining && e->ring.consumed == e->ring.queued);
                e->notified = e->ring.consumed / NATIVE_PERIOD_FRAMES;
            }
        }
        mutex_unlock(&e->io_lock);
        if (err < 0)
            snd_pcm_stop(ss, SNDRV_PCM_STATE_XRUN);
        else if (notify)
            snd_pcm_period_elapsed_under_stream_lock(ss);
        snd_pcm_stream_unlock(ss);
        usleep_range(1000, 1500);
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
    err = snd_card_new(&pdev->dev, -1, "AvidHDNative", THIS_MODULE, 0, &e->card);
    if (err)
        goto fail;
    strscpy(e->card->driver, "AvidNativeDesk");
    strscpy(e->card->shortname, "Avid HD Native + 192 I/O");
    snprintf(e->card->longname, sizeof(e->card->longname), "HD Native PCIe + 192 at %s (desktop playback, experimental)", pci_name(pdev));
    err = snd_pcm_new(e->card, "192 analog 1-2", 0, 1, 0, &e->pcm);
    if (err)
        goto fail;
    e->pcm->private_data = e;
    e->pcm->nonatomic = true;
    strscpy(e->pcm->name, "192 analog 1-2");
    snd_pcm_set_ops(e->pcm, SNDRV_PCM_STREAM_PLAYBACK, &native_ops);
    err = snd_pcm_set_managed_buffer_all(e->pcm, SNDRV_DMA_TYPE_VMALLOC, NULL, 0, 0);
    if (err)
        goto fail;
    e->worker = kthread_run(native_poll, e, "avid-desktop-pcm");
    if (IS_ERR(e->worker)) { err = PTR_ERR(e->worker); e->worker = NULL; goto fail; }
    err = snd_card_register(e->card);
    if (err)
        goto fail;
    pci_set_drvdata(pdev, e);
    bound = true;
    dev_info(&pdev->dev, "ALSA ready: card=%d id=%s; 48 kHz S24_3LE stereo, stream limit=%u s (0=continuous); experimental desktop playback\n",
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
    finish_session(e);
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
    finish_session(e);
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
    pr_info(DRV ": begin desktop ALSA session\n");
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
MODULE_DESCRIPTION("HD Native PCIe + 192 desktop ALSA playback, 48 kHz stereo, experimental");
