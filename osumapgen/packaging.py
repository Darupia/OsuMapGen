"""Output folder layout, .osz packaging and launching osu!."""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from .serializer import ascii_fallback, safe_filename


def make_output_folder(base: Path, artist: str, title: str, stars: float, style_label: str) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
    name = safe_filename(f"{ascii_fallback(artist) or 'Unknown Artist'} - {ascii_fallback(title) or 'Unknown Title'}"
                         f" [{stars:.1f} stars {style_label}] {stamp}", 150)
    room = 200 - len(str(Path(base).resolve()))
    if len(name) > room:
        tail = f" [{stars:.1f}] {stamp}"
        name = safe_filename(name[:max(8, room - len(tail))] + tail, 150)
    folder = Path(base) / name
    n = 2
    while folder.exists():
        folder = Path(base) / f"{name} ({n})"
        n += 1
    folder.mkdir(parents=True)
    return folder


def audio_filename(src: str) -> str:
    return "audio" + Path(src).suffix.lower()


def build_osz(folder: Path, osu_name: str, audio_name: str, osz_name: str) -> Path:
    osz = folder / osz_name
    tmp = osz.with_suffix(".osz.part")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(folder / osu_name, arcname=osu_name)
        # audio is already compressed; store it
        z.write(folder / audio_name, arcname=audio_name, compress_type=zipfile.ZIP_STORED)
    os.replace(tmp, osz)
    return osz


def copy_audio(src: str, folder: Path) -> str:
    name = audio_filename(src)
    shutil.copyfile(src, folder / name)
    return name


# ---------------------------------------------------------------- osu! client

def find_osu() -> Optional[Path]:
    local = os.environ.get("LOCALAPPDATA", "")
    for p in (Path(local) / "osulazer" / "osu!.exe", Path(local) / "osu!" / "osu!.exe"):
        if p.is_file():
            return p
    return None


def osu_client_name() -> str:
    p = find_osu()
    if p is None:
        return ""
    return "osu!lazer" if "osulazer" in str(p).lower() else "osu!stable"


def open_in_osu(osz: Path) -> str:
    """Hand the package to osu! (which imports it). Returns a status message."""
    exe = find_osu()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if exe is not None:
        subprocess.Popen([str(exe), str(osz)], creationflags=flags, close_fds=True)
        return f"Sent to {osu_client_name()} for import."
    if hasattr(os, "startfile"):
        try:
            os.startfile(str(osz))  # uses the .osz file association if any
            return "Opened with the program associated with .osz files."
        except OSError:
            pass
    return "osu! was not found. Double-click the .osz file after installing osu! to import it."


def open_folder(path: Path) -> None:
    if hasattr(os, "startfile"):
        os.startfile(str(path))
    else:
        subprocess.Popen(["xdg-open", str(path)])
