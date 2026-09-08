"""Guided contents repair using Preloader + a temporary boot image."""
from __future__ import annotations

import hashlib
from pathlib import Path

from walkman_recovery.bootimg import build_repair_boot, image_parts
from walkman_recovery.flash import dump, flash_and_readback, reboot
from walkman_recovery.partitions import classify, contents_header_kind, parse_mbr_ebr
from walkman_recovery.paths import ensure_work


class RecoveryError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repair_contents(log, stage2: bool = False) -> Path:
    """Backup boot, flash guarded repair boot, verify readback. Does not reboot."""
    work = ensure_work()
    prefix = work / "prefix32.bin"
    log("อ่านตารางพาร์ติชัน 32 MiB แรก...")
    dump(0, 32 * 1024 * 1024, prefix, stage2, "dump-prefix.log")
    data = prefix.read_bytes()
    parts = parse_mbr_ebr(data)
    named = classify(parts, data)
    if "boot" not in named or "contents" not in named:
        raise RecoveryError("อ่านตารางพาร์ติชันไม่ครบ ยังไม่แฟลชอะไร")
    boot = named["boot"]
    contents = named["contents"]
    log(f"boot @ {boot.offset:#x}  contents @ {contents.offset:#x} (LBA {contents.start_lba})")

    boot_img = work / "boot-original.img"
    log("สำรอง boot เดิม...")
    dump(boot.offset, boot.size, boot_img, True, "dump-boot.log")
    image_parts(boot_img.read_bytes())

    head = work / "contents-head.bin"
    dump(contents.offset, 512, head, True, "dump-contents-head.log")
    kind = contents_header_kind(head.read_bytes())
    log(f"หัวพาร์ติชันเพลง: {kind}")
    if kind == "fat32":
        raise RecoveryError("พาร์ติชันเพลงเป็น FAT32 อยู่แล้ว ไม่ต้องแฟลช boot ซ่อม")
    if kind not in {"mbr", "unknown", "empty", "fat16"}:
        raise RecoveryError(f"หัวพาร์ติชันเพลงเป็น {kind} ยังไม่แฟลช")

    header_md5 = hashlib.md5(head.read_bytes()).hexdigest()
    repair = work / "boot-repair.img"
    log("สร้าง boot ซ่อมชั่วคราวจากไฟล์สำรองของเครื่องนี้...")
    repair.write_bytes(build_repair_boot(boot_img.read_bytes(), contents.start_lba, header_md5))

    before = work / "boot-before-write.img"
    dump(boot.offset, boot.size, before, True, "prewrite-boot.log")
    if sha256(before) != sha256(boot_img):
        raise RecoveryError("boot บนเครื่องไม่ตรงกับไฟล์สำรอง ยกเลิกการเขียน")

    readback = work / "boot-repair-readback.img"
    log("เขียน boot ซ่อมแล้วอ่านกลับเทียบ...")
    flash_and_readback(boot.offset, boot.size, repair, readback, True, "flash-repair-boot.log")
    if sha256(repair) != sha256(readback):
        raise RecoveryError("อ่านกลับไม่ตรงกับไฟล์ที่เขียน อย่ารีบูต")
    log(f"SHA256 ตรงกัน: {sha256(readback)}")
    return boot_img


def restore_boot(original: Path, log, stage2: bool = True) -> None:
    work = ensure_work()
    if not original.is_file():
        raise RecoveryError("ไม่พบไฟล์ boot เดิม")
    length = original.stat().st_size
    prefix = work / "prefix32.bin"
    if not prefix.is_file():
        dump(0, 32 * 1024 * 1024, prefix, stage2, "dump-prefix-restore.log")
    named = classify(parse_mbr_ebr(prefix.read_bytes()), prefix.read_bytes())
    boot = named["boot"]
    if boot.size != length:
        raise RecoveryError("ขนาดไฟล์ boot ไม่ตรงกับพาร์ติชัน")
    readback = work / "boot-original-readback.img"
    log("คืน boot เดิมแล้วอ่านกลับเทียบ...")
    flash_and_readback(boot.offset, boot.size, original, readback, True, "restore-boot.log")
    if sha256(original) != sha256(readback):
        raise RecoveryError("อ่านกลับไม่ตรงกับ boot เดิม อย่ารีบูต")
    log(f"คืน boot เดิมแล้ว SHA256 {sha256(readback)}")


def reboot_device(log) -> None:
    log("สั่งรีบูตผ่าน Download Agent...")
    reboot(True)
