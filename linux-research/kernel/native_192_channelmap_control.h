/* SPDX-License-Identifier: GPL-2.0 */
/* Bounded analog pair mapping: capture bank1 reg41=9..12;
 * playback bank1 reg4d..50 (DA module1) or reg55..58 (DA module3)=1.
 * Never configures digital, input level/trim, firmware, or clock.
 * Each profile requires an initially zero route table and restores both
 * selected routes after ANY write attempt, including lost ACKs. */
#ifndef NATIVE_192_CHANNELMAP_CONTROL_H
#define NATIVE_192_CHANNELMAP_CONTROL_H
struct native_192 {
    void *ctx;
    unsigned int (*read)(void *, unsigned int);
    void (*write)(void *, unsigned int, unsigned int);
    unsigned long long (*now_us)(void *);
    void (*pause)(void *);
    int before, during, after;
    int restore_required, write_attempted, restored;
    unsigned int input_pair, output_pair; /* 1..4 AD, 1..8 DA pairs */
    int route_enabled, route_before, route_during, route_after;
    int route_restore_required, route_write_attempted, route_restored;
};

/* Same 192 module IDs as the validated stereo experiment. The first
 * logical pair is mapped to ONE physical AD pair and ONE DA pair. */
static int n192_profile_valid(struct native_192 *s)
{
    return s->input_pair >= 1 && s->input_pair <= 4 &&
           s->output_pair >= 1 && s->output_pair <= 8;
}
static unsigned int n192_output_reg(struct native_192 *s)
{
    return s->output_pair <= 4 ? 0x4c + s->output_pair : 0x50 + s->output_pair;
}

static int n192_wait(struct native_192 *s, unsigned int header,
                     unsigned int *response)
{
    unsigned long long start = s->now_us(s->ctx);
    unsigned int i;
    for (i = 0; i < 2001; i++) {
        *response = s->read(s->ctx, 0x70040) & 0xffffff;
        if ((*response & 0xffff00) == header)
            return 0;
        if (s->now_us(s->ctx) - start >= 100000)
            break;
        s->pause(s->ctx);
    }
    return -ETIMEDOUT;
}

static int n192_xfer(struct native_192 *s, unsigned int reg, int write,
                     unsigned int *value)
{
    unsigned int tx, command, response = 0, idle;
    int ret, cleanup;
    int route_reg = s->route_enabled && reg >= 0x40 && reg <= 0x5d;
    int control_write = reg == 0 && (*value == 0 || *value == 2);
    int route_write = s->route_enabled && ((reg == n192_output_reg(s) && *value <= 1) ||
                      (reg == 0x41 && (*value == 0 || *value == 8 + s->input_pair)));
    if (!n192_profile_valid(s)) return -EINVAL;
    if (write ? !(control_write || route_write) :
                !(reg <= 3 || (reg >= 0x10 && reg <= 0x17) || route_reg))
        return -EINVAL;
    tx = s->read(s->ctx, 0x7001c);
    if ((tx & 0xffffff) || (s->read(s->ctx, 0x70040) & 0xffff00))
        return -EBUSY;
    command = 0x010000 | (reg << 8);
    if (write) {
        command |= 0x800000 | *value;
        /* A lost ACK does not mean that the peripheral ignored the write. */
        if (reg == 0) {
            s->restore_required = 1;
            s->write_attempted = 1;
        } else {
            s->route_restore_required = 1;
            s->route_write_attempted = 1;
        }
    }
    s->write(s->ctx, 0x7001c, (tx & 0xff000000) | command);
    ret = n192_wait(s, command & 0xffff00, &response);
    if (!ret && !write)
        *value = response & 255;
    tx = s->read(s->ctx, 0x7001c);
    s->write(s->ctx, 0x7001c, tx & 0xff000000);
    cleanup = n192_wait(s, 0, &idle);
    if (cleanup || (s->read(s->ctx, 0x7001c) & 0xffffff))
        return -EIO;
    return ret;
}

static int n192_expect(struct native_192 *s, unsigned int reg,
                       unsigned int expected, int *observed)
{
    unsigned int value = 0;
    int ret = n192_xfer(s, reg, 0, &value);
    if (ret)
        return ret;
    if (observed)
        *observed = (int)value;
    return value == expected ? 0 : -EPROTO;
}

static int n192_check_unmuted(struct native_192 *s)
{
    unsigned int pass, reg;
    int ret;
    for (pass = 0; pass < 2; pass++) {
        ret = n192_expect(s, 0, 0, &s->during);
        if (ret)
            return ret;
        for (reg = 1; reg <= 3; reg++) {
            ret = n192_expect(s, reg, 0, 0);
            if (ret)
                return ret;
        }
    }
    return 0;
}

static int n192_preflight(struct native_192 *s)
{
    /* Exact observations from --inspect-192, not defaults for other units. */
    static const unsigned int regs[] = {0x10, 0x14, 0x15, 0x16, 0x17,
                                        0x11, 0x12, 0x13, 0, 1, 2, 3};
    static const unsigned int values[] = {1, 0x14, 0x13, 0x15, 0x13,
                                          0x49, 1, 1, 2, 0, 0, 0};
    unsigned int i, pass;
    int ret;
    for (pass = 0; pass < 2; pass++) {
        for (i = 0; i < sizeof(regs) / sizeof(regs[0]); i++) {
            ret = n192_expect(s, regs[i], values[i],
                              regs[i] == 0 ? &s->before : 0);
            if (ret)
                return ret;
        }
    }
    return 0;
}

static int n192_unmute(struct native_192 *s)
{
    unsigned int value = 0;
    int ret = n192_preflight(s);
    if (ret)
        return ret;
    ret = n192_xfer(s, 0, 1, &value);
    if (ret)
        return ret;
    return n192_check_unmuted(s);
}

static int n192_restore(struct native_192 *s)
{
    unsigned int attempt, pass, value;
    int ret = 0;
    if (!s->restore_required)
        return 0;
    if (s->before != 2)
        return -EINVAL;
    /* At most three attempts. Never write over an outstanding transaction. */
    for (attempt = 0; attempt < 3; attempt++) {
        value = (unsigned int)s->before;
        ret = n192_xfer(s, 0, 1, &value);
        if (ret)
            continue;
        for (pass = 0; pass < 2; pass++) {
            ret = n192_expect(s, 0, value, &s->after);
            if (ret)
                break;
        }
        if (!ret) {
            s->restored = 1;
            s->restore_required = 0;
            return 0;
        }
    }
    return ret;
}

static int n192_check_route(struct native_192 *s, unsigned int expected,
                            int *observed)
{
    unsigned int pass, reg;
    int ret;
    if (!s->route_enabled)
        return -EINVAL;
    for (pass = 0; pass < 2; pass++) {
        for (reg = 0x40; reg <= 0x5d; reg++) {
            ret = n192_expect(s, reg, reg == 0x41 ? (expected ? 8 + s->input_pair : 0) : (reg == n192_output_reg(s) ? expected : 0),
                              reg == n192_output_reg(s) ? observed : 0);
            if (ret)
                return ret;
        }
    }
    return 0;
}

static int n192_route_enable(struct native_192 *s)
{
    unsigned int value = 1;
    int ret = n192_preflight(s);
    if (ret)
        return ret;
    ret = n192_check_route(s, 0, &s->route_before);
    if (ret)
        return ret;
    value = 8 + s->input_pair;
    ret = n192_xfer(s, 0x41, 1, &value);
    if (ret)
        return ret;
    value = 1;
    ret = n192_xfer(s, n192_output_reg(s), 1, &value);
    if (ret)
        return ret;
    /* Refuse audio if this is write-only or ignored: require 00 -> 01. */
    return n192_check_route(s, 1, &s->route_during);
}

static int n192_route_restore(struct native_192 *s)
{
    unsigned int attempt, value = 0;
    int ret = 0;
    if (!s->route_restore_required)
        return 0;
    if (s->route_before != 0)
        return -EINVAL;
    for (attempt = 0; attempt < 3; attempt++) {
        int input_err;
        value = 0;
        input_err = n192_xfer(s, 0x41, 1, &value);
        ret = n192_xfer(s, n192_output_reg(s), 1, &value);
        if (input_err)
            ret = input_err;
        if (!ret)
            ret = n192_check_route(s, 0, &s->route_after);
        if (!ret) {
            s->route_restored = 1;
            s->route_restore_required = 0;
            return 0;
        }
    }
    return ret;
}
#endif
