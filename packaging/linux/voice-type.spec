# PyInstaller spec for Linux onedir portable build.
# Run from repo root: pyinstaller --noconfirm --clean packaging/linux/voice-type.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent.parent
sys.path.insert(0, str(ROOT))

a = Analysis(
    [str(ROOT / "packaging" / "linux" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=["evdev", "pynput"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "pytest", "tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="voice-type",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="voice-type",
)
