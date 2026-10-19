"""Click-track timing preview: the song mixed with a click at every hit object.

Lets the user check the map's timing by ear without opening osu!. Slider and
spinner heads get a full click, slider repeats/ends and spinner ends a softer
one, and new-combo objects a higher pitch.
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from . import audio_io
from .deps import find_ffmpeg
from .infra import get_logger
from .model import AudioInfo, HitObject

PREVIEW_SR = 44100
PREVIEW_STEM = "preview with clicks"
SONG_GAIN = 0.6

# (frequency Hz, amplitude) per click kind
CLICKS = {"head": (2000.0, 0.55), "combo": (3200.0, 0.6), "tail": (1300.0, 0.28)}

log = get_logger("preview")


def click_events(objects: List[HitObject]) -> List[Tuple[float, str]]:
    """(time_ms, kind) for every audible point of the map."""
    ev: List[Tuple[float, str]] = []
    for o in objects:
        ev.append((float(o.time_ms), "combo" if o.new_combo else "head"))
        if o.kind == "slider" and o.end_time_ms > o.time_ms:
            span = (o.end_time_ms - o.time_ms) / max(1, o.slides)
            ev += [(o.time_ms + k * span, "tail") for k in range(1, max(1, o.slides) + 1)]
        elif o.kind == "spinner" and o.end_time_ms > o.time_ms:
            ev.append((float(o.end_time_ms), "tail"))
    return ev


def _click(freq: float, amp: float, sr: int) -> np.ndarray:
    n = int(0.03 * sr)
    t = np.arange(n) / sr
    env = np.minimum(1.0, t / 0.0005) * np.exp(-t / 0.006)
    return (amp * env * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def mix(song: np.ndarray, sr: int, events: List[Tuple[float, str]]) -> np.ndarray:
    out = song.astype(np.float32) * SONG_GAIN
    shapes = {k: _click(f, a, sr) for k, (f, a) in CLICKS.items()}
    for t_ms, kind in events:
        i = int(round(t_ms / 1000.0 * sr))
        if i < 0 or i >= len(out):
            continue
        c = shapes[kind]
        j = min(len(out), i + len(c))
        out[i:j] += c[: j - i]
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 0.98:
        out *= 0.98 / peak
    return out


def _encode(y: np.ndarray, sr: int, folder: Path) -> Path:
    ffmpeg = find_ffmpeg("ffmpeg")
    if ffmpeg:
        dest = folder / f"{PREVIEW_STEM}.mp3"
        pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
        cmd = [ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-",
               "-codec:a", "libmp3lame", "-b:a", "160k", str(dest)]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(cmd, input=pcm, capture_output=True, creationflags=flags, timeout=600)
            if proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
                return dest
            log.warning("ffmpeg could not encode the preview: %s",
                        proc.stderr.decode("utf-8", "replace").strip()[:300])
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("ffmpeg could not encode the preview: %s", e)
        dest.unlink(missing_ok=True)
    import soundfile as sf
    dest = folder / f"{PREVIEW_STEM}.mp3"
    try:
        sf.write(str(dest), y, sr, format="MP3")
        return dest
    except Exception as e:  # older libsndfile builds have no MP3 encoder
        log.info("soundfile MP3 encode unavailable (%s); writing WAV", e)
        dest.unlink(missing_ok=True)
    dest = folder / f"{PREVIEW_STEM}.wav"
    sf.write(str(dest), y, sr, subtype="PCM_16")
    return dest


def write_preview(info: AudioInfo, objects: List[HitObject], folder: Path,
                  song: Optional[np.ndarray] = None, sr: int = PREVIEW_SR) -> Path:
    """Decode the song (unless given) and write the click-track preview into folder."""
    if song is None:
        song, sr = audio_io.decode(dataclasses.replace(info), sr=sr)
    y = mix(song, sr, click_events(objects))
    return _encode(y, sr, Path(folder))
