/* Recovered DSI 26.4.1 protocol, deliberately no hardware initialization.
 * Backend supplies dl_read32, dl_write32, dl_now_us, dl_pause, dl_cancelled.
 * Bank 1 identity reads; explicit diagnostic mode additionally permits
 * 0x00..0x03 (tentative control readback) and 0x11..0x13 (DSI status reads).
 * Diagnostic level 2 also permits 0x40..0x5d: the DSI routing table range.
 * Diagnostic level 3 permits only the extra digital module controls 0x30..0x32.
 * No command has the peripheral write bit (bit 23) set.
 */
#define DL_TX(p) (0x7001cu + 4u * (p))
#define DL_RX(p) (0x70040u + 4u * (p))
#define DL_MASK 0x00ffffffu
enum { DL_OK, DL_TIMEOUT, DL_BUSY, DL_BAD_REQUEST, DL_CANCELLED, DL_CLEANUP, DL_NOT_ATTEMPTED, DL_UNSTABLE };

static int dl_wait(unsigned port, uint32_t command, uint32_t *response)
{
    uint64_t start = dl_now_us();
    for (unsigned n = 0; n < 2001; n++) {
        *response = dl_read32(DL_RX(port)) & DL_MASK;
        if (dl_cancelled()) return DL_CANCELLED;
        if ((*response & 0xffff00u) == command) return DL_OK;
        if (dl_now_us() - start >= 100000) break;
        dl_pause();
    }
    return DL_TIMEOUT;
}

static int dl_query_impl(unsigned port, unsigned reg, int diagnostics,
                         uint8_t *value, uint32_t *response, int *cleanup)
{
    *cleanup = DL_OK;
    *value = 0;
    *response = 0;
    int identity_reg = reg == 0x10 || (reg >= 0x14 && reg <= 0x17);
    int diagnostic_reg = reg <= 3 || (reg >= 0x11 && reg <= 0x13);
    int digital_reg = reg >= 0x30 && reg <= 0x32;
    int routing_reg = reg >= 0x40 && reg <= 0x5d;
    if (port > 7 || !(identity_reg || (diagnostics && diagnostic_reg) ||
                     (diagnostics == 2 && routing_reg) ||
                     (diagnostics == 3 && digital_reg)))
        return DL_BAD_REQUEST;
    if (dl_cancelled()) return DL_CANCELLED;
    uint32_t tx = dl_read32(DL_TX(port));
    if ((tx & DL_MASK) || (dl_read32(DL_RX(port)) & 0xffff00u))
        return DL_BUSY; /* Refuse a stale or outstanding transaction. */
    uint32_t command = 0x10000u | (reg << 8);
    dl_write32(DL_TX(port), (tx & 0xff000000u) | command);
    int result = dl_wait(port, command, response);
    if (result == DL_OK) *value = (uint8_t)*response;
    /* Same neutral command as DSI 0x19b37e/0x19b47b, including on timeout.
     * Upper byte is preserved from a fresh read, as DSI 0x19f6c0 does.
     */
    tx = dl_read32(DL_TX(port));
    dl_write32(DL_TX(port), tx & 0xff000000u);
    uint32_t idle_response;
    *cleanup = dl_wait(port, 0, &idle_response);
    if (dl_read32(DL_TX(port)) & DL_MASK) *cleanup = DL_CLEANUP;
    return result;
}


/* Read only the three addresses derived from the module write adapter.
 * A clean timeout makes the value unavailable, not zero. Continue only
 * after acknowledged neutralization; never continue after other errors.
 * All three addresses remain candidates for readable controls. */
struct dl_digital_snapshot {
    uint8_t values[2][3];
    uint32_t responses[2][3];
    int results[2][3], cleanup[2][3];
    unsigned attempted;
    int complete, stable;
};
static int dl_inspect_digital(unsigned port, struct dl_digital_snapshot *s)
{
    *s = (struct dl_digital_snapshot){0};
    for (unsigned pass = 0; pass < 2; pass++)
        for (unsigned j = 0; j < 3; j++) {
            s->results[pass][j] = DL_NOT_ATTEMPTED;
            s->cleanup[pass][j] = DL_NOT_ATTEMPTED;
        }
    for (unsigned pass = 0; pass < 2; pass++) {
        for (unsigned j = 0; j < 3; j++) {
            int rc = dl_query_impl(port, 0x30 + j, 3, &s->values[pass][j],
                                  &s->responses[pass][j], &s->cleanup[pass][j]);
            s->results[pass][j] = rc;
            s->attempted++;
            if (s->cleanup[pass][j] != DL_OK)
                return s->cleanup[pass][j];
            if (rc != DL_OK && rc != DL_TIMEOUT)
                return rc;
        }
    }
    s->complete = 1;
    for (unsigned pass = 0; pass < 2; pass++)
        for (unsigned j = 0; j < 3; j++)
            if (s->results[pass][j] != DL_OK) s->complete = 0;
    if (!s->complete) return DL_TIMEOUT;
    s->stable = 1;
    for (unsigned j = 0; j < 3; j++)
        if (s->values[0][j] != s->values[1][j]) s->stable = 0;
    return s->stable ? DL_OK : DL_UNSTABLE;
}

static int dl_query(unsigned port, unsigned reg, uint8_t *value,
                    uint32_t *response, int *cleanup)
{
    return dl_query_impl(port, reg, 0, value, response, cleanup);
}

/* DSI 0x1ae270: module bytes 0x14..0x17, little endian.
 * Family ID 1 alone is insufficient: Django also includes 96 I/O.
 */
static unsigned dl_django_model(uint32_t modules)
{
    switch (modules) {
    case 0x12: case 0x1100: case 0x1112: return 15;
    case 0x15: case 0x1500: case 0x1515: return 17;
    case 0x1314: case 0x150014: case 0x151300: case 0x151314:
    case 0x13001314: case 0x13150014: case 0x13151300:
    case 0x13151314: case 0x14001314: case 0x14150014:
    case 0x14151300: case 0x14151314: case 0x15001314:
    case 0x15150014: case 0x15151300: case 0x15151314: return 16;
    default: return 0;
    }
}
