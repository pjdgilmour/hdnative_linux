/* Experimental HD Native / DigiLink identity query. See reports/digilink-protocol.md.
 * No reset or clock initialization. Writes only neutral/read commands in
 * BAR0 0x7001c..0x70038, after the DSI presence predicate and idle checks.
 * SIGINT/TERM/HUP request cleanup; SIGBUS/SEGV restore only PCI config.
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <time.h>
#include <sys/file.h>

#if !defined(__x86_64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error This bounded experiment requires little-endian x86-64.
#endif

static volatile sig_atomic_t stop_requested;
static volatile uint32_t *mmio;
static uint32_t dl_read32(unsigned off) { return mmio[off / 4]; }
static void dl_write32(unsigned off, uint32_t value) {
    mmio[off / 4] = value;
    (void)mmio[off / 4]; /* Flush the posted PCIe write. */
}
static uint64_t dl_now_us(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { stop_requested = 1; return 0; }
    return (uint64_t)t.tv_sec * 1000000 + (uint64_t)t.tv_nsec / 1000;
}
static void dl_pause(void) {
    const struct timespec delay = {0, 50000};
    (void)nanosleep(&delay, NULL);
}
static int dl_cancelled(void) { return stop_requested != 0; }
#include "digilink_query.h"
static int config_fd = -1;
static uint16_t original_command;
static volatile sig_atomic_t restore_needed;

static int restore(void)
{
    uint16_t got;
    if (!restore_needed) return 0;
    if (pwrite(config_fd, &original_command, 2, 4) != 2 ||
        pread(config_fd, &got, 2, 4) != 2 || got != original_command) {
        fprintf(stderr, "ERROR: PCI COMMAND restoration failed! Original: 0x%04x\n",
                original_command);
        return -1;
    }
    restore_needed = 0;
    return 0;
}

static void interrupted(int sig)
{
    if (sig == SIGINT || sig == SIGTERM || sig == SIGHUP) {
        stop_requested = sig; return;
    }
    /* MMIO faults cannot safely retry MMIO cleanup. Restore PCI only. */
    if (restore_needed) {
        ssize_t n = pwrite(config_fd, &original_command, 2, 4);
        if (n != 2) {
            static const char msg[] = "ERROR: PCI COMMAND restoration failed on signal\n";
            ssize_t ignored = write(STDERR_FILENO, msg, sizeof(msg) - 1);
            (void)ignored;
        }
    }
    _exit(128 + sig);
}

int main(int argc, char **argv)
{
    const char *bdf = "0000:81:00.0";
    char path[160], canonical[32];
    unsigned domain, bus, slot, function;
    uint16_t header[32], command;
    struct stat st;
    struct sigaction action = {0};
    sigset_t blocked, previous;
    int fd = -1, rc = 1;
    void *mapping = MAP_FAILED;

    if (argc != 2 && argc != 3) {
        fprintf(stderr, "Usage: %s --identify-192|--inspect-192|--inspect-routing|--inspect-digital [0000:81:00.0]\n", argv[0]);
        return 2;
    }
    const int digital = strcmp(argv[1], "--inspect-digital") == 0;
    const int routing = strcmp(argv[1], "--inspect-routing") == 0;
    const int diagnostics = digital || routing || strcmp(argv[1], "--inspect-192") == 0;
    if (!diagnostics && strcmp(argv[1], "--identify-192") != 0) return 2;
    if (argc == 3) bdf = argv[2];
    if (sscanf(bdf, "%x:%x:%x.%x", &domain, &bus, &slot, &function) != 4 ||
        domain > 65535 || bus > 255 || slot > 31 || function > 7) return 2;
    snprintf(canonical, sizeof(canonical), "%04x:%02x:%02x.%x", domain, bus, slot, function);
    if (strcmp(bdf, canonical)) return 2;
    if (geteuid() != 0) {
        fprintf(stderr, "Root required for PCI resource access; no hardware changes made.\n");
        return 1;
    }
    snprintf(path, sizeof(path), "/sys/bus/pci/devices/%s/driver", bdf);
    if (lstat(path, &st) == 0 || errno != ENOENT) {
        fprintf(stderr, "Refusing: bound driver or driver state cannot be checked.\n");
        return 1;
    }
    snprintf(path, sizeof(path), "/sys/bus/pci/devices/%s/config", bdf);
    config_fd = open(path, O_RDWR | O_CLOEXEC);
    if (config_fd < 0) { perror("open config"); return 1; }
    if (pread(config_fd, header, sizeof(header), 0) != sizeof(header)) {
        perror("read PCI header"); goto done;
    }
    if (header[0] != 0x11af || header[1] != 0xef80 ||
        header[22] != 0x11af || header[23] != 0xef80) {
        fprintf(stderr, "Refusing: not the expected HD Native PCIe/subsystem.\n");
        goto done;
    }
    original_command = header[2];
    if (original_command & 4) {
        fprintf(stderr, "Refusing: bus mastering is already active.\n"); goto done;
    }
    if (flock(config_fd, LOCK_EX | LOCK_NB)) {
        perror("lock config"); goto done;
    }
    snprintf(path, sizeof(path), "/sys/bus/pci/devices/%s/resource0", bdf);
    fd = open(path, O_RDWR | O_CLOEXEC);
    if (fd < 0) { perror("open resource0"); goto done; }
    if (fstat(fd, &st) || st.st_size != 0x400000) {
        fprintf(stderr, "Refusing: unexpected BAR0 length.\n"); goto done;
    }
    mapping = mmap(NULL, 0x71000, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (mapping == MAP_FAILED) { perror("mmap resource0"); goto done; }
    action.sa_handler = interrupted;
    sigemptyset(&action.sa_mask);
    const int signals[] = {SIGBUS, SIGSEGV, SIGINT, SIGTERM, SIGHUP};
    sigemptyset(&blocked);
    for (size_t i = 0; i < sizeof(signals) / sizeof(signals[0]); i++) {
        if (sigaction(signals[i], &action, NULL)) { perror("sigaction"); goto done; }
        sigaddset(&blocked, signals[i]);
    }
    command = original_command | 2;
    if (sigprocmask(SIG_BLOCK, &blocked, &previous)) { perror("sigprocmask"); goto done; }
    restore_needed = command != original_command;
    if (restore_needed && pwrite(config_fd, &command, 2, 4) != 2) {
        perror("enable memory decoding");
        sigprocmask(SIG_SETMASK, &previous, NULL); goto done;
    }
    sigprocmask(SIG_SETMASK, &previous, NULL);
    uint16_t observed;
    if (pread(config_fd, &observed, 2, 4) != 2 || observed != command) {
        fprintf(stderr, "PCI command verification failed.\n"); goto done;
    }
    mmio = mapping;
    setvbuf(stdout, NULL, _IONBF, 0);
    const uint32_t identity = dl_read32(0), version = dl_read32(4);
    printf("device=%s\nBAR0+0x00=0x%08x\nBAR0+0x04=0x%08x\n", bdf, identity, version);
    rc = 3;
    if (identity != 0xd400 || version != 0x01050040) {
        fprintf(stderr, "Refusing: not the hardware/firmware observed in the first experiment.\n");
        goto done;
    }
    const unsigned status_offsets[] = {0x10, 0x20, 0x44, 0x70000, 0x70004};
    for (unsigned i = 0; i < sizeof(status_offsets)/sizeof(status_offsets[0]); i++)
        printf("status[0x%05x]=0x%08x\n", status_offsets[i], dl_read32(status_offsets[i]));
    if (diagnostics && (dl_read32(0x10) != 0xa00 || dl_read32(0x20) ||
                        dl_read32(0x70000) || dl_read32(0x42004))) {
        fputs("Refusing diagnostic queries outside the known quiet transport state.\n", stderr);
        goto done;
    }
    for (unsigned port = 0; port < 8; port++)
        printf("slot=%u tx=0x%08x rx=0x%08x\n", port,
               dl_read32(DL_TX(port)), dl_read32(DL_RX(port)));
    if (!(dl_read32(0x70004) & 15)) {
        puts("DIGILINK_READY=no; DSI presence predicate is false; no BAR writes performed.");
        puts("192_IDENTIFIED=no; link initialization may be required.");
        goto done;
    }
    puts("DIGILINK_READY=yes; attempting bounded identification queries.");
    unsigned found = 0;
    for (unsigned port = 0; port < (diagnostics ? 1u : 8u) && !stop_requested; port++) {
        uint8_t family;
        uint32_t response;
        int cleanup;
        int result = dl_query(port, 0x10, &family, &response, &cleanup);
        printf("slot=%u reg=0x10 result=%d response=0x%06x value=0x%02x cleanup=%d\n",
               port, result, response, family, cleanup);
        if (cleanup != DL_OK) { rc = 5; break; }
        if (result != DL_OK || family != 1) continue;
        uint32_t modules = 0;
        int complete = 1;
        for (unsigned reg = 0x14; reg <= 0x17; reg++) {
            uint8_t value;
            result = dl_query(port, reg, &value, &response, &cleanup);
            printf("slot=%u reg=0x%02x result=%d response=0x%06x value=0x%02x cleanup=%d\n",
                   port, reg, result, response, value, cleanup);
            if (result != DL_OK || cleanup != DL_OK) { complete = 0; break; }
            modules |= (uint32_t)value << (8 * (reg - 0x14));
        }
        if (cleanup != DL_OK) { rc = 5; break; }
        if (!complete) continue;
        unsigned model = dl_django_model(modules);
        printf("slot=%u Django_modules=0x%08x DSI_model=%u\n", port, modules, model);
        if (model == 16 || model == 17) {
            printf("slot=%u model=192 I/O\n", port);
            found++;
        }
        if (diagnostics) {
            if (modules != 0x13151314 || model != 16) {
                fputs("Refusing diagnostic reads: expected the previously identified 192 modules.\n", stderr);
                rc = 5;
                break;
            }
            const unsigned regs[] = {0x11, 0x12, 0x13, 0x00, 0x01, 0x02, 0x03};
            puts("Control readback support is unverified; ACK/zero values alone do not prove register contents.");
            for (unsigned pass = 0; pass < 2 && rc != 5 && !stop_requested; pass++) {
                for (unsigned j = 0; j < sizeof(regs)/sizeof(regs[0]); j++) {
                    uint8_t value;
                    result = dl_query_impl(port, regs[j], 1, &value, &response, &cleanup);
                    printf("diagnostic pass=%u slot=%u bank=1 reg=0x%02x result=%d response=0x%06x value=0x%02x cleanup=%d\n",
                           pass, port, regs[j], result, response, value, cleanup);
                    if (result != DL_OK || cleanup != DL_OK) { rc = 5; break; }
                }
            }
            if (digital && rc != 5 && !stop_requested) {
                struct dl_digital_snapshot snapshot;
                puts("Digital candidate readback: a timeout is unavailable data, not zero. No peripheral writes.");
                int read_result = dl_inspect_digital(port, &snapshot);
                for (unsigned pass = 0; pass < 2; pass++) {
                    for (unsigned j = 0; j < 3; j++) {
                        if (snapshot.results[pass][j] == DL_NOT_ATTEMPTED) continue;
                        printf("digital pass=%u slot=%u module=2 bank=1 reg=0x%02x result=%d response=0x%06x ",
                               pass, port, 0x30+j, snapshot.results[pass][j], snapshot.responses[pass][j]);
                        if (snapshot.results[pass][j] == DL_OK)
                            printf("value=0x%02x ", snapshot.values[pass][j]);
                        else
                            printf("value=unavailable ");
                        printf("cleanup=%d\n", snapshot.cleanup[pass][j]);
                    }
                }
                printf("DIGITAL_READS_ATTEMPTED=%u\n", snapshot.attempted);
                printf("DIGITAL_READS_COMPLETE=%s\n", snapshot.complete ? "yes" : "no");
                printf("DIGITAL_READS_STABLE=%s\n", snapshot.complete ? (snapshot.stable ? "yes" : "no") : "unavailable");
                puts("Readback alone does not establish ADAT selection or optical lock.");
                if (read_result != DL_OK) rc = 5;
            }
            if (routing && rc != 5 && !stop_requested) {
                uint8_t previous_values[30] = {0};
                int stable = 1;
                puts("Routing readback support remains provisional; this mode sends no peripheral WRITE commands.");
                for (unsigned pass = 0; pass < 2 && rc != 5 && !stop_requested; pass++) {
                    uint8_t values[30] = {0};
                    for (unsigned j = 0; j < 30; j++) {
                        result = dl_query_impl(port, 0x40 + j, 2, &values[j], &response, &cleanup);
                        if (result != DL_OK || cleanup != DL_OK) {
                            printf("routing reg=0x%02x result=%d response=0x%06x cleanup=%d\n",
                                   0x40+j, result, response, cleanup);
                            rc = 5;
                            break;
                        }
                        if (pass && values[j] != previous_values[j]) stable = 0;
                    }
                    if (rc == 5) break;
                    printf("routing pass=%u values[0x40..0x5d]=", pass);
                    for (unsigned j = 0; j < 30; j++) printf("%s%02x", j ? " " : "", values[j]);
                    putchar('\n');
                    memcpy(previous_values, values, sizeof(values));
                }
                if (rc != 5 && !stop_requested) {
                    printf("ROUTING_READS_STABLE=%s\n", stable ? "yes" : "no");
                    if (!stable) rc = 5;
                }
            }
            puts("No peripheral WRITE command was sent; no mute or routing value was changed by this tool.");
        }
    }
    printf("192_IDENTIFIED=%s count=%u\n", found ? "yes" : "no", found);
    puts("No reset, clock setup, DMA, audio or firmware update was performed.");
    if (rc != 5) rc = stop_requested ? 128 + stop_requested : found ? 0 : 3;
done:
    if (restore()) rc = 4;
    else puts("PCI_COMMAND_RESTORED=yes");
    if (mapping != MAP_FAILED) munmap(mapping, 0x71000);
    if (fd >= 0) close(fd);
    close(config_fd);
    return rc;
}
