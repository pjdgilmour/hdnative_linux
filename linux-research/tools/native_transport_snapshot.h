/* Fixed MMIO reads only, matching avid_native_adat quiet_state and the
 * slot-0 command-idle guard in native_192_adat_control.h.
 * No writes, no state normalization; a match is not optical lock. */
#ifndef NATIVE_TRANSPORT_SNAPSHOT_H
#define NATIVE_TRANSPORT_SNAPSHOT_H
struct transport_register {
    unsigned offset, mask, expected;
    const char *name;
};
static const struct transport_register transport_registers[] = {
    {0x00000, 0xffffffff, 0xd400, "identity"},
    {0x00004, 0xffffffff, 0x01050040, "firmware"},
    {0x00010, 0xffffffff, 0xa00, "core_control"},
    {0x00020, 0xffffffff, 0, "reset"},
    {0x70004, 0x101, 0x101, "digilink_status"},
    {0x70000, 0xffffffff, 0, "digilink_control"},
    {0x42004, 0xffffffff, 0, "dma_control"},
    {0x70018, 0xffffffff, 0, "digilink_irq_mask"},
    {0x42008, 0xffffffff, 0, "dma_irq"},
    {0x40918, 0xffffffff, 0, "rx_dma_low"},
    {0x40958, 0xffffffff, 0, "rx_dma_high"},
    {0x41118, 0xffffffff, 0, "tx_dma_low"},
    {0x41158, 0xffffffff, 0, "tx_dma_high"},
    {0x4093c, 0xffffffff, 0, "status_dma_low"},
    {0x4097c, 0xffffffff, 0, "status_dma_high"},
    {0x7001c, 0x00ffffff, 0, "slot0_tx_command"},
    {0x70040, 0x00ffff00, 0, "slot0_rx_header"},
};
#define TRANSPORT_REGISTER_COUNT (sizeof(transport_registers)/sizeof(transport_registers[0]))
static unsigned native_transport_snapshot(void)
{
    unsigned previous[TRANSPORT_REGISTER_COUNT], mismatches = 0;
    int stable = 1;
    for (unsigned pass = 0; pass < 2; pass++) {
        for (unsigned i = 0; i < TRANSPORT_REGISTER_COUNT; i++) {
            const struct transport_register *r = &transport_registers[i];
            unsigned value = dl_read32(r->offset);
            int match = (value & r->mask) == r->expected;
            if (!match) mismatches++;
            if (pass && previous[i] != value) stable = 0;
            previous[i] = value;
            printf("transport pass=%u reg=0x%05x name=%s value=0x%08x mask=0x%08x expected=0x%08x match=%s\n",
                   pass, r->offset, r->name, value, r->mask, r->expected, match ? "yes" : "no");
        }
    }
    printf("TRANSPORT_READS_STABLE=%s\n", stable ? "yes" : "no");
    printf("TRANSPORT_PRECONDITIONS_MATCH=%s\n", mismatches ? "no" : "yes");
    puts("This snapshot does not identify optical format/lock or prove the cause of a previous probe failure.");
    return mismatches;
}
#endif
