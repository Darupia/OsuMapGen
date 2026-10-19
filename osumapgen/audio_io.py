"""Audio probing and decoding (full file, mono float32)."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Tuple

import numpy as np

from .deps import find_ffmpeg
from .infra import UserFacingError, get_logger
from .model import AudioInfo

ANALYSIS_SR = 22050
SUPPORTED_EXT = {".mp3", ".ogg"}

log = get_logger("audio")


class InvalidAudioError(UserFacingError):
    pass


def file_hash(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean_tag(v) -> str | None:
    if v is None:
        return None
    s = str(v[0] if isinstance(v, (list, tuple)) and v else v).strip().strip("\x00")
    return s or None


def probe(path: str) -> AudioInfo:
    p = Path(path)
    if not p.is_file():
        raise InvalidAudioError(f"File not found: {path}")
    if p.suffix.lower() not in SUPPORTED_EXT:
        raise InvalidAudioError(f"Unsupported file type '{p.suffix}'. Please choose an MP3 file.")
    if p.stat().st_size < 1024:
        raise InvalidAudioError("The selected file is too small to be a valid audio file.")
    try:
        import mutagen
        mf = mutagen.File(str(p), easy=True)
    except Exception as e:  # mutagen raises many specific header errors
        raise InvalidAudioError(f"The file could not be read as audio ({type(e).__name__}: {e}).") from e
    if mf is None or getattr(mf, "info", None) is None or not getattr(mf.info, "length", 0):
        raise InvalidAudioError("The file does not contain a readable MP3/OGG audio stream.")
    info = mf.info
    tags = mf.tags or {}
    br = getattr(info, "bitrate", None)
    return AudioInfo(
        path=str(p),
        duration_ms=float(info.length) * 1000.0,
        sample_rate=int(getattr(info, "sample_rate", 0) or 0),
        channels=int(getattr(info, "channels", 0) or 0),
        bitrate_kbps=int(br / 1000) if br else None,
        decoder="",
        title=_clean_tag(tags.get("title")),
        artist=_clean_tag(tags.get("artist")),
        album=_clean_tag(tags.get("album")),
    )


def _image_ext(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    return None


def cover_art(path: str) -> Tuple[bytes, str] | None:
    """Embedded cover image (ID3 APIC) as (bytes, ".jpg"/".png"), preferring the front cover."""
    try:
        import mutagen
        mf = mutagen.File(str(path))
        frames = list(mf.tags.getall("APIC")) if mf is not None and hasattr(mf.tags, "getall") else []
    except Exception as e:
        log.info("No cover art read from %s: %s", path, e)
        return None
    frames.sort(key=lambda f: getattr(f, "type", 0) != 3)      # 3 = front cover
    for f in frames:
        data = bytes(getattr(f, "data", b"") or b"")
        ext = _image_ext(data)
        if ext and len(data) >= 64:
            return data, ext
    return None


def _decode_ffmpeg(ffmpeg: str, path: str, sr: int) -> np.ndarray:
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr),
           "-f", "f32le", "-"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(cmd, capture_output=True, creationflags=flags, timeout=600)
    if proc.returncode != 0:
        raise InvalidAudioError("FFmpeg could not decode the file: "
                                + proc.stderr.decode("utf-8", "replace").strip()[:400])
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def _decode_soundfile(path: str, sr: int) -> np.ndarray:
    import soundfile as sf
    try:
        data, native_sr = sf.read(path, dtype="float32", always_2d=True)
    except Exception as e:
        raise InvalidAudioError(f"The audio could not be decoded ({e}).") from e
    mono = data.mean(axis=1)
    if native_sr != sr:
        import soxr
        mono = soxr.resample(mono, native_sr, sr, quality="HQ").astype(np.float32)
    return mono


def decode(info: AudioInfo, sr: int = ANALYSIS_SR, prefer_ffmpeg: bool = True) -> Tuple[np.ndarray, int]:
    """Decode the complete file. Raises if the decode is truncated or silent."""
    ffmpeg = find_ffmpeg("ffmpeg") if prefer_ffmpeg else None
    y = None
    if ffmpeg:
        try:
            y = _decode_ffmpeg(ffmpeg, info.path, sr)
            info.decoder = "ffmpeg"
        except (InvalidAudioError, OSError, subprocess.TimeoutExpired) as e:
            log.warning("ffmpeg decode failed, falling back to soundfile: %s", e)
            y = None
    if y is None:
        y = _decode_soundfile(info.path, sr)
        info.decoder = "soundfile"
    if y.size == 0:
        raise InvalidAudioError("The file decoded to zero samples.")
    if not np.all(np.isfinite(y)):
        y = np.nan_to_num(y)
    decoded_ms = y.size / sr * 1000.0
    expected = info.duration_ms
    if expected > 0 and decoded_ms < expected - max(1500.0, 0.02 * expected):
        raise InvalidAudioError(
            f"Only {decoded_ms / 1000:.1f}s of {expected / 1000:.1f}s could be decoded; the file may be damaged.")
    if abs(decoded_ms - expected) > 1000:
        log.info("Header duration %.0f ms differs from decoded %.0f ms; using decoded length",
                 expected, decoded_ms)
        info.duration_ms = decoded_ms
    peak = float(np.max(np.abs(y)))
    if peak < 1e-4:
        raise InvalidAudioError("The audio is silent.")
    log.info("Decoded %s with %s: %.1fs @ %d Hz (peak %.3f)", info.path, info.decoder,
             decoded_ms / 1000, sr, peak)
    return y, sr
