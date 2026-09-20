#!/usr/bin/env python3
"""Exercise the exact kernel control helper with a simulated DigiLink endpoint.

No PCI, sudo, or module loading. Faults include applied writes with lost ACKs.
"""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "native_192_control.h"

enum fault { NONE, LOST_UNMUTE_ACK, IGNORE_UNMUTE, IGNORE_RESTORE,
             BAD_NEUTRAL, LOST_READBACK, OTHER_CONTROL_CHANGED,
             LOST_ROUTE_ACK, IGNORE_ROUTE, ROUTE_WRITE_ONLY, IGNORE_ROUTE_RESTORE };
struct sim {
    unsigned int tx, rx, regs[256], writes, unmute_writes, restore_writes;
    unsigned long long now;
    enum fault fault;
    int changed;
    unsigned int route_on, route_off;
};
static unsigned int read_reg(void *ctx, unsigned int off)
{
    struct sim *h = ctx;
    assert(off == 0x7001c || off == 0x70040);
    return off == 0x7001c ? h->tx : h->rx;
}
static void write_reg(void *ctx, unsigned int off, unsigned int value)
{
    struct sim *h = ctx;
    unsigned int cmd = value & 0xffffff, reg = (cmd >> 8) & 255;
    assert(off == 0x7001c && (value & 0xff000000) == 0xa5000000);
    h->writes++;
    h->tx = value;
    if (!cmd) {
        if (h->fault != BAD_NEUTRAL || !h->changed)
            h->rx = 0;
        return;
    }
    if (cmd & 0x800000) {
        if (reg == 0x4d) {
            assert(cmd == 0x814d00 || cmd == 0x814d01);
            if (cmd & 1) {
                assert(h->regs[0] == 2); /* Install route while still muted. */
                h->route_on++;
                if (h->fault != IGNORE_ROUTE) h->regs[reg] = 1;
                if (h->fault == LOST_ROUTE_ACK) return;
            } else {
                h->route_off++;
                if (h->fault != IGNORE_ROUTE_RESTORE) h->regs[reg] = 0;
            }
            h->rx = 0x814d00;
            return;
        }
        assert(cmd == 0x810000 || cmd == 0x810002);
        if (!(cmd & 255)) {
            h->unmute_writes++;
            h->changed = 1;
            if (h->fault != IGNORE_UNMUTE)
                h->regs[0] = 0;
            if (h->fault == OTHER_CONTROL_CHANGED)
                h->regs[1] = 8;
            if (h->fault == LOST_UNMUTE_ACK)
                return;
        } else {
            h->restore_writes++;
            if (h->fault != IGNORE_RESTORE)
                h->regs[0] = 2;
        }
        h->rx = 0x810000; /* ACK low byte need not echo the written value. */
        return;
    }
    assert((cmd >> 16) == 1 && !(cmd & 255));
    assert(reg <= 3 || (reg >= 0x10 && reg <= 0x17) || (reg >= 0x40 && reg <= 0x5d));
    if (h->fault == LOST_READBACK && h->changed && !h->restore_writes)
        return;
    h->rx = cmd | h->regs[reg];
    if (h->fault == ROUTE_WRITE_ONLY && reg >= 0x40 && reg <= 0x5d)
        h->rx = cmd;
}
static unsigned long long now_us(void *ctx) { return ((struct sim *)ctx)->now; }
static void pause_sim(void *ctx) { ((struct sim *)ctx)->now += 50; }
static void init(struct sim *h, struct native_192 *s, enum fault fault)
{
    memset(h, 0, sizeof(*h));
    h->fault = fault;
    h->tx = 0xa5000000;
    h->regs[0] = 2;
    h->regs[0x10] = 1; h->regs[0x11] = 0x49;
    h->regs[0x12] = 1; h->regs[0x13] = 1;
    h->regs[0x14] = 0x14; h->regs[0x15] = 0x13;
    h->regs[0x16] = 0x15; h->regs[0x17] = 0x13;
    *s = (struct native_192) { .ctx=h, .read=read_reg, .write=write_reg,
        .now_us=now_us, .pause=pause_sim, .before=-1, .during=-1, .after=-1,
        .route_before=-1, .route_during=-1, .route_after=-1 };
}
int main(void)
{
    struct sim h;
    struct native_192 s;
    unsigned int reg, value, bad_regs[] = {0,1,2,3,0x10,0x11,0x12,0x13,0x14,0x15,0x16,0x17};
    init(&h,&s,NONE);
    assert(!n192_unmute(&s));
    assert(s.before==2 && s.during==0 && s.restore_required && s.write_attempted);
    assert(h.unmute_writes==1 && !h.restore_writes && h.regs[0]==0);
    assert(!n192_check_unmuted(&s));
    assert(!n192_restore(&s));
    assert(s.after==2 && s.restored && !s.restore_required && h.regs[0]==2);
    assert(h.restore_writes==1);
    assert(!n192_restore(&s) && h.restore_writes==1); /* Idempotent cleanup. */

    for (reg=0;reg<sizeof(bad_regs)/sizeof(bad_regs[0]);reg++) {
        init(&h,&s,NONE);
        h.regs[bad_regs[reg]] ^= 4;
        assert(n192_unmute(&s)==-EPROTO);
        assert(!s.write_attempted && !h.unmute_writes);
        assert(!n192_restore(&s) && !h.restore_writes);
    }
    init(&h,&s,NONE);
    h.tx |= 0x11000;
    assert(n192_unmute(&s)==-EBUSY && h.writes==0);
    init(&h,&s,NONE);
    h.rx = 0x11001;
    assert(n192_unmute(&s)==-EBUSY && h.writes==0);

    init(&h,&s,LOST_UNMUTE_ACK);
    assert(n192_unmute(&s)==-ETIMEDOUT && h.now==100000);
    assert(s.restore_required && h.regs[0]==0);
    assert(!n192_restore(&s) && s.restored && h.regs[0]==2);
    init(&h,&s,IGNORE_UNMUTE);
    assert(n192_unmute(&s)==-EPROTO);
    assert(!n192_restore(&s) && s.restored);
    init(&h,&s,LOST_READBACK);
    assert(n192_unmute(&s)==-ETIMEDOUT);
    assert(!n192_restore(&s) && s.restored);
    init(&h,&s,OTHER_CONTROL_CHANGED);
    assert(n192_unmute(&s)==-EPROTO);
    assert(!n192_restore(&s) && s.restored);
    init(&h,&s,IGNORE_RESTORE);
    assert(!n192_unmute(&s));
    assert(n192_restore(&s)==-EPROTO && !s.restored && s.restore_required);
    assert(h.restore_writes==3 && h.regs[0]==0);
    init(&h,&s,BAD_NEUTRAL);
    assert(n192_unmute(&s)==-EIO && s.restore_required);
    assert(n192_restore(&s)==-EBUSY && !s.restored);
    assert(!h.restore_writes); /* Do not overwrite the stale command response. */

    init(&h,&s,NONE);
    for (reg=0;reg<256;reg++) {
        value=3;
        assert(n192_xfer(&s,reg,1,&value)==-EINVAL);
        if (reg) {
            value=0;
            assert(n192_xfer(&s,reg,1,&value)==-EINVAL);
        }
        if (!(reg<=3 || (reg>=0x10 && reg<=0x17))) {
            value=0;
            assert(n192_xfer(&s,reg,0,&value)==-EINVAL);
        }
    }
    assert(h.writes==0);
    init(&h,&s,NONE); s.route_enabled=1;
    assert(!n192_route_enable(&s));
    assert(s.route_before==0 && s.route_during==1 && h.regs[0]==2);
    assert(h.route_on==1 && s.route_write_attempted && !s.write_attempted);
    assert(!n192_unmute(&s) && h.regs[0]==0);
    assert(!n192_check_route(&s,1,&s.route_during));
    assert(!n192_restore(&s) && h.regs[0]==2);
    assert(!n192_route_restore(&s) && h.regs[0x4d]==0);
    assert(s.route_after==0 && s.route_restored && !s.route_restore_required);
    assert(!n192_route_restore(&s) && h.route_off==1);

    for (reg=0x40;reg<=0x5d;reg++) {
        init(&h,&s,NONE); s.route_enabled=1; h.regs[reg]=7;
        assert(n192_route_enable(&s)==-EPROTO);
        assert(!h.route_on && !s.route_write_attempted && !s.write_attempted);
        assert(!n192_route_restore(&s) && !h.route_off && h.regs[reg]==7);
    }
    init(&h,&s,LOST_ROUTE_ACK); s.route_enabled=1;
    assert(n192_route_enable(&s)==-ETIMEDOUT && h.regs[0x4d]==1);
    assert(s.route_restore_required && !s.write_attempted);
    assert(!n192_route_restore(&s) && s.route_restored && h.regs[0x4d]==0);
    init(&h,&s,IGNORE_ROUTE); s.route_enabled=1;
    assert(n192_route_enable(&s)==-EPROTO && h.regs[0]==2);
    assert(!n192_route_restore(&s) && s.route_restored);
    init(&h,&s,ROUTE_WRITE_ONLY); s.route_enabled=1;
    assert(n192_route_enable(&s)==-EPROTO && h.regs[0x4d]==1 && h.regs[0]==2);
    assert(!n192_route_restore(&s) && h.regs[0x4d]==0);
    init(&h,&s,IGNORE_ROUTE_RESTORE); s.route_enabled=1;
    assert(!n192_route_enable(&s));
    assert(n192_route_restore(&s)==-EPROTO && !s.route_restored && h.route_off==3);
    init(&h,&s,LOST_UNMUTE_ACK); s.route_enabled=1;
    assert(!n192_route_enable(&s));
    assert(n192_unmute(&s)==-ETIMEDOUT);
    assert(!n192_restore(&s) && !n192_route_restore(&s));
    assert(h.regs[0]==2 && h.regs[0x4d]==0 && s.restored && s.route_restored);
    init(&h,&s,NONE); s.route_enabled=1;
    for (reg=0;reg<256;reg++) {
        value=2;
        if (reg) assert(n192_xfer(&s,reg,1,&value)==-EINVAL);
        value=1;
        if (reg!=0x4d) assert(n192_xfer(&s,reg,1,&value)==-EINVAL);
    }
    assert(!h.writes);
    puts("PASS: route 00->01->00, muted setup, strict existing-route refusal, lost route/mute ACK recovery, ignored/write-only routing, restoration failure");
    puts("PASS: strict preflight, 02->00->02 readback, lost ACK recovery, ignored writes, readback/cleanup failures, bounded retries, command allowlist");
}
'''
with tempfile.TemporaryDirectory(prefix="native-192-control-") as d:
    p = Path(d)
    (p / "test.c").write_text(source)
    subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                    "-I" + str(root / "kernel"), str(p / "test.c"),
                    "-o", str(p / "test")], check=True)
    subprocess.run([str(p / "test")], check=True, timeout=5)
