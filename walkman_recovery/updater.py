"""Launch user-supplied StockRevert / Sony firmware installers."""
from __future__ import annotations

from pathlib import Path
import subprocess
import time


def find_stock_packages(folder: Path) -> tuple[Path | None, Path | None]:
    revert = None
    official = None
    for path in folder.rglob("*.exe"):
        name = path.name.lower()
        if "stockrevert" in name and revert is None:
            revert = path
        elif "nw-wm1" in name and "v3" in name.replace(".", "") and official is None:
            official = path
        elif name.endswith("v3_02.exe") or "v3.02" in name.lower():
            official = path
    return revert, official


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
