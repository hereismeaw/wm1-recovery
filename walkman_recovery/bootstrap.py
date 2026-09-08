"""Fetch Preloader tools. StockRevert/Sony EXEs are never downloaded."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import urllib.request
from pathlib import Path

from walkman_recovery.paths import ROOT, TOOLS_MTK, VENDOR_MTK, VENDOR_STOCK, mtk_dir

FLASH_TOOL_URL = "https://github.com/unknown321/mediatek_flash_tool/releases/download/v0.1.7/flash_tool.exe"
FLASH_TOOL_SHA256 = "84ca8686154afb51aef65e2460e030dd8d6cdf02690bbc9edb35d5fbc693c45f"
WBRT_URL = "https://github.com/unknown321/wbrt/releases/download/v1.0.9/walkman-backup-restore-tool.v1.0.9.exe"

_SEVEN = Path(r"C:\Program Files\7-Zip\7z.exe")
_UA = "WM1-Recovery/0.1"


def _download(url: str, dest: Path, log) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    log(f"ดาวน์โหลด {url}")
    with urllib.request.urlopen(req, timeout=120) as src, dest.open("wb") as out:
        shutil.copyfileobj(src, out)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_if_present(src: Path, dest: Path, log) -> bool:
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        return True
    shutil.copy2(src, dest)
    log(f"คัดลอก {src.name}")
    return True


def ensure_mtk_tools(log=print) -> Path:
    existing = mtk_dir()
    if existing is not None:
        return existing
    VENDOR_MTK.mkdir(parents=True, exist_ok=True)
    tool = VENDOR_MTK / "flash_tool.exe"
    da = VENDOR_MTK / "DA.bin"
    if not tool.is_file():
        if not _copy_if_present(TOOLS_MTK / "flash_tool.exe", tool, log):
            _download(FLASH_TOOL_URL, tool, log)
            if _sha256(tool) != FLASH_TOOL_SHA256:
                tool.unlink(missing_ok=True)
                raise RuntimeError("flash_tool.exe checksum mismatch")
    if not da.is_file():
        copied = _copy_if_present(TOOLS_MTK / "DA.bin", da, log) or _copy_if_present(
            TOOLS_MTK / "wbrt-extracted" / "DA.bin", da, log
        )
        if not copied:
            archive = VENDOR_MTK / "wbrt-setup.exe"
            _download(WBRT_URL, archive, log)
            if not _SEVEN.is_file():
                raise RuntimeError("ต้องมี 7-Zip เพื่อแกะ DA.bin จาก wbrt")
            subprocess.run(
                [str(_SEVEN), "e", "-y", f"-o{VENDOR_MTK}", str(archive), "DA.bin"],
                check=True, capture_output=True,
            )
    folder = mtk_dir()
    if folder is None:
        raise RuntimeError("ยังไม่มี flash_tool.exe และ DA.bin")
    log(f"เครื่องมือ Preloader พร้อมที่ {folder}")
    return folder


def stock_search_dirs() -> list[Path]:
    dirs = [
        VENDOR_STOCK,
        ROOT / "research" / "stockrevert",
        ROOT,
        TOOLS_MTK.parent,
    ]
    return [path for path in dirs if path.is_dir()]
