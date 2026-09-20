#!/usr/bin/env python3
"""Index PE64 strings, exports and unwind function ranges without running code.

Optional objdump output links RIP-relative references to matching strings.
These are evidence locations, not an automatically recovered hardware protocol.
"""
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import struct


class PE:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        b = self.data
        if b[:2] != b"MZ":
            raise ValueError("Not a PE image")
        pe = struct.unpack_from("<I", b, 0x3c)[0]
        if b[pe:pe + 4] != b"PE\0\0":
            raise ValueError("Bad PE signature")
        _, count, _, _, _, opt_size, _ = struct.unpack_from("<HHIIIHH", b, pe + 4)
        opt = pe + 24
        if struct.unpack_from("<H", b, opt)[0] != 0x20b:
            raise ValueError("Expected PE32+")
        self.base = struct.unpack_from("<Q", b, opt + 24)[0]
        self.dirs = [struct.unpack_from("<II", b, opt + 112 + 8 * i) for i in range(16)]
        self.sections = []
        for i in range(count):
            o = opt + opt_size + 40 * i
            name, size, va, rawsize, raw = struct.unpack_from("<8sIIII", b, o)
            self.sections.append((name.rstrip(b"\0").decode(), va, size, raw, rawsize))
        self.functions = []
        rva, size = self.dirs[3]
        if rva:
            o = self.offset(rva)
            for j in range(0, size, 12):
                start, end, unwind = struct.unpack_from("<III", b, o + j)
                if start and end > start:
                    self.functions.append((self.base + start, self.base + end))
        self.functions.sort()
        self.starts = [x[0] for x in self.functions]

    def offset(self, rva):
        for _, va, _, raw, rawsize in self.sections:
            if va <= rva < va + rawsize:
                return raw + rva - va
        raise ValueError(f"RVA not file-backed: {rva:x}")

    def va(self, offset):
        for _, va, _, raw, rawsize in self.sections:
            if raw <= offset < raw + rawsize:
                return self.base + va + offset - raw
        return None

    def cstring(self, rva):
        o = self.offset(rva)
        return self.data[o:self.data.index(b"\0", o)].decode("ascii", "replace")

    def exports(self):
        rva, size = self.dirs[0]
        if not rva:
            return []
        o = self.offset(rva)
        _, _, _, _, _, ordinal_base, _, n, functions, names, ordinals = struct.unpack_from("<IIHHIIIIIII", self.data, o)
        result = []
        for i in range(n):
            nrva = struct.unpack_from("<I", self.data, self.offset(names) + 4 * i)[0]
            ordinal = struct.unpack_from("<H", self.data, self.offset(ordinals) + 2 * i)[0]
            target = struct.unpack_from("<I", self.data, self.offset(functions) + 4 * ordinal)[0]
            result.append({"name": self.cstring(nrva), "va": hex(self.base + target),
                           "ordinal": ordinal_base + ordinal,
                           "forwarder": self.cstring(target) if rva <= target < rva + size else None})
        return result

    def function(self, va):
        i = bisect.bisect_right(self.starts, va) - 1
        if i >= 0 and va < self.functions[i][1]:
            return [hex(x) for x in self.functions[i]]
        return None


def analyze(path, pattern, disasm=None):
    pe = PE(path)
    matches = []
    targets = {}
    for m in re.finditer(rb"[\x20-\x7e]{7,}", pe.data):
        value = m.group().decode("ascii")
        if not pattern.search(value):
            continue
        va = pe.va(m.start())
        entry = {"offset": hex(m.start()), "va": hex(va) if va else None,
                 "string": value, "references": []}
        matches.append(entry)
        if va:
            targets[va] = entry
    if disasm:
        with Path(disasm).open() as f:
            for line in f:
                m = re.search(r"^\s*([0-9a-f]+):.*#\s*(?:0x)?([0-9a-f]+)", line)
                if m and int(m[2], 16) in targets:
                    addr = int(m[1], 16)
                    targets[int(m[2], 16)]["references"].append({
                        "instruction": line.strip(), "function_range": pe.function(addr)})
    return {"file": str(path), "sha256": hashlib.sha256(pe.data).hexdigest(),
            "image_base": hex(pe.base), "function_ranges": len(pe.functions),
            "strings": matches, "exports": [e for e in pe.exports() if pattern.search(e["name"])]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--disasm", type=Path)
    parser.add_argument("--pattern", default=r"HDNative|ProToolsNative_FW|IOCTL_|192 I/O|D400")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.dumps(analyze(args.binary, re.compile(args.pattern, re.I), args.disasm), indent=2) + "\n"
    if args.output:
        args.output.write_text(data)
    else:
        print(data, end="")
