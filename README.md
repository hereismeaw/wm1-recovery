# WM1 Recovery

Windows app that recovers a Sony **NW-WM1A / NW-WM1Z** after a contents-partition bootloop, and can take a Walkman One install back to stock firmware.

Python 3.13, standard library only. Thai-first UI, large buttons, one action at a time.

## What it does

- Detects Walkman USB, Preloader, stock vs Walkman One, and whether the music volume is mounted
- Deletes leftover Walkman One files (`CFW\`, `wm1a-repair.log`) on the Walkman disk only
- Optionally dumps this device’s partition map and boot, flashes a **temporary** repair boot, lets Sony’s own `format_contents` rebuild the music partition, then restores the original boot after a verified read-back
- Launches **your** StockRevert + official Sony 3.02 installers (those files are not included)

It never selects a disk by `PhysicalDrive` number. SCSI and cleanup run only on `SONY` / `WALKMAN` / USB.

## What is not in git

Device dumps, boot images, `DA.bin`, `flash_tool.exe`, StockRevert, and Sony firmware EXEs stay on your PC. Publishing them would leak a specific player and third-party firmware.

## Run

Windows 10/11, Python 3, Administrator recommended:

```bat
Start-WM1-Recovery.cmd
```

or:

```bat
python -m walkman_recovery
```

## Preloader tools

Clicking **กู้พาร์ติชันเพลง** downloads `flash_tool.exe` (and `DA.bin` via wbrt + 7-Zip) into `vendor/mtk/` when they are missing. Existing files in `tools/mtk/` are reused. These binaries stay gitignored.

Preloader entry (USB already connected): hold **Volume Down + Play**, then hold **Power 8–10 seconds**. Keep the first two buttons down about 10 seconds after releasing Power.

## Stock firmware

Walkman One / Sony installers are **not** downloaded. If you have them, put both EXEs in `vendor/stockrevert/` (or leave them in `research/stockrevert/`). The app picks them up automatically; otherwise it asks for a folder.

1. Connect the player in mass-storage mode.
2. Click **กลับเฟิร์มสต็อก**.
3. Watch the update bar on the player. Do not unplug.

## Tests

```bat
python -m unittest discover -v tests
```

## Safety

- Music on the contents partition is erased by format / StockRevert
- Boot is written only after a same-device backup and a full SHA-256 read-back
- PC disks are never targeted
- You must supply Sony / MrWalkman installers yourself

## License

MIT for this repository’s Python. MediaTek flash tool, wbrt, Walkman One, and Sony firmware remain under their own terms.
