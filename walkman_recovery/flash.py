"""Wrap unknown321 flash_tool.exe. One process at a time."""
from __future__ import annotations

from pathlib import Path
import subprocess

from walkman_recovery.paths import download_agent, ensure_work, flash_tool


class FlashError(RuntimeError):
    pass


def run(args: list[str], log_name: str, timeout: int = 300) -> str:
    tool = flash_tool()
    work = ensure_work()
    log = work.parent / "logs" / log_name
    log.parent.mkdir(exist_ok=True)
    command = [str(tool), *args, "-n"]
    with log.open("w", encoding="utf-8", errors="replace") as stream:
        proc = subprocess.run(
            command, stdout=stream, stderr=subprocess.STDOUT,
            timeout=timeout, cwd=str(tool.parent),
        )
    text = log.read_text(encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FlashError(f"flash_tool exited {proc.returncode}\n{text[-2000:]}")
    return text


def _stage2_or_da(stage2: bool) -> list[str]:
    if stage2:
        return ["-2"]
    return ["-d", str(download_agent())]


def dump(address: int, length: int, dest: Path, stage2: bool, log_name: str) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = _stage2_or_da(stage2) + ["-a", hex(address), "-l", hex(length), "-D", str(dest)]
    return run(args, log_name)


def flash_and_readback(address: int, length: int, source: Path, readback: Path, stage2: bool, log_name: str) -> str:
    if not source.is_file() or source.stat().st_size != length:
        raise FlashError(f"Source image size mismatch: {source}")
    args = _stage2_or_da(stage2) + [
        "-a", hex(address), "-l", hex(length),
        "-F", str(source), "-D", str(readback),
    ]
    return run(args, log_name)


def reboot(stage2: bool = True) -> str:
    work = ensure_work()
    scratch = work / "reboot-probe.bin"
    args = _stage2_or_da(stage2) + ["-a", "0", "-l", "512", "-D", str(scratch), "-R"]
    return run(args, "reboot.log", timeout=60)
