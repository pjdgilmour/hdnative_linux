/* SPDX-License-Identifier: GPL-2.0 */
#ifndef NATIVE_DUPLEX_RING_H
#define NATIVE_DUPLEX_RING_H
#define ND_ALSA 4096U
#define ND_TX 8192U
#define ND_RX 16384U
#define ND_PERIOD 1024U
struct nd_play {
    unsigned long long accepted, submitted, played, base;
    unsigned long appl;
};
static int nd_ack(struct nd_play *p, unsigned long appl, unsigned long boundary)
{
    unsigned long n;
    if (!boundary || boundary % ND_ALSA || appl >= boundary || p->appl >= boundary ||
        p->played > p->submitted || p->submitted > p->accepted)
        return -EINVAL;
    n = appl >= p->appl ? appl-p->appl : boundary-p->appl+appl;
    if (p->accepted-p->played+n > ND_ALSA) return -EPIPE;
    p->accepted += n; p->appl = appl;
    return 0;
}
static int nd_position(struct nd_play *p, unsigned long long consumed)
{
    unsigned long long n = consumed > p->base ? consumed-p->base : 0;
    if (p->played > p->submitted || p->submitted > p->accepted) return -EINVAL;
    if (n > p->submitted) n = p->submitted;
    if (n < p->played) return -EINVAL;
    p->played = n;
    return 0;
}
/* Always leaves queued TX contiguous. A joining playback stream starts AFTER
 * previously offered silence; its ALSA pointer stays zero through that lead. */
static int nd_refill(struct nd_play *p, unsigned char *tx, const unsigned char *pcm,
                     unsigned long long *queued, unsigned long long consumed,
                     int playing, int draining)
{
    unsigned int room, n, i;
    if (*queued < consumed || *queued-consumed > ND_ALSA) return -EPIPE;
    room = ND_ALSA - (unsigned int)(*queued-consumed);
    n = room;
    if (playing) {
        if (!pcm || p->submitted > p->accepted ||
            p->accepted-p->played > ND_ALSA || p->base+p->submitted > *queued)
            return -EINVAL;
        if (p->accepted-p->submitted < n) n = (unsigned int)(p->accepted-p->submitted);
        /* No data may follow a published draining tail. */
        if (n && *queued != p->base+p->submitted) return -EPIPE;
        for (i=0;i<n;i++) {
            unsigned char *dst=tx+((*queued+i)%ND_TX)*256;
            const unsigned char *src=pcm+((p->submitted+i)%ND_ALSA)*6;
            memset(dst,0,256); memcpy(dst+4,src,6);
        }
        p->submitted += n; *queued += n;
        room -= n;
        if (!draining) return 0;
    }
    for (i=0;i<room;i++) memset(tx+((*queued+i)%ND_TX)*256,0,256);
    *queued += room;
    return 0;
}
#endif
