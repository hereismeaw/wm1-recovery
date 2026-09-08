"""Install the MediaTek Preloader WinUSB driver for other PCs."""
from __future__ import annotations

import subprocess

from walkman_recovery.paths import driver_inf, wdi_simple

PRELOADER_VID = "0x0E8D"
PRELOADER_PID = "0x2000"


def wdi_command(wdi, inf=None) -> list[str]:
    cmd = [
        str(wdi),
        "-n", "MT65xx Preloader",
        "-m", "MediaTek Inc.",
        "-v", PRELOADER_VID,
        "-p", PRELOADER_PID,
        "-t", "0",
        "-s",
    ]
    if inf is not None:
        cmd.extend(["-e", str(inf)])
    return cmd


def install_preloader_driver(log=print) -> None:
    wdi = wdi_simple()
    if wdi is None:
        raise FileNotFoundError("ไม่พบ wdi-simple.exe สำหรับติดตั้งไดรเวอร์ Preloader")
    cmd = wdi_command(wdi, driver_inf())
    log("ติดตั้งไดรเวอร์ WinUSB สำหรับ Preloader VID 0E8D PID 2000...")
    proc = subprocess.run(cmd, cwd=str(wdi.parent), capture_output=True, text=True)
    text = (proc.stdout or "") + (proc.stderr or "")
    if text.strip():
        log(text.strip())
    if proc.returncode != 0:
        raise RuntimeError(f"ติดตั้งไดรเวอร์ไม่สำเร็จ (รหัส {proc.returncode})")
    log("ติดตั้งไดรเวอร์ Preloader แล้ว")
