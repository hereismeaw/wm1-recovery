# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
mtk = root / "vendor" / "mtk"
datas = []
for rel in ("flash_tool.exe", "DA.bin", "wdi-simple.exe"):
    src = mtk / rel
    if src.is_file():
        datas.append((str(src), "vendor/mtk"))
driver = mtk / "driver"
if driver.is_dir():
    datas.append((str(driver), "vendor/mtk/driver"))

a = Analysis(
    ["walkman_recovery/__main__.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=["tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.scrolledtext"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WM1Recovery",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WM1Recovery",
)
