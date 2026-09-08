"""Launch user-supplied StockRevert / Sony firmware installers."""
from __future__ import annotations

from pathlib import Path
import subprocess
import time

from walkman_recovery.bootstrap import stock_search_dirs


def find_stock_packages(folder: Path) -> tuple[Path | None, Path | None]:
    revert = None
    official = None
    if not folder.is_dir():
        return None, None
    for path in folder.rglob("*.exe"):
        name = path.name.lower()
        if "stockrevert" in name and revert is None:
            revert = path
        elif official is None and (
            ("nw-wm1" in name and "v3" in name.replace(".", ""))
            or name.endswith("v3_02.exe")
            or "v3.02" in name.lower()
        ):
            official = path
    return revert, official


def locate_stock_packages() -> tuple[Path | None, Path | None]:
    for folder in stock_search_dirs():
        revert, official = find_stock_packages(folder)
        if revert is not None:
            return revert, official
    return None, None


def launch(path: Path) -> subprocess.Popen:
    if not path.is_file():
        raise FileNotFoundError(path)
    return subprocess.Popen([str(path)], cwd=str(path.parent))


def wait_closed(proc: subprocess.Popen, timeout: float = 1800) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code = proc.poll()
        if code is not None:
            return code
        time.sleep(1)
    raise TimeoutError("Installer is still running")
