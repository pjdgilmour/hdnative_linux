#!/usr/bin/env python3
"""Exercise the C probe against temporary files; no real PCI device access.

Linker wrappers redirect every open/lstat in the probe to the fixture and
inject failures/signals. Tests cover restoration of PCI COMMAND.
"""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

WRAPPERS = r'''
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
int __real_open(const char *, int, ...);
int __real_lstat(const char *, struct stat *);
ssize_t __real_pread(int, void *, size_t, off_t);
ssize_t __real_pwrite(int, const void *, size_t, off_t);
static int translate(const char *p, char *dest) {
    const char *prefix = "/sys/bus/pci/devices/0000:81:00.0/";
    if (strncmp(p, prefix, strlen(prefix))) { errno = EACCES; return -1; }
    snprintf(dest, 1024, "%s/%s", getenv("FIXTURE"), p + strlen(prefix));
    return 0;
}
uid_t __wrap_geteuid(void) { return 0; }
int __wrap_open(const char *p, int flags, ...) {
    char dest[1024];
    if (translate(p, dest)) return -1;
    return __real_open(dest, flags);
}
int __wrap_lstat(const char *p, struct stat *st) {
    char dest[1024];
    if (translate(p, dest)) return -1;
    return __real_lstat(dest, st);
}
ssize_t __wrap_pread(int fd, void *buf, size_t n, off_t off) {
    static int count;
    const char *fault = getenv("FAULT");
    if (++count == 2 && fault) {
        if (!strcmp(fault, "verify_error")) { errno = EIO; return -1; }
        if (!strcmp(fault, "sigterm")) raise(SIGTERM);
        if (!strcmp(fault, "sigbus")) raise(SIGBUS);
    }
    return __real_pread(fd, buf, n, off);
}
ssize_t __wrap_pwrite(int fd, const void *buf, size_t n, off_t off) {
    static int count;
    const char *fault = getenv("FAULT");
    if (++count == 1 && fault && !strcmp(fault, "enable_error")) {
        errno = EACCES; return -1;
    }
    return __real_pwrite(fd, buf, n, off);
}
'''


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="native-probe-test-")
        cls.root = Path(cls.temp.name)
        (cls.root / "wrappers.c").write_text(WRAPPERS)
        cls.exe = cls.root / "probe"
        subprocess.run([
            "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            str(Path(__file__).with_name("read_native_id.c")),
            str(cls.root / "wrappers.c"), "-o", str(cls.exe),
            *["-Wl,--wrap=" + x for x in ("geteuid", "open", "lstat", "pread", "pwrite")],
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, *, identity=0x1000d400, command=0x100,
                 vendor=0x11af, fault="", bound=False, expected=0):
        with tempfile.TemporaryDirectory(dir=self.root) as d:
            p = Path(d)
            header = bytearray(64)
            struct.pack_into("<HHH", header, 0, vendor, 0xef80, command)
            struct.pack_into("<HH", header, 44, 0x11af, 0xef80)
            (p / "config").write_bytes(header)
            with (p / "resource0").open("wb") as f:
                f.write(struct.pack("<II", identity, 0x01050000))
                f.truncate(0x400000)
            if bound:
                (p / "driver").mkdir()
            proc = subprocess.run([str(self.exe), "--read-id"], text=True,
                                  capture_output=True,
                                  env={**os.environ, "FIXTURE": d, "FAULT": fault})
            self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
            self.assertEqual((p / "config").read_bytes(), bytes(header),
                             "PCI config was not restored exactly")
            with (p / "resource0").open("rb") as f:
                self.assertEqual(f.read(8), struct.pack("<II", identity, 0x01050000))
            return proc

    def test_identity(self):
        self.assertIn("HD_NATIVE_D400_MATCH=yes", self.run_case().stdout)

    def test_bad_identity(self):
        self.run_case(identity=0xffffffff, expected=3)

    def test_bus_master_refused(self):
        self.run_case(command=0x104, expected=1)

    def test_wrong_card_refused(self):
        self.run_case(vendor=0x8086, expected=1)

    def test_bound_driver_refused(self):
        self.run_case(bound=True, expected=1)

    def test_existing_memory_decode_preserved(self):
        self.run_case(command=0x102)

    def test_verification_failure_restores(self):
        self.run_case(fault="verify_error", expected=1)

    def test_enable_failure_restores(self):
        self.run_case(fault="enable_error", expected=1)

    def test_sigterm_restores(self):
        self.run_case(fault="sigterm", expected=143)

    def test_sigbus_restores(self):
        self.run_case(fault="sigbus", expected=135)


if __name__ == "__main__":
    unittest.main(verbosity=2)
