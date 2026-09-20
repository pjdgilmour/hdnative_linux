#!/usr/bin/env python3
"""Read-only inventory of Pro Tools firmware and DIO files.

Checks the observed 32-byte firmware wrapper and compares payload MD5 with
its embedded checksum. This is not signature/authenticity verification and
does not decide which image should be programmed into a device.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from pe_evidence import PE


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def inventory(root, extracted=None):
    dsi_path = root / "DIO_64" / "DSI.dll"
    dsi = PE(dsi_path)
    firmware = []
    for path in sorted(root.glob("*.bin")):
        data = path.read_bytes()
        item = {"path": str(path), "bytes": len(data), "sha256": digest(path)}
        if len(data) < 32 or data[4:8] != b"taem":
            item["recognized_wrapper"] = False
            firmware.append(item)
            continue
        expected = data[8:24]
        actual = hashlib.md5(data[32:]).digest()
        item.update({
            "recognized_wrapper": True,
            "wrapper_u32_00": struct.unpack_from("<I", data, 0)[0],
            "wrapper_magic_u32_04": hex(struct.unpack_from("<I", data, 4)[0]),
            "target_u16_18": hex(struct.unpack_from("<H", data, 24)[0]),
            "metadata_bytes_1a_1f": data[26:32].hex(),
            "payload_bytes": len(data) - 32,
            "embedded_md5": expected.hex(), "computed_payload_md5": actual.hex(),
            "payload_md5_matches": expected == actual,
            "dsi_digest_records": [],
        })
        # Record candidate table entries only when both digest and referenced
        # filename match; this avoids treating arbitrary byte hits as metadata.
        for match in re.finditer(re.escape(expected), dsi.data):
            offset = match.start()
            if offset + 40 > len(dsi.data):
                continue
            ptr = struct.unpack_from("<Q", dsi.data, offset + 24)[0]
            try:
                name = dsi.cstring(ptr - dsi.base)
            except (ValueError, IndexError):
                continue
            if name != path.name:
                continue
            target, extra = struct.unpack_from("<II", dsi.data, offset + 32)
            va = dsi.va(offset)
            item["dsi_digest_records"].append({
                "rva": hex(va - dsi.base) if va else None,
                "filename": name,
                "metadata_bytes_10_17": dsi.data[offset + 16:offset + 24].hex(),
                "target_u32_20": hex(target), "uninterpreted_u32_24": hex(extra),
            })
        firmware.append(item)
    comparison = []
    old = list(extracted.iterdir()) if extracted and extracted.is_dir() else []
    for path in sorted((root / "DIO_64").iterdir()):
        if not path.is_file():
            continue
        sha = digest(path)
        candidates = [p for p in old if p.is_file() and
                      (p.name.lower() == path.name.lower() or
                       p.name.lower().startswith(path.name.lower() + "."))]
        comparison.append({"name": path.name, "bytes": path.stat().st_size,
                           "sha256": sha,
                           "identical_to": [str(p) for p in candidates if digest(p) == sha]})
    return {"source": str(root), "dsi_sha256": digest(dsi_path),
            "firmware": firmware, "dio_comparison": comparison,
            "scope": "offline file inspection only; no hardware access or firmware writes"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protools_directory", type=Path)
    parser.add_argument("--extracted-driver", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inventory(args.protools_directory, args.extracted_driver)
    data = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(data)
        print(f"Firmware files: {len(result['firmware'])}")
        print("Valid internal MD5:", sum(x.get("payload_md5_matches", False) for x in result["firmware"]))
        print("DIO files:", len(result["dio_comparison"]))
        print("DIO identical to driver:", sum(bool(x["identical_to"]) for x in result["dio_comparison"]))
    else:
        print(data, end="")
