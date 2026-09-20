#!/usr/bin/env python3
"""Verify actual C tone helper against fixed S24_LE vectors; no PCI access."""
from pathlib import Path
import math
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="native-tone-test-") as d:
    p = Path(d)
    (p / "test.c").write_text('''
#include <stdio.h>
#include "native_tone.h"
static unsigned char buffer[8192 * 256];
int main(int argc, char **argv) {
    (void)argv;
    native_fill_tone(buffer, argc > 1);
    return fwrite(buffer, 1, sizeof(buffer), stdout) != sizeof(buffer);
}
''')
    subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                    "-I" + str(root / "kernel"), str(p / "test.c"),
                    "-o", str(p / "test")], check=True)
    for frames in (1024, 6144):
        data = subprocess.check_output([str(p / "test")] + (["long"] if frames == 6144 else []))
        assert len(data) == 8192 * 256
        # Fixed byte vectors at steady-state positive/negative sine peaks.
        assert data[156*256+4:156*256+10] == bytes.fromhex("ae4701ae4701")
        assert data[132*256+4:132*256+10] == bytes.fromhex("52b8fe52b8fe")
        peak = 0
        for frame in range(frames):
            b = data[frame*256:(frame+1)*256]
            assert b[:4] == bytes(4) and b[10:] == bytes(246)
            assert b[4:7] == b[7:10]
            value = int.from_bytes(b[4:7], "little", signed=True)
            peak = max(peak, abs(value))
            edge = min(frame, frames-1-frame, 128)
            expected = int(round(83886*math.sin(2*math.pi*(frame%48)/48))*edge/128)
            assert value == expected
        assert data[:256] == bytes(256)
        assert data[(frames-1)*256:] == bytes((8192-frames+1)*256)
        assert peak == 83886 and abs(20*math.log10(peak/8388607) + 40) < 0.001

print("PASS: 1024/6144-frame bursts, S24_LE peak vectors, two channels, zero headers/padding/other channels, ramps, silence tail, -40 dBFS limit")
