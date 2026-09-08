"""Local paths. Vendor binaries are never required to be in git."""
from __future__ import annotations

from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
VENDOR_MTK = ROOT / "vendor" / "mtk"
TOOLS_MTK = ROOT / "tools" / "mtk"
WORK = ROOT / "work"
LOGS = ROOT / "logs"


def mtk_dir() -> Path | None:
    env = os.environ.get("WM1_MTK_DIR")
    candidates = [Path(env)] if env else []
    candidates.extend([VENDOR_MTK, TOOLS_MTK])
    for folder in candidates:
        if (folder / "flash_tool.exe").is_file() and (folder / "DA.bin").is_file():
            return folder
    return None


def flash_tool() -> Path:
    folder = mtk_dir()
    if folder is None:
        raise FileNotFoundError(
            "Missing vendor/mtk/flash_tool.exe and DA.bin. See vendor/mtk/README.md."
        )
    return folder / "flash_tool.exe"


def download_agent() -> Path:
    folder = mtk_dir()
    if folder is None:
        raise FileNotFoundError("Missing DA.bin. See vendor/mtk/README.md.")
    return folder / "DA.bin"


def ensure_work() -> Path:
    WORK.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    return WORK
