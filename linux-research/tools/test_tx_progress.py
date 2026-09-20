#!/usr/bin/env python3
"""Replay TX observations through the actual transfer_pcm function, no hardware."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "kernel/avid_native_dma_probe.c").read_text()
start = source.index("static int transfer_pcm(")
end = source.index("static bool stop_dma(", start)
transfer = source[start:end]
harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
typedef unsigned int u32;
typedef unsigned long long ktime_t;
struct experiment { void *pdev; };
#define DMA_CTL 0x42004
#define DL_CTL 0x70000
#define DL_STATUS 0x70004
#define CTL 0x10
#define DMA_ENABLE 0x400040
#define CORE_ENABLE 0x10f0000
#define STREAM_ENABLE 0x400
#define dev_info(...) ((void)0)
static bool run_tone=true, tone_long=true;
static unsigned int tx_mmio_first,tx_mmio_last,tx_mmio_changes;
static unsigned int tx_consumed, status_sequence, pos, step, mock_status;
static ktime_t now;
static u32 rd(struct experiment *e, unsigned int off) {
    (void)e; return off==0x41058 ? pos : 0;
}
static void wr(struct experiment *e,unsigned int off,unsigned int value) {
    (void)e; (void)off; (void)value;
}
static void flush(struct experiment *e) { (void)e; }
static void dma_wmb(void) {}
static void pci_set_master(void *p) { (void)p; }
static ktime_t ktime_get(void) { return now; }
static ktime_t ktime_add_ms(ktime_t t,unsigned int ms) { return t+ms*1000; }
static int ktime_before(ktime_t a,ktime_t b) { return a<b; }
static void usleep_range(unsigned int lo,unsigned int hi) {
    (void)hi; now+=lo; if(lo>=1000)pos=(pos+step)&8191;
}
static void sample_status(struct experiment *e) {
    (void)e; tx_consumed=mock_status; status_sequence=2;
}
'''
cases = r'''
int main(void) {
    struct experiment e={0};
    pos=9; step=48; mock_status=0;
    assert(transfer_pcm(&e)==0); /* Observed regression: memory TX stays zero. */
    assert(tx_mmio_first==9 && tx_mmio_last>=7168 && tx_consumed==0);
    assert(status_sequence==2 && tx_mmio_changes>0);
    pos=9; step=0; mock_status=9;
    assert(transfer_pcm(&e)==-ETIMEDOUT); /* Earlier progress cannot mask a stall. */
    assert(tx_mmio_changes>0 && tx_consumed==9);
    tx_mmio_changes=0; pos=0; mock_status=0;
    assert(transfer_pcm(&e)==-ETIMEDOUT);
    tone_long=false; run_tone=false; pos=0; step=48;
    assert(transfer_pcm(&e)==0);
    puts("PASS: MMIO progress with stale DMA snapshot; per-burst stall detection; silence mode");
}
'''
with tempfile.TemporaryDirectory(prefix="native-tx-progress-") as d:
    p = Path(d)
    (p / "test.c").write_text(harness + transfer + cases)
    subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                    str(p / "test.c"), "-o", str(p / "test")], check=True)
    subprocess.run([str(p / "test")], check=True, timeout=5)
