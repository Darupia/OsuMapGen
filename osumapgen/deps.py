"""Dependency detection with actionable messages."""

from __future__ import annotations

import importlib
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

REQUIRED_MODULES = [
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("librosa", "librosa"),
    ("soundfile", "soundfile"),
    ("rosu_pp_py", "rosu-pp-py"),
    ("mutagen", "mutagen"),
]

REPAIR_HINT = ("Download DarupiMapper.exe again to repair it." if getattr(sys, "frozen", False)
               else 'Double-click "Setup or Repair.bat" in the OsuMapGen folder to reinstall them.')


@dataclass
class DepReport:
    missing_modules: List[str]
    ffmpeg: Optional[str]
    ffprobe: Optional[str]

    @property
    def ok(self) -> bool:
        return not self.missing_modules

    def describe(self) -> str:
        lines = []
        if self.missing_modules:
            lines.append("Missing Python packages: " + ", ".join(self.missing_modules) + ". " + REPAIR_HINT)
        if not self.ffmpeg:
            lines.append("FFmpeg not found: MP3 decoding will use the built-in libsndfile decoder "
                         "(works for normal MP3s). Installing FFmpeg is optional.")
        return "\n".join(lines) or "All dependencies available."


def find_ffmpeg(tool: str = "ffmpeg") -> Optional[str]:
    found = shutil.which(tool)
    if found:
        return found
    # common user-level locations (winget installs, portable folder next to the app)
    candidates = [Path(__file__).resolve().parent.parent / "ffmpeg" / "bin" / f"{tool}.exe"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        winget = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if winget.is_dir():
            candidates.extend(sorted(winget.glob(f"*FFmpeg*/*/bin/{tool}.exe")))
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def check_dependencies() -> DepReport:
    missing = []
    for mod, pip_name in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
        except Exception:  # ImportError or a broken binary wheel
            missing.append(pip_name)
    return DepReport(missing, find_ffmpeg("ffmpeg"), find_ffmpeg("ffprobe"))
