/* SPDX-License-Identifier: GPL-2.0 */
/* Fixed 48 kHz stereo S24_3LE staging ring -> HD Native 256-byte frames.
 * Caller serializes access, supplies errno and memset, and publishes DMA
 * writes only after a write barrier. No hardware or ALSA dependencies here.
 */
#ifndef NATIVE_PCM_RING_H
#define NATIVE_PCM_RING_H
#define NATIVE_ALSA_FRAMES 4096U
#define NATIVE_HW_FRAMES 8192U
#define NATIVE_PERIOD_FRAMES 1024U
#define NATIVE_FRAME_BYTES 256U
#define NATIVE_PCM_BYTES 6U
struct native_pcm_ring {
    unsigned long long queued, consumed;
    unsigned long appl;
    unsigned int hw;
};

static int native_ring_push(struct native_pcm_ring *r, unsigned char *tx,
                            const unsigned char *pcm, unsigned long appl,
                            unsigned long boundary)
{
    unsigned long count, i;
    if (!boundary || boundary % NATIVE_ALSA_FRAMES || appl >= boundary ||
        r->appl >= boundary || r->consumed > r->queued)
        return -EINVAL;
    count = appl >= r->appl ? appl - r->appl : boundary - r->appl + appl;
    if (count > NATIVE_ALSA_FRAMES ||
        r->queued - r->consumed + count > NATIVE_ALSA_FRAMES)
        return -EPIPE; /* Includes unsupported rewinds/forwards. */
    for (i = 0; i < count; i++) {
        unsigned int j;
        unsigned char *dst = tx + ((r->queued + i) % NATIVE_HW_FRAMES) * NATIVE_FRAME_BYTES;
        const unsigned char *src = pcm + ((r->appl + i) % NATIVE_ALSA_FRAMES) * NATIVE_PCM_BYTES;
        memset(dst, 0, NATIVE_FRAME_BYTES);
        for (j = 0; j < NATIVE_PCM_BYTES; j++)
            dst[4 + j] = src[j];
    }
    r->queued += count;
    r->appl = appl;
    return (int)count;
}

static int native_ring_advance(struct native_pcm_ring *r, unsigned char *tx,
                               unsigned int hw, int draining)
{
    unsigned int count, i;
    unsigned long long available;
    if (hw >= NATIVE_HW_FRAMES || r->consumed > r->queued)
        return -EINVAL;
    count = (hw - r->hw) & (NATIVE_HW_FRAMES - 1);
    available = r->queued - r->consumed;
    if (available > NATIVE_ALSA_FRAMES)
        return -EINVAL;
    if (count > available) {
        if (!draining)
            return -EPIPE;
        /* At EOF report only submitted PCM. Unsubmitted frames remain zero.
         * Caller must stop on the same poll when consumed reaches queued.
         */
        count = (unsigned int)available;
    }
    for (i = 0; i < count; i++)
        memset(tx + ((r->consumed + i) % NATIVE_HW_FRAMES) * NATIVE_FRAME_BYTES,
               0, NATIVE_FRAME_BYTES);
    r->consumed += count;
    r->hw = hw;
    return (int)count;
}
#endif
