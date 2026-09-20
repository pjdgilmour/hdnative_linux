#!/usr/bin/env python3
"""Read PCI metadata only: never mmap BARs, write config or bind a driver."""
import argparse
import datetime
import json
import os
from pathlib import Path
import struct
import subprocess


def snapshot():
    result = {
        "time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "kernel": os.uname().release,
        "devices": [],
        "scope": "PCI metadata only; does not detect DigiLink peripherals",
    }
    for p in sorted(Path("/sys/bus/pci/devices").iterdir()):
        if (p / "vendor").read_text().strip() != "0x11af":
            continue
        d = {"bdf": p.name}
        for key in ("vendor", "device", "subsystem_vendor", "subsystem_device",
                    "class", "revision", "enable", "irq", "resource", "modalias"):
            try:
                d[key] = (p / key).read_text().strip()
            except OSError as e:
                d[key] = {"error": str(e)}
        for key in ("driver", "iommu_group"):
            d[key] = (p / key).resolve().name if (p / key).exists() else None
        try:
            with (p / "config").open("rb", buffering=0) as f:
                header = f.read(64)
            d["config_header_hex"] = header.hex()
            if len(header) >= 6:
                command = struct.unpack_from("<H", header, 4)[0]
                d["pci_command"] = {
                    "value": hex(command), "memory_decode": bool(command & 2),
                    "bus_master": bool(command & 4),
                }
        except OSError as e:
            d["config_error"] = str(e)
        proc = subprocess.run(["lspci", "-nnk", "-s", p.name],
                              text=True, capture_output=True, check=False)
        d["lspci"] = proc.stdout
        d["lspci_error"] = proc.stderr
        result["devices"].append(d)
    try:
        result["alsa_cards"] = Path("/proc/asound/cards").read_text()
    except OSError as e:
        result["alsa_error"] = str(e)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.dumps(snapshot(), indent=2) + "\n"
    if args.output:
        args.output.write_text(data)
    print(data, end="")
