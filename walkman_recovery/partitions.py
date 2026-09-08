"""Parse MBR/EBR chains from a raw eMMC prefix dump. No device I/O."""
from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class Partition:
    table_offset: int
    index: int
    type: int
    offset: int
    size: int

    @property
    def start_lba(self) -> int:
        return self.offset // 512


def parse_mbr_ebr(data: bytes) -> list[Partition]:
    queue = [(0, 0)]
    seen: set[int] = set()
    found: list[Partition] = []
    while queue:
        off, base = queue.pop(0)
        if off in seen or off + 512 > len(data):
            continue
        seen.add(off)
        sector = data[off : off + 512]
        if sector[510:512] != b"\x55\xaa":
            continue
        for i in range(4):
            entry = sector[446 + i * 16 : 462 + i * 16]
            typ = entry[4]
            lba, count = struct.unpack_from("<II", entry, 8)
            if not typ:
                continue
            extended = typ in (5, 15, 133)
            absolute = (base if extended and off else off) + lba * 512
            if extended:
                queue.append((absolute, base or absolute))
                continue
            found.append(Partition(off, i, typ, absolute, count * 512))
    return found


def find_android_images(data: bytes) -> list[int]:
    return [i for i in range(0, len(data) - 8, 512) if data[i : i + 8] == b"ANDROID!"]


def classify(parts: list[Partition], prefix: bytes) -> dict[str, Partition]:
    """Best-effort names from a prefix dump that includes boot/recovery."""
    named: dict[str, Partition] = {}
    images = find_android_images(prefix)
    for offset in images:
        for part in parts:
            if part.offset <= offset < part.offset + part.size:
                if "boot" not in named:
                    named["boot"] = part
                elif "recovery" not in named and part.offset != named["boot"].offset:
                    named["recovery"] = part
                break
    remaining = [p for p in parts if p not in named.values()]
    remaining.sort(key=lambda p: p.offset)
    if remaining:
        named["contents"] = remaining[-1]
    return named


def contents_header_kind(sector: bytes) -> str:
    """Classify the first sector of the contents partition."""
    if len(sector) < 512:
        return "short"
    if sector[510:512] == b"\x55\xaa" and sector[0] in (0xEB, 0xE9) and sector[0x52:0x57] == b"FAT32":
        return "fat32"
    if sector[510:512] == b"\x55\xaa" and sector[0x36:0x3B] == b"FAT16":
        return "fat16"
    if sector[510:512] == b"\x55\xaa" and any(sector[446 + i * 16 + 4] for i in range(4)):
        return "mbr"
    if sector[0] in (0xEB, 0xE9) and b"FAT" in sector[0x36:0x5A]:
        return "fat"
    if not any(sector):
        return "empty"
    return "unknown"
