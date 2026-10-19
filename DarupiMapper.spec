# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DarupiMapper.exe (one file, no console window).
#   pyinstaller --noconfirm DarupiMapper.spec
# Build on Windows to get a Windows exe (PyInstaller cannot cross-compile). See "Build DarupiMapper.bat"
# and .github/workflows/build-exe.yml.

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

datas, binaries, hiddenimports = [], [], []

# librosa loads submodules lazily (lazy_loader + .pyi stubs), so ask for its files explicitly.
datas += collect_data_files("librosa")
datas += collect_data_files("lazy_loader")
hiddenimports += collect_submodules("librosa.core") + collect_submodules("librosa.feature") + [
    "librosa.filters", "librosa.util", "librosa.util.utils", "librosa.util.exceptions", "librosa.util.decorators",
]
# libsndfile / soxr / rosu-pp-py ship native libraries.
for pkg in ("_soundfile_data", "soxr", "rosu_pp_py", "llvmlite", "numba"):
    try:
        binaries += collect_dynamic_libs(pkg)
    except Exception:
        pass
datas += collect_data_files("_soundfile_data")
hiddenimports += ["soxr", "rosu_pp_py", "mutagen", "scipy.special.cython_special", "scipy.ndimage", "scipy.signal"]
for dist in ("rosu-pp-py", "librosa", "numba", "soundfile", "soxr"):   # importlib.metadata lookups
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

# Not used by the generator; keeps the exe smaller.
excludes = ["matplotlib", "pytest", "IPython", "notebook", "jupyter", "pandas", "torch", "tensorflow",
            "PyQt5", "PyQt6", "PySide2", "PySide6", "wx", "sphinx", "docutils", "setuptools", "pip"]

a = Analysis(
    ["darupimapper.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DarupiMapper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                       # UPX makes antivirus false positives more likely
    runtime_tmpdir=None,
    console=False,                   # windowed GUI; command-line use still works, it just prints nothing
    disable_windowed_traceback=False,
)
