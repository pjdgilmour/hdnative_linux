/* HD Native PCIe identification experiment, x86-64 Linux only.
 * MMIO: exactly two 32-bit reads, BAR0 + 0 and + 4. No BAR writes.
 * PCI config: temporarily set COMMAND.MEMORY, then restore exact COMMAND.
 * Never enables bus mastering, DMA, interrupts, reset or firmware updates.
 * Evidence: dsi.dll RVA 0x19db90 and Dalwdm.sys RVA 0xe540, 26.4.1.179.
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

#if !defined(__x86_64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error This bounded experiment requires little-endian x86-64.
#endif

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
        fprintf(stderr, "Usage: %s --read-id [0000:81:00.0]\n", argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "--read-id") != 0) return 2;
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
    snprintf(path, sizeof(path), "/sys/bus/pci/devices/%s/resource0", bdf);
    fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) { perror("open resource0"); goto done; }
    if (fstat(fd, &st) || st.st_size != 0x400000) {
        fprintf(stderr, "Refusing: unexpected BAR0 length.\n"); goto done;
    }
    mapping = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, 0);
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
    volatile const uint32_t *regs = mapping;
    const uint32_t identity = regs[0];
    const uint32_t version = regs[1];
    printf("device=%s\nBAR0+0x00=0x%08x\nBAR0+0x04=0x%08x\n", bdf, identity, version);
    printf("HD_NATIVE_D400_MATCH=%s\n", (identity & 0xffff) == 0xd400 ? "yes" : "no");
    printf("This identifies the PCIe hardware only, not the connected 192.\n");
    rc = (identity & 0xffff) == 0xd400 ? 0 : 3;
done:
    if (restore()) rc = 4;
    if (mapping != MAP_FAILED) munmap(mapping, 4096);
    if (fd >= 0) close(fd);
    close(config_fd);
    return rc;
}
