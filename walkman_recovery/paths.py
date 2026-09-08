"""Local paths. Works from source and from a frozen exe."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WM1Recovery"
        root.mkdir(parents=True, exist_ok=True)
        return root
    return Path(__file__).resolve().parent.parent


ROOT = data_root()
BUNDLE = resource_root()
VENDOR_MTK = ROOT / "vendor" / "mtk"
VENDOR_STOCK = ROOT / "vendor" / "stockrevert"
TOOLS_MTK = data_root() / "tools" / "mtk"
WORK = ROOT / "work"
LOGS = ROOT / "logs"
BUNDLE_MTK = BUNDLE / "vendor" / "mtk"


def mtk_dir() -> Path | None:
    env = os.environ.get("WM1_MTK_DIR")
    candidates = [Path(env)] if env else []
    candidates.extend([VENDOR_MTK, TOOLS_MTK, BUNDLE_MTK])
    for folder in candidates:
        if folder and (folder / "flash_tool.exe").is_file() and (folder / "DA.bin").is_file():
            return folder
    return None


def flash_tool() -> Path:
    folder = mtk_dir()
    if folder is None:
        raise FileNotFoundError("Missing flash_tool.exe and DA.bin")
    return folder / "flash_tool.exe"


def download_agent() -> Path:
    folder = mtk_dir()
    if folder is None:
        raise FileNotFoundError("Missing DA.bin")
    return folder / "DA.bin"


def wdi_simple() -> Path | None:
    for folder in (VENDOR_MTK, TOOLS_MTK, BUNDLE_MTK, TOOLS_MTK / "wbrt-extracted"):
        path = folder / "wdi-simple.exe"
        if path.is_file():
            return path
    return None


def driver_inf() -> Path | None:
    for folder in (VENDOR_MTK / "driver", BUNDLE_MTK / "driver", TOOLS_MTK / "driver"):
        path = folder / "usb_device.inf"
        if path.is_file():
            return path
    return None


def ensure_work() -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    return WORK
