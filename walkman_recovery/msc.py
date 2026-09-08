"""Find the Walkman mass-storage volume and remove Walkman One leftovers.

Never formats, and never touches a volume that is not a SONY WALKMAN USB disk.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from dataclasses import dataclass

WALKMAN_ONE_DIRS = ("CFW",)
WALKMAN_ONE_FILES = ("wm1a-repair.log",)
KEEP = {
    "MUSIC",
    "default-capability.xml",
    "DevLogo.fil",
    "DevIcon.fil",
    "System Volume Information",
}


@dataclass
class Volume:
    letter: str
    label: str
    filesystem: str
    size: int
    disk_serial: str
    pnp: str
    has_cfw: bool = False


def _ps(command: str) -> str:
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True, text=True, timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return proc.stdout


def list_walkman_volumes() -> list[Volume]:
    command = r"""
$disks = Get-CimInstance Win32_DiskDrive | Where-Object {
  $_.Model -match 'WALKMAN' -and $_.InterfaceType -eq 'USB'
}
foreach ($d in $disks) {
  $parts = Get-Partition -DiskNumber $d.Index -ErrorAction SilentlyContinue
  foreach ($p in $parts) {
    if (-not $p.DriveLetter) { continue }
    $vol = Get-Volume -DriveLetter $p.DriveLetter -ErrorAction SilentlyContinue
    if (-not $vol) { continue }
    $letter = $p.DriveLetter
    $cfw = Test-Path -LiteralPath ($letter + ':\CFW')
    Write-Output ($letter + '|' + ($vol.FileSystemLabel -replace '\|',' ') + '|' + $vol.FileSystem + '|' + [int64]$vol.Size + '|' + $d.SerialNumber + '|' + $d.PNPDeviceID + '|' + $cfw)
  }
}
"""
    volumes: list[Volume] = []
    try:
        text = _ps(command)
    except (OSError, subprocess.TimeoutExpired):
        return volumes
    for line in text.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 7:
            continue
        letter, label, fs, size, serial, pnp, cfw = parts
        if "WALKMAN" not in pnp.upper() and "WALKMAN" not in label.upper():
            continue
        volumes.append(Volume(
            letter=letter, label=label, filesystem=fs or "",
            size=int(size or 0), disk_serial=serial, pnp=pnp,
            has_cfw=cfw.strip().lower() == "true",
        ))
    return volumes


def leftovers_on(root: Path) -> list[Path]:
    found: list[Path] = []
    for name in WALKMAN_ONE_DIRS:
        path = root / name
        if path.is_dir():
            found.append(path)
    for name in WALKMAN_ONE_FILES:
        path = root / name
        if path.is_file():
            found.append(path)
    return found


def clean_walkman_one(volume: Volume) -> list[str]:
    if "WALKMAN" not in volume.pnp.upper():
        raise ValueError("Refusing to clean a disk that is not SONY WALKMAN")
    root = Path(f"{volume.letter}:/")
    if not root.exists():
        raise FileNotFoundError(f"Volume {volume.letter}: is not mounted")
    removed: list[str] = []
    for path in leftovers_on(root):
        if path.name in KEEP:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(str(path))
    return removed
