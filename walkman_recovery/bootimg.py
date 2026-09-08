"""Build a guarded temporary boot image from a device's own boot dump.

Never writes to a device. Preserves kernel and original cpio entries except
init.rc plus one added script that calls Sony's native format_contents.
"""
from __future__ import annotations

import gzip
import hashlib
import struct

REPAIR_SCRIPT = b'''#!/bin/sh
LOG=/tmp/wm1a-repair.log
if [ "$1" = save ]; then
    if grep -q ' /contents ' /proc/mounts && [ -f "$LOG" ]; then
        cp "$LOG" /contents/wm1a-repair.log
    fi
    exit 0
fi
exec >"$LOG" 2>&1
echo 'WM1A guarded contents format'
DEV=/emmc@contents
REAL=$(/sbin/busybox readlink -f "$DEV")
NAME=${REAL##*/}
echo "device=$DEV resolved=$REAL"
case "$NAME" in mmcblk0p*) ;; *) echo 'REFUSED: unexpected block device'; exit 1;; esac
START=$(cat /sys/class/block/$NAME/start)
SIZE=$(cat /sys/class/block/mmcblk0/size)
echo "partition_start=$START emmc_sectors=$SIZE"
[ "$START" = PLACEHOLDER_START ] || { echo 'REFUSED: partition start mismatch'; exit 1; }
[ "$SIZE" -gt 234375000 ] && [ "$SIZE" -lt 273437500 ] || { echo 'REFUSED: not 128GB device'; exit 1; }
[ -b "$DEV" ] || { echo 'REFUSED: not a block device'; exit 1; }
MD5=$(/sbin/busybox dd if="$DEV" bs=512 count=1 2>/dev/null | /sbin/busybox md5sum | /sbin/busybox awk '{print $1}')
echo "header_md5=$MD5"
[ "$MD5" = PLACEHOLDER_MD5 ] || { echo 'SKIP: original invalid header no longer present'; exit 0; }
[ -x /system/bin/format_contents ] || { echo 'REFUSED: native formatter missing'; exit 1; }
echo 'Starting native Sony format_contents for /emmc@contents only'
/system/bin/format_contents
RESULT=$?
echo "format_exit=$RESULT"
sync
exit "$RESULT"
'''


def unpack_cpio(data: bytes):
    records = []
    p = 0
    while p + 110 <= len(data):
        header = data[p : p + 110]
        if header[:6] != b"070701":
            raise ValueError("Unsupported cpio format")
        vals = [int(header[6 + i * 8 : 14 + i * 8], 16) for i in range(13)]
        ns, size = vals[11], vals[6]
        name = data[p + 110 : p + 110 + ns]
        q = (p + 110 + ns + 3) & ~3
        content = data[q : q + size]
        if len(content) != size or not name.endswith(b"\0"):
            raise ValueError("Truncated cpio entry")
        records.append((vals, name, content))
        p = (q + size + 3) & ~3
        if name == b"TRAILER!!!\0":
            return records
    raise ValueError("Missing cpio trailer")


def pack_cpio(records) -> bytes:
    result = bytearray()
    for vals, name, content in records:
        vals = list(vals)
        vals[6], vals[11] = len(content), len(name)
        result.extend(b"070701" + b"".join(f"{v:08x}".encode() for v in vals))
        result.extend(name)
        result.extend(bytes((-len(result)) % 4))
        result.extend(content)
        result.extend(bytes((-len(result)) % 4))
    return bytes(result)


def image_parts(data: bytes):
    if data[:8] != b"ANDROID!":
        raise ValueError("Not an Android boot image")
    ks, _, rs, _, ss = struct.unpack_from("<IIIII", data, 8)
    page = struct.unpack_from("<I", data, 36)[0]
    if page != 2048 or ss != 0 or struct.unpack_from("<I", data, 40)[0] != 0:
        raise ValueError("Unexpected boot geometry")
    ro = page + ((ks + page - 1) // page) * page
    end = ro + ((rs + page - 1) // page) * page
    if any(data[end:]):
        raise ValueError("Unexpected data after ramdisk")
    kernel, rd = data[page : page + ks], data[ro : ro + rs]
    digest = hashlib.sha1()
    for blob in (kernel, rd, b""):
        digest.update(blob)
        digest.update(struct.pack("<I", len(blob)))
    if digest.digest() != data[576:596]:
        raise ValueError("Boot SHA-1 mismatch")
    return page, ro, kernel, rd


def build_repair_boot(original: bytes, partition_start: int, header_md5: str) -> bytes:
    page, ro, kernel, rd = image_parts(original)
    if rd[:4] != bytes.fromhex("88168858") or rd[512:515] != b"\x1f\x8b\x08":
        raise ValueError("Unexpected MediaTek header")
    if struct.unpack_from("<I", rd, 4)[0] != len(rd) - 512:
        raise ValueError("MediaTek length mismatch")
    script = REPAIR_SCRIPT.replace(b"PLACEHOLDER_START", str(partition_start).encode()).replace(
        b"PLACEHOLDER_MD5", header_md5.encode()
    )
    records = unpack_cpio(gzip.decompress(rd[512:]))
    old = {name: (v, content) for v, name, content in records}
    if b"sbin/repair_contents.sh\0" in old:
        raise ValueError("Original already modified")
    patched = []
    changed = 0
    for vals, name, content in records:
        if name == b"init.rc\0":
            first = b"    exec /system/bin/fsck_msdos -y /emmc@contents\n"
            second = b"    exec /system/bin/mount_partition cache usrdata var db option1 option3 contents\n"
            if content.count(first) != 1 or content.count(second) != 1:
                raise ValueError("Unexpected init script")
            content = content.replace(first, b"    exec /bin/sh /sbin/repair_contents.sh\n" + first)
            content = content.replace(second, second + b"    exec /bin/sh /sbin/repair_contents.sh save\n")
            changed += 1
        if name == b"TRAILER!!!\0":
            vals_new = list(old[b"sbin/boot_complete.sh\0"][0])
            vals_new[0] = max(r[0][0] for r in records) + 1
            vals_new[1] = 0o100700
            patched.append((vals_new, b"sbin/repair_contents.sh\0", script))
        patched.append((vals, name, content))
    if changed != 1:
        raise ValueError("init.rc not modified")
    gz = gzip.compress(pack_cpio(patched), compresslevel=9, mtime=0)
    mtk = bytearray(rd[:512])
    struct.pack_into("<I", mtk, 4, len(gz))
    newrd = bytes(mtk) + gz
    result = bytearray(original[:ro])
    struct.pack_into("<I", result, 16, len(newrd))
    result.extend(newrd)
    if len(result) > len(original):
        raise ValueError("Patched image exceeds partition")
    result.extend(bytes(len(original) - len(result)))
    digest = hashlib.sha1()
    for blob in (kernel, newrd, b""):
        digest.update(blob)
        digest.update(struct.pack("<I", len(blob)))
    result[576:608] = digest.digest() + bytes(12)
    _, _, newkernel, validated = image_parts(result)
    assert kernel == newkernel
    check = {name: (v, content) for v, name, content in unpack_cpio(gzip.decompress(validated[512:]))}
    for name, (vals, content) in old.items():
        if name != b"init.rc\0":
            assert check[name] == (vals, content), name
    assert check[b"sbin/repair_contents.sh\0"][1] == script
    return bytes(result)
