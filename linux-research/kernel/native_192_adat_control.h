/* SPDX-License-Identifier: GPL-2.0 */
/* Bounded optical route probe: enclosure endpoints 25..28, module 17..20.
 * Capture reg41 selects one endpoint; output reg40+endpoint selects TX pair1.
 * Never configures digital, input level/trim, firmware, or clock.
 * Each profile requires an initially zero route table and restores both
 * selected routes after ANY write attempt, including lost ACKs. */
#ifndef NATIVE_192_ADAT_CONTROL_H
#define NATIVE_192_ADAT_CONTROL_H
struct native_192 {
    void *ctx;
    unsigned int (*read)(void *, unsigned int);
    void (*write)(void *, unsigned int, unsigned int);
    unsigned long long (*now_us)(void *);
    void (*pause)(void *);
    int before, during, after;
    int restore_required, write_attempted, restored;
    int windows_state; /* exact observed profile, all peripheral writes forbidden */
    unsigned int input_pair, output_pair; /* 1..4 optical pairs */
    unsigned int optical_path; /* 1=enclosure, 2=digital module; format retained */
    unsigned int check_reg, check_expected, check_observed;
    unsigned int idle_waits, idle_tx, idle_rx;
    int route_enabled, route_before, route_during, route_after;
    int route_restore_required, route_write_attempted, route_restored;
};

/* The first transport pair is mapped to one selected optical pair.
 * No ADAT format/SRC/clock control is read or written. A positive physical
 * loopback is needed to establish the path; absence of tones is inconclusive. */
static int n192_profile_valid(struct native_192 *s)
{
    if (s->windows_state)
        return s->optical_path == 1 && s->input_pair >= 1 && s->input_pair <= 4 &&
               s->output_pair >= 1 && s->output_pair <= 4;
    return s->input_pair >= 1 && s->input_pair <= 4 &&
           s->output_pair >= 1 && s->output_pair <= 4 &&
           (s->optical_path == 1 || s->optical_path == 2);
}
static unsigned int n192_input_selector(struct native_192 *s)
{
    return (s->optical_path == 1 ? 24 : 16) + s->input_pair;
}
static unsigned int n192_output_reg(struct native_192 *s)
{
    return (s->optical_path == 1 ? 0x58 : 0x50) + s->output_pair;
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

/* Observe only: never clear somebody else's pending command or mask a
 * nonzero RX header. Require two idle samples separated by a pause;
 * a single zero during response teardown is not sufficient. */
static int n192_wait_idle(struct native_192 *s, unsigned int *tx)
{
    unsigned long long start = s->now_us(s->ctx);
    unsigned int i, consecutive = 0;
    int saw_busy = 0;
    for (i = 0; i < 2001; i++) {
        *tx = s->read(s->ctx, 0x7001c);
        s->idle_tx = *tx;
        s->idle_rx = s->read(s->ctx, 0x70040);
        if (*tx & 0xffffff)
            return -EBUSY;
        if (s->idle_rx & 0xffff00) {
            consecutive = 0;
            if (!saw_busy) { s->idle_waits++; saw_busy = 1; }
        } else if (++consecutive == 2) {
            return 0;
        }
        if (s->now_us(s->ctx) - start >= 100000)
            break;
        s->pause(s->ctx);
    }
    return -EBUSY;
}

static int n192_xfer(struct native_192 *s, unsigned int reg, int write,
                     unsigned int *value)
{
    unsigned int tx, command, response = 0;
    int ret, cleanup;
    int route_reg = s->route_enabled && reg >= 0x40 && reg <= 0x5d;
    int control_write = reg == 0 && (*value == 0 || *value == 2);
    int route_write = s->route_enabled && ((reg == n192_output_reg(s) && *value <= 1) ||
                      (reg == 0x41 && (*value == 0 || *value == n192_input_selector(s))));
    if (!n192_profile_valid(s) || (s->windows_state && write)) return -EINVAL;
    if (write ? !(control_write || route_write) :
                !(reg <= 3 || (reg >= 0x10 && reg <= 0x17) || route_reg))
        return -EINVAL;
    ret = n192_wait_idle(s, &tx);
    if (ret)
        return ret;
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
    cleanup = n192_wait_idle(s, &tx);
    if (cleanup)
        return -EIO;
    return ret;
}

static int n192_expect(struct native_192 *s, unsigned int reg,
                       unsigned int expected, int *observed)
{
    unsigned int value = 0;
    int ret = n192_xfer(s, reg, 0, &value);
    s->check_reg = reg;
    s->check_expected = expected;
    s->check_observed = ret ? 0xffffffffU : value;
    if (ret)
        return ret;
    if (observed)
        *observed = (int)value;
    return value == expected ? 0 : -EPROTO;
}

/* Exact readback from the Windows session: no general saved-state loader. */
static int n192_windows_routes(struct native_192 *s, int *observed)
{
    static const unsigned int routes[30] = {
        0,9,10,11,12,25,26,27,28,0,0,0,0,1,2,3,4,0,0,0,0,0,0,0,0,5,6,7,8,1
    };
    unsigned int pass, i;
    int ret;
    for (pass = 0; pass < 2; pass++)
        for (i = 0; i < 30; i++) {
            ret = n192_expect(s, 0x40 + i, routes[i], 0x40 + i == n192_output_reg(s) ? observed : 0);
            if (ret) return ret;
        }
    return 0;
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
            ret = n192_expect(s, reg, s->windows_state && reg == 1 ? 0x80 : 0, 0);
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
            unsigned int expected = values[i];
            if (s->windows_state) {
                if (regs[i] == 0x12) expected = 3;
                if (regs[i] == 0) expected = 0;
                if (regs[i] == 1) expected = 0x80;
            }
            ret = n192_expect(s, regs[i], expected,
                              regs[i] == 0 ? &s->before : 0);
            if (ret)
                return ret;
        }
    }
    return s->windows_state ? n192_windows_routes(s, &s->route_before) : 0;
}

static int n192_unmute(struct native_192 *s)
{
    unsigned int value = 0;
    int ret = n192_preflight(s);
    if (!ret && s->windows_state) return n192_check_unmuted(s);
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
    if (s->windows_state) {
        ret = n192_preflight(s);
        s->restore_required = !!ret;
        s->restored = !ret;
        if (!ret) s->after = 0;
        return ret;
    }
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
    if (s->windows_state) return n192_windows_routes(s, observed);
    for (pass = 0; pass < 2; pass++) {
        for (reg = 0x40; reg <= 0x5d; reg++) {
            ret = n192_expect(s, reg, reg == 0x41 ? (expected ? n192_input_selector(s) : 0) : (reg == n192_output_reg(s) ? expected : 0),
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
    if (s->windows_state) return n192_windows_routes(s, &s->route_during);
    ret = n192_check_route(s, 0, &s->route_before);
    if (ret)
        return ret;
    value = n192_input_selector(s);
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
    if (s->windows_state) {
        ret = n192_windows_routes(s, &s->route_after);
        s->route_restore_required = !!ret;
        s->route_restored = !ret;
        return ret;
    }
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
