"""Relaunch the app with a Windows Administrator token when needed."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as W
from pathlib import Path
import subprocess
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch() -> bool:
    if is_admin():
        return False
    python = sys.executable
    if sys.argv[0].endswith(".py"):
        params = subprocess.list2cmdline(["-m", "walkman_recovery", *sys.argv[1:]])
        exe = python
        cwd = str(Path(__file__).resolve().parent.parent)
    else:
        params = subprocess.list2cmdline(sys.argv[1:])
        exe = sys.argv[0]
        cwd = str(Path(exe).parent)
    shell = ctypes.windll.shell32.ShellExecuteW
    shell.argtypes = [W.HWND, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, ctypes.c_int]
    shell.restype = ctypes.c_ssize_t
    code = shell(None, "runas", exe, params, cwd, 1)
    if code <= 32:
        raise SystemExit(f"Windows elevation was cancelled or failed (code {code}).")
    return True
