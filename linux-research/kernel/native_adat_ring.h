/* SPDX-License-Identifier: GPL-2.0 */
/* Capture PCM extraction and optional independent TX test pattern.
 * Caller holds stream/io locks and performs DMA barriers before reading
 * RX and before publishing indices. Caller enforces a <80 ms poll gap. */
#ifndef NATIVE_ADAT_RING_H
#define NATIVE_ADAT_RING_H
/* DirectIO 26.4.1, TX RVA fc56 / RX ffe2: advance 32 bytes per
 * group of up to eight packed 24-bit samples, beginning at group byte 4.
 * Zero-based channel 8 (logical 9) is byte 36, NOT byte 28.
 * Bytes 28..31 and the next group's 32..35 are not PCM samples. */
#define NC_CHANNEL_OFFSET(ch) (((ch) / 8U) * 32U + 4U + ((ch) % 8U) * 3U)
#ifndef NC_RX_OFFSET
#define NC_RX_OFFSET NC_CHANNEL_OFFSET(0U)
#endif
#ifndef NC_TX_OFFSET
#define NC_TX_OFFSET NC_CHANNEL_OFFSET(0U)
#endif
#define NC_RX_FRAMES 16384U
#define NC_TX_FRAMES 8192U
#define NC_ALSA_FRAMES 4096U
#define NC_PERIOD 1024U
struct native_capture_ring {
    unsigned long long produced, taken;
    unsigned long appl;
    unsigned int hw;
};
static int nc_ack(struct native_capture_ring *r, unsigned long appl,
                  unsigned long boundary)
{
    unsigned long n;
    if (!boundary || boundary % NC_ALSA_FRAMES || appl >= boundary ||
        r->appl >= boundary || r->taken > r->produced)
        return -EINVAL;
    n = appl >= r->appl ? appl - r->appl : boundary - r->appl + appl;
    if (n > r->produced - r->taken)
        return -EPIPE;
    r->taken += n;
    r->appl = appl;
    return 0;
}
static int nc_pull(struct native_capture_ring *r, const unsigned char *rx,
                   unsigned char *pcm, unsigned int hw)
{
    unsigned int n, i;
    if (hw >= NC_RX_FRAMES || r->hw >= NC_RX_FRAMES ||
        r->taken > r->produced || r->produced - r->taken > NC_ALSA_FRAMES)
        return -EINVAL;
    n = (hw - r->hw) & (NC_RX_FRAMES - 1);
    /* Keep one frame free: a completely full ALSA ring has ambiguous pointer. */
    if (r->produced - r->taken + n >= NC_ALSA_FRAMES)
        return -EPIPE;
    for (i = 0; i < n; i++) {
        const unsigned char *src = rx + ((r->hw + i) % NC_RX_FRAMES) * 256 + NC_RX_OFFSET;
        unsigned char *dst = pcm + ((r->produced + i) % NC_ALSA_FRAMES) * 6;
        unsigned int j;
        for (j = 0; j < 6; j++) dst[j] = src[j];
    }
    r->produced += n;
    r->hw = hw;
    return (int)n;
}
static void nc_tx_fill(unsigned char *tx, unsigned long long start,
                       unsigned int count, int tone)
{
    static const int sine[64] = {0, 8222, 16365, 24351, 32102, 39544, 46605, 53217, 59316, 64845, 69749, 73981, 77501, 80274, 82274, 83482, 83886, 83482, 82274, 80274, 77501, 73981, 69749, 64845, 59316, 53217, 46605, 39544, 32102, 24351, 16365, 8222, 0, -8222, -16365, -24351, -32102, -39544, -46605, -53217, -59316, -64845, -69749, -73981, -77501, -80274, -82274, -83482, -83886, -83482, -82274, -80274, -77501, -73981, -69749, -64845, -59316, -53217, -46605, -39544, -32102, -24351, -16365, -8222};
    unsigned int i;
    for (i = 0; i < count; i++) {
        unsigned long long frame = start + i;
        unsigned int t = (unsigned int)(frame % 480000ULL), ch;
        unsigned char *dst = tx + (frame % NC_TX_FRAMES) * 256;
        memset(dst, 0, 256);
        /* 10 s: 1..3 s left 750 Hz; 4..6 s right 1500 Hz;
         * 7..9 s both. 10 ms ramps. Never copy captured data to TX. */
        for (ch = 0; ch < 2; ch++) {
            unsigned int begin = ch ? 192000 : 48000, end = begin + 96000;
            unsigned int ramp, value;
            int sample;
            if (t >= 336000 && t < 432000) { begin = 336000; end = 432000; }
            if (!tone || t < begin || t >= end) continue;
            ramp = t - begin;
            if (end - 1 - t < ramp) ramp = end - 1 - t;
            if (ramp > 480) ramp = 480;
            sample = sine[((t - begin) * (ch + 1)) % 64] * (int)ramp / 480;
            value = (unsigned int)sample;
            dst[NC_TX_OFFSET + ch*3] = value & 255;
            dst[NC_TX_OFFSET + 1 + ch*3] = (value >> 8) & 255;
            dst[NC_TX_OFFSET + 2 + ch*3] = (value >> 16) & 255;
        }
    }
}
#endif
