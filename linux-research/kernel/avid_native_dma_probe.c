// SPDX-License-Identifier: GPL-2.0
/* Bounded silence/tone experiment, not an ALSA driver.
 * Register evidence: DSI RVAs 19c8f0 (DMA), 19f2b0 (start), 19f4b0 (stop).
 * Unlike DSI, this experiment leaves all interrupt sources masked and polls.
 * Optional unmute_192 changes bank 1 control 0 from 0x02 to 0x00 temporarily.
 * Optional route_192 temporarily selects the first DA routing entry.
 * No firmware load or clock changes.
 */
#include <linux/module.h>
#include <linux/pci.h>
#include <linux/dma-mapping.h>
#include <linux/delay.h>
#include <linux/ktime.h>
#include <linux/slab.h>
#include "native_tone.h"
#include "native_192_control.h"

#define DRV "avid_native_dma_probe"
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

static bool run_silence;
module_param(run_silence, bool, 0400);
MODULE_PARM_DESC(run_silence, "Required explicit opt-in: 20 ms of zero PCM");
static bool run_tone;
module_param(run_tone, bool, 0400);
MODULE_PARM_DESC(run_tone, "Five short -40 dBFS tone bursts on logical outputs 1-2");
static bool tone_long;
module_param(tone_long, bool, 0400);
MODULE_PARM_DESC(tone_long, "With run_tone only: 6144 tone frames (128 ms at 48 kHz), no refill");
static bool unmute_192;
module_param(unmute_192, bool, 0400);
MODULE_PARM_DESC(unmute_192, "With long tone only: verify known 192 state, temporarily clear control bit 1, restore afterward");
static bool route_192;
module_param(route_192, bool, 0400);
MODULE_PARM_DESC(route_192, "With unmute_192 only: temporarily set bank 1 routing register 0x4d to 1, verify and restore 0");
static bool route_write_attempted, route_restored;
module_param(route_write_attempted, bool, 0444);
module_param(route_restored, bool, 0444);
static int route_before = -1, route_during = -1, route_after = -1;
module_param(route_before, int, 0444);
module_param(route_during, int, 0444);
module_param(route_after, int, 0444);
static bool mute_write_attempted, mute_restored;
module_param(mute_write_attempted, bool, 0444);
module_param(mute_restored, bool, 0444);
static int control_before = -1, control_during = -1, control_after = -1;
module_param(control_before, int, 0444);
module_param(control_during, int, 0444);
module_param(control_after, int, 0444);
static char *bdf = "0000:81:00.0";
module_param(bdf, charp, 0400);
static int result = -ENODEV;
module_param(result, int, 0444);
/* result 0 means TX MMIO progress in every burst, NOT verified analog output. */
static uint tx_consumed, rx_produced, status_sequence;
module_param(tx_consumed, uint, 0444);
module_param(rx_produced, uint, 0444);
module_param(status_sequence, uint, 0444);
static bool pci_restored;
module_param(pci_restored, bool, 0444);
static uint tx_mmio_first, tx_mmio_last, tx_mmio_changes;
module_param(tx_mmio_first, uint, 0444);
module_param(tx_mmio_last, uint, 0444);
module_param(tx_mmio_changes, uint, 0444);

/* Every ordinary register modified, for restoration after DMA is disabled.
 * Do not include write-one-to-clear registers: this probe does not write them.
 */
static const u32 saved_offsets[] = {
    CTL, RESET, 0x44, DL_CTL, DL_IRQ_MASK, DMA_CTL, 0x42008,
    0x40918, 0x40958, 0x41118, 0x41158, 0x4093c, 0x4097c,
    0x40818, 0x40858, 0x40898, 0x408d8, 0x40000,
    0x41018, 0x41058, 0x41098, 0x410d8, 0x40400,
    0x4083c, 0x4087c, 0x408bc, 0x408fc, 0x40004, 0x40404, 0x40008,
};
struct experiment {
    struct pci_dev *pdev;
    void __iomem *bar;
    void *tx, *rx, *status;
    dma_addr_t tx_dma, rx_dma, status_dma;
    u16 command;
    u32 saved[ARRAY_SIZE(saved_offsets)];
    bool enabled, regions, configured;
    struct native_192 peripheral;
};

static u32 rd(struct experiment *e, u32 off)
{
    return readl(e->bar + off);
}
static void wr(struct experiment *e, u32 off, u32 value)
{
    writel(value, e->bar + off);
}
static void flush(struct experiment *e)
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
static void restore_peripheral(struct experiment *e)
{
    int err;
    if (!unmute_192)
        return;
    err = n192_restore(&e->peripheral);
    control_before = e->peripheral.before;
    control_during = e->peripheral.during;
    control_after = e->peripheral.after;
    mute_write_attempted = e->peripheral.write_attempted;
    mute_restored = e->peripheral.restored;
    dev_info(&e->pdev->dev,
             "192 control0: before=%d during=%d after=%d write_attempted=%u restored=%u restore_result=%d\n",
             control_before, control_during, control_after,
             mute_write_attempted, mute_restored, err);
    if (err) {
        result = err;
        dev_err(&e->pdev->dev,
                "192 control restoration NOT confirmed; stop experiments and preserve this log.\n");
    }
    if (route_192) {
        /* Restore mute before removing the route. Still attempt route cleanup
         * when mute restoration fails; both failures are reported separately.
         */
        err = n192_route_restore(&e->peripheral);
        route_before = e->peripheral.route_before;
        route_during = e->peripheral.route_during;
        route_after = e->peripheral.route_after;
        route_write_attempted = e->peripheral.route_write_attempted;
        route_restored = e->peripheral.route_restored;
        dev_info(&e->pdev->dev,
                 "192 route4d: before=%d during=%d after=%d write_attempted=%u restored=%u restore_result=%d\n",
                 route_before, route_during, route_after,
                 route_write_attempted, route_restored, err);
        if (err) {
            result = err;
            dev_err(&e->pdev->dev, "192 routing restoration NOT confirmed; stop experiments and preserve this log.\n");
        }
    }
}

static void setup_dma(struct experiment *e)
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

static void sample_status(struct experiment *e)
{
    unsigned int i;
    dma_rmb();
    for (i = 0; i < 4; i++) {
        __le32 *s = (__le32 *)(e->status + i * 256);
        u32 seq = le32_to_cpu(READ_ONCE(s[8]));
        u32 tx = le32_to_cpu(READ_ONCE(s[1])) & 0x1fff;
        u32 rx = le32_to_cpu(READ_ONCE(s[0])) & 0x3fff;
        if (seq > status_sequence) status_sequence = seq;
        if (tx > tx_consumed) tx_consumed = tx;
        if (rx > rx_produced) rx_produced = rx;
    }
}

static int transfer_pcm(struct experiment *e)
{
    ktime_t deadline;
    unsigned int initial_changes = tx_mmio_changes;
    /* 8191 queued frames, including a silent tail for tone mode.
     * Longer mode stops at TX >= 7168 or 160 ms, whichever is observed first.
     * No refill, capture processing, or long-running stream. Polling is not
     * a hard real-time deadline; scheduling stalls can delay the stop.
     */
    dma_wmb();
    pci_set_master(e->pdev);
    wr(e, 0x41018, 8191);
    wr(e, DMA_CTL, rd(e, DMA_CTL) | DMA_ENABLE);
    wr(e, DL_CTL, rd(e, DL_CTL) | 0x100); /* Enable logical slot pair 0. */
    flush(e);
    usleep_range(50, 100);
    wr(e, CTL, rd(e, CTL) | STREAM_ENABLE);
    flush(e);
    tx_mmio_first = rd(e, 0x41058);
    tx_mmio_last = tx_mmio_first;
    deadline = ktime_add_ms(ktime_get(), tone_long ? 160 : run_tone ? 40 : 20);
    do {
        u32 pos = rd(e, 0x41058);
        if (pos != tx_mmio_last) tx_mmio_changes++;
        tx_mmio_last = pos;
        sample_status(e);
        if (tone_long && (pos & 0x1fff) >= 7168)
            break;
        usleep_range(1000, 1500);
    } while (ktime_before(ktime_get(), deadline));
    sample_status(e);
    dev_info(&e->pdev->dev,
             "%s: tx_consumed=%u rx_produced=%u status_sequence=%u; registers tx=%08x rx=%08x link=%08x\n",
             run_tone ? "tone" : "silence", tx_consumed, rx_produced, status_sequence,
             rd(e, 0x41058), rd(e, 0x40818), rd(e, DL_STATUS));
    /* The status DMA snapshot can stay at TX=0 or 9 while MMIO advances.
     * Require progress in this burst; an earlier burst cannot mask a stall.
     */
    return tx_mmio_changes != initial_changes ? 0 : -ETIMEDOUT;
}

static bool stop_dma(struct experiment *e)
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

static int probe(struct pci_dev *pdev, const struct pci_device_id *id)
{
    struct experiment *e;
    u16 command;
    int err, i;
    bool drained;
    (void)id;
    if (strcmp(pci_name(pdev), bdf)) return -ENODEV;
    if (pdev->subsystem_vendor != 0x11af || pdev->subsystem_device != 0xef80)
        return -ENODEV;
    if (pci_resource_len(pdev, 0) != 0x400000) return -ENODEV;
    e = kzalloc(sizeof(*e), GFP_KERNEL);
    if (!e) { result = -ENOMEM; return -ENOMEM; }
    e->pdev = pdev;
    e->peripheral = (struct native_192) {
        .ctx = e, .read = peripheral_read, .write = peripheral_write,
        .now_us = peripheral_now, .pause = peripheral_pause,
        .before = -1, .during = -1, .after = -1,
        .route_enabled = route_192,
        .route_before = -1, .route_during = -1, .route_after = -1,
    };
    err = pci_read_config_word(pdev, PCI_COMMAND, &e->command);
    if (err) { result = -EIO; goto out; }
    if (e->command & PCI_COMMAND_MASTER) { result = -EBUSY; goto out; }
    err = pci_enable_device_mem(pdev);
    if (err) { result = err; goto out; }
    e->enabled = true;
    pci_clear_master(pdev);
    pci_intx(pdev, 0);
    err = pci_request_regions(pdev, DRV);
    if (err) { result = err; goto out; }
    e->regions = true;
    e->bar = pci_iomap(pdev, 0, 0x71000);
    if (!e->bar) { result = -ENOMEM; goto out; }
    dev_info(&pdev->dev,
             "initial id=%08x fw=%08x ctl=%08x reset=%08x linkctl=%08x linkstatus=%08x dmactl=%08x irqmask=%08x dmairq=%08x\n",
             rd(e, 0), rd(e, 4), rd(e, CTL), rd(e, RESET),
             rd(e, DL_CTL), rd(e, DL_STATUS), rd(e, DMA_CTL),
             rd(e, DL_IRQ_MASK), rd(e, 0x42008));
    if (rd(e, 0) != 0xd400 || rd(e, 4) != 0x01050040 ||
        !(rd(e, DL_STATUS) & 1) || !(rd(e, DL_STATUS) & 0x100)) {
        result = -ENOLINK; goto out;
    }
    /* Require the exact quiet state observed during successful 192 ID.
     * No experiment over an existing stream or DMA configuration.
     */
    if (rd(e, CTL) != 0xa00 || rd(e, RESET) || rd(e, DL_CTL) ||
        rd(e, DMA_CTL) || rd(e, DL_IRQ_MASK) || rd(e, 0x42008)) {
        result = -EBUSY; goto out;
    }
    for (i = 7; i <= 12; i++)
        if (rd(e, saved_offsets[i])) { result = -EBUSY; goto out; }
    err = dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(32));
    if (err) { result = err; goto out; }
    e->tx = dma_alloc_coherent(&pdev->dev, TX_BYTES, &e->tx_dma, GFP_KERNEL);
    e->rx = dma_alloc_coherent(&pdev->dev, RX_BYTES, &e->rx_dma, GFP_KERNEL);
    e->status = dma_alloc_coherent(&pdev->dev, STATUS_BYTES, &e->status_dma, GFP_KERNEL);
    if (!e->tx || !e->rx || !e->status) { result = -ENOMEM; goto out; }
    if ((e->tx_dma | e->rx_dma | e->status_dma) & 255) {
        result = -EINVAL; goto out;
    }
    memset(e->tx, 0, TX_BYTES);
    memset(e->rx, 0, RX_BYTES);
    memset(e->status, 0, STATUS_BYTES);
    for (i = 0; i < ARRAY_SIZE(saved_offsets); i++)
        e->saved[i] = rd(e, saved_offsets[i]);
    if (run_tone) native_fill_tone(e->tx, tone_long);
    if (route_192) {
        err = n192_route_enable(&e->peripheral);
        if (err) {
            dev_err(&pdev->dev, "192 route verification failed: %d; no audio started.\n", err);
            result = err;
            goto out;
        }
    }
    if (unmute_192) {
        err = n192_unmute(&e->peripheral);
        if (err) {
            dev_err(&pdev->dev, "192 preflight/unmute verification failed: %d; no audio started.\n", err);
            result = err;
            goto out;
        }
        msleep(20);
    }
    e->configured = true;
    for (i = 0; i < (run_tone ? 5 : 1); i++) {
        if (i) {
            if (!stop_dma(e)) {
                result = -EBUSY;
                goto out;
            }
            memset(e->status, 0, STATUS_BYTES);
            msleep(300);
        }
        setup_dma(e);
        if (unmute_192) {
            err = n192_check_unmuted(&e->peripheral);
            if (err) {
                result = err;
                goto out;
            }
        }
        if (route_192) {
            err = n192_check_route(&e->peripheral, 1, &e->peripheral.route_during);
            if (err) {
                result = err;
                goto out;
            }
        }
        err = transfer_pcm(e);
        if (err) {
            result = err;
            goto out;
        }
    }
    result = 0;
out:
    drained = !e->configured || stop_dma(e);
    /* Even if DMA cannot drain, try to restore mute before quarantine.
     * A lost command ACK also requires restoration; audio never starts then.
     */
    restore_peripheral(e);
    if (e->configured) {
        if (!drained) {
            result = -EBUSY;
            __module_get(THIS_MODULE);
            pci_dev_get(pdev);
            dev_err(&pdev->dev, "DMA drain failed; buffers and module pinned. Reboot required before retry.\n");
            return -EBUSY; /* Deliberate quarantine: do not free DMA buffers. */
        }
        for (i = ARRAY_SIZE(saved_offsets) - 1; i >= 0; i--)
            wr(e, saved_offsets[i], e->saved[i]);
        flush(e);
    }
    if (e->status) dma_free_coherent(&pdev->dev, STATUS_BYTES, e->status, e->status_dma);
    if (e->rx) dma_free_coherent(&pdev->dev, RX_BYTES, e->rx, e->rx_dma);
    if (e->tx) dma_free_coherent(&pdev->dev, TX_BYTES, e->tx, e->tx_dma);
    if (e->bar) pci_iounmap(pdev, e->bar);
    if (e->regions) pci_release_regions(pdev);
    if (e->enabled) {
        pci_disable_device(pdev);
        pci_write_config_word(pdev, PCI_COMMAND, e->command);
        pci_restored = !pci_read_config_word(pdev, PCI_COMMAND, &command) && command == e->command;
    }
    dev_info(&pdev->dev, "bounded DMA experiment result=%d PCI_restored=%u\n", result, pci_restored);
    kfree(e);
    return -ENODEV; /* Experiment finished; do not remain bound. */
}

static const struct pci_device_id ids[] = {
    { PCI_DEVICE(0x11af, 0xef80) }, { 0 }
};
/* Deliberately no MODULE_DEVICE_TABLE: this experiment must not autoload. */
static struct pci_driver driver = { .name = DRV, .id_table = ids, .probe = probe };
static int __init experiment_init(void)
{
    int err;
    if (run_silence == run_tone) return -EINVAL;
    if (tone_long && !run_tone) return -EINVAL;
    if (unmute_192 && (!run_tone || !tone_long)) return -EINVAL;
    if (route_192 && !unmute_192) return -EINVAL;
    err = pci_register_driver(&driver);
    if (err) return err;
    pci_unregister_driver(&driver);
    pr_info(DRV ": finished. result=%d; mode=%s; not an ALSA device; analog output requires external confirmation.\n",
            result, run_tone ? (tone_long ? "tone-128ms-at-48k" : "tone-21ms-at-48k") : "silence");
    return 0;
}
static void __exit experiment_exit(void) { }
module_init(experiment_init);
module_exit(experiment_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Bounded Avid HD Native PCIe DMA silence/tone research probe");
