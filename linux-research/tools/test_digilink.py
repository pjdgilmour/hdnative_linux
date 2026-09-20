#!/usr/bin/env python3
"""No hardware access: protocol simulator and PCI-file integration fixtures."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from test_probe import WRAPPERS

HERE = Path(__file__).resolve().parent
HARNESS = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint32_t tx[8], rx[8];
static unsigned writes, mode, cancelled, last_port;
static uint64_t now;
static uint32_t dl_read32(unsigned off) {
    if (off >= 0x7001c && off <= 0x70038 && !(off & 3))
        return tx[(off - 0x7001c) / 4];
    assert(off >= 0x70040 && off <= 0x7005c && !(off & 3));
    return rx[(off - 0x70040) / 4];
}
static void dl_write32(unsigned off, uint32_t v) {
    assert(off >= 0x7001c && off <= 0x70038 && !(off & 3));
    unsigned p = (off - 0x7001c) / 4;
    uint32_t cmd = v & 0xffffff;
    assert(!(cmd & 0x800000)); /* Peripheral WRITE bit must never be set. */
    assert(cmd == 0 || (!(cmd & 255) &&
           ((cmd >= 0x10000 && cmd <= 0x10300) ||
            (cmd >= 0x11000 && cmd <= 0x11700) ||
            (cmd >= 0x14000 && cmd <= 0x15d00))));
    assert((v & 0xff000000) == 0xa5000000);
    writes++; last_port = p; tx[p] = v;
    if (mode == 1 && cmd) rx[p] = 0x11201; /* Wrong response header. */
    else if (mode == 2 && !cmd) rx[p] = 0x11001; /* Neutral timeout. */
    else rx[p] = cmd ? cmd | 1 : 0;
    if (mode == 3 && cmd) cancelled = 1;
}
static uint64_t dl_now_us(void) { return now; }
static void dl_pause(void) { now += 50; }
static int dl_cancelled(void) { return cancelled; }
#include "digilink_query.h"
static void reset(unsigned m) {
    for (unsigned p=0; p<8; p++) { tx[p]=0xa5000000; rx[p]=0; }
    writes=cancelled=0; now=0; mode=m;
}
int main(void) {
    uint8_t val; uint32_t response; int cleanup;
    for (unsigned p=0; p<8; p++) {
        reset(0);
        assert(dl_query(p,0x10,&val,&response,&cleanup)==DL_OK);
        assert(val==1 && response==0x11001 && cleanup==DL_OK);
        assert(writes==2 && last_port==p && tx[p]==0xa5000000);
    }
    reset(1);
    assert(dl_query(0,0x10,&val,&response,&cleanup)==DL_TIMEOUT);
    assert(val==0 && cleanup==DL_OK && writes==2 && now==100000);
    reset(2);
    assert(dl_query(0,0x10,&val,&response,&cleanup)==DL_OK);
    assert(cleanup==DL_TIMEOUT && tx[0]==0xa5000000);
    reset(3);
    assert(dl_query(0,0x10,&val,&response,&cleanup)==DL_CANCELLED);
    assert(val==0 && writes==2 && tx[0]==0xa5000000);
    reset(0); tx[0]|=0x11000;
    assert(dl_query(0,0x10,&val,&response,&cleanup)==DL_BUSY && writes==0);
    reset(0); rx[0]=0x11001;
    assert(dl_query(0,0x10,&val,&response,&cleanup)==DL_BUSY && writes==0);
    reset(0);
    assert(dl_query(8,0x10,&val,&response,&cleanup)==DL_BAD_REQUEST);
    for (unsigned r=0; r<256; r++) {
        if (r==0x10 || (r>=0x14 && r<=0x17)) continue;
        assert(dl_query(0,r,&val,&response,&cleanup)==DL_BAD_REQUEST);
    }
    assert(writes==0);
    for (unsigned r=0; r<256; r++) {
        reset(0);
        int allowed = r<=3 || (r>=0x10 && r<=0x17);
        int status = dl_query_impl(0,r,1,&val,&response,&cleanup);
        assert(status == (allowed ? DL_OK : DL_BAD_REQUEST));
        assert(writes == (allowed ? 2u : 0u));
        if (allowed) {
            assert(response == (0x10000u | (r<<8) | 1));
            assert(cleanup == DL_OK && tx[0] == 0xa5000000);
        }
    }
    assert(dl_django_model(0x13151314)==16);
    for (unsigned r=0; r<256; r++) {
        reset(0);
        int allowed = r<=3 || (r>=0x10 && r<=0x17) || (r>=0x40 && r<=0x5d);
        int status = dl_query_impl(0,r,2,&val,&response,&cleanup);
        assert(status == (allowed ? DL_OK : DL_BAD_REQUEST));
        assert(writes == (allowed ? 2u : 0u));
        if (allowed) assert(response == (0x10000u | (r<<8) | 1) && cleanup==DL_OK);
    }
    assert(dl_django_model(0x1515)==17);
    assert(dl_django_model(0x1112)==15);
    assert(dl_django_model(0xffffffff)==0 && dl_django_model(0)==0);
    puts("Protocol: all 8 slots; response correlation; timeouts; cleanup; cancellation; stale replies; command allowlist; model distinction: PASS");
}
'''


class DigiLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="digilink-test-")
        cls.root = Path(cls.temp.name)
        (cls.root / "wrappers.c").write_text(WRAPPERS)
        (cls.root / "protocol.c").write_text(HARNESS)
        opts = ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror"]
        subprocess.run(opts + ["-I" + str(HERE), str(cls.root / "protocol.c"),
                              "-o", str(cls.root / "protocol")], check=True)
        subprocess.run(opts + [str(HERE / "identify_192.c"), str(cls.root / "wrappers.c"),
                              "-o", str(cls.root / "probe"),
                              *["-Wl,--wrap=" + x for x in
                                ("geteuid", "open", "lstat", "pread", "pwrite")]], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_protocol(self):
        subprocess.run([str(self.root / "protocol")], check=True)

    def run_fixture(self, *, command=0x100, version=0x01050040,
                    identity=0xd400, ready=0, fault="", bound=False, expected=3,
                    inspect=False, routing=False, ctl=0, dma=0):
        with tempfile.TemporaryDirectory(dir=self.root) as d:
            p = Path(d)
            header = bytearray(64)
            struct.pack_into("<HHH", header, 0, 0x11af, 0xef80, command)
            struct.pack_into("<HH", header, 44, 0x11af, 0xef80)
            (p / "config").write_bytes(header)
            bar = bytearray(0x400000)
            struct.pack_into("<II", bar, 0, identity, version)
            struct.pack_into("<I", bar, 0x70004, ready)
            struct.pack_into("<I", bar, 0x10, ctl)
            struct.pack_into("<I", bar, 0x42004, dma)
            (p / "resource0").write_bytes(bar)
            if bound:
                (p / "driver").mkdir()
            arg = "--inspect-routing" if routing else "--inspect-192" if inspect else "--identify-192"
            r = subprocess.run([str(self.root / "probe"), arg],
                               env={**os.environ, "FIXTURE": d, "FAULT": fault},
                               capture_output=True, text=True, timeout=5)
            self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
            self.assertEqual((p / "config").read_bytes(), header)
            self.assertEqual((p / "resource0").read_bytes(), bar)
            self.assertNotIn("192_IDENTIFIED=yes", r.stdout)
            return r

    def test_no_link_no_bar_writes(self):
        self.assertIn("DIGILINK_READY=no", self.run_fixture().stdout)

    def test_diagnostics_refuses_nonquiet_control(self):
        r = self.run_fixture(inspect=True, ctl=0xe00, ready=1)
        self.assertIn("known quiet transport state", r.stderr)

    def test_diagnostics_refuses_active_dma(self):
        r = self.run_fixture(inspect=True, ctl=0xa00, dma=0x400040, ready=1)
        self.assertIn("known quiet transport state", r.stderr)

    def test_diagnostics_requires_identity_before_controls(self):
        r = self.run_fixture(inspect=True, ctl=0xa00, ready=1)
        self.assertEqual(r.stdout.count("result=1"), 1)
        self.assertNotIn("diagnostic pass=", r.stdout)

    def test_routing_requires_identity_before_queries(self):
        r = self.run_fixture(routing=True, ctl=0xa00, ready=1)
        self.assertEqual(r.stdout.count("result=1"), 1)
        self.assertNotIn("routing pass=", r.stdout)

    def test_routing_refuses_active_dma(self):
        r = self.run_fixture(routing=True, ctl=0xa00, dma=0x400040, ready=1)
        self.assertIn("known quiet transport state", r.stderr)

    def test_ready_without_response_times_out(self):
        r = self.run_fixture(ready=1)
        self.assertEqual(r.stdout.count("result=1"), 8)

    def test_unexpected_version_refused(self):
        self.run_fixture(version=0x01050041)

    def test_unexpected_identity_refused(self):
        self.run_fixture(identity=0xffffffff)

    def test_bus_master_refused(self):
        self.run_fixture(command=0x104, expected=1)

    def test_bound_driver_refused(self):
        self.run_fixture(bound=True, expected=1)

    def test_verify_failure_restores(self):
        self.run_fixture(fault="verify_error", expected=1)

    def test_enable_failure_restores(self):
        self.run_fixture(fault="enable_error", expected=1)

    def test_fatal_signal_restores_pci(self):
        self.run_fixture(fault="sigbus", expected=135)

    def test_cancellation_no_queries(self):
        self.run_fixture(fault="sigterm", ready=1, expected=143)


if __name__ == "__main__":
    unittest.main(verbosity=2)
