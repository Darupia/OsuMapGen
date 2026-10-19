"""Map length: pick the best stretch of a song for a requested length and cut the audio to it.

The cut follows the music: it starts and ends on section boundaries (which sit on bar lines),
prefers stretches that contain the song's most intense part, and gets a short fade so the
audio does not stop abruptly. The source file is never modified; the cut is a new MP3.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

from .deps import find_ffmpeg
from .infra import UserFacingError, get_logger
from .model import SongAnalysis

log = get_logger("length")

FULL_SONG = "Full song"
LENGTH_CHOICES = [FULL_SONG, "1:00", "1:30 (TV size)", "2:00", "2:30", "3:00"]
MIN_LENGTH_S = 20.0
NO_CUT_MARGIN_S = 15.0         # a song at most this much longer than the request is mapped whole
PRE_ROLL_MS = 1000.0           # audio kept before the first mapped bar (lead-in for the player)
FADE_OUT_MS = 2000.0           # fade after the last mapped bar


def parse_length(text) -> Optional[float]:
    """'Full song' / '' -> None; '90', '1:30', '1:30 (TV size)', '2 min' -> seconds."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        secs = float(text)
    else:
        t = str(text).strip().lower()
        if not t or t.startswith("full"):
            return None
        m = re.match(r"^(\d+):([0-5]?\d)\b", t)
        if m:
            secs = int(m.group(1)) * 60 + int(m.group(2))
        else:
            m = re.match(r"^(\d+(?:[.,]\d+)?)\s*(m|min|mins|minutes?)?\b", t)
            if not m:
                raise UserFacingError(f"Map length '{text}' is not a time. Use minutes:seconds such as 1:30, "
                                      "or 'Full song'.")
            secs = float(m.group(1).replace(",", ".")) * (60 if m.group(2) else 1)
    if secs < MIN_LENGTH_S:
        raise UserFacingError(f"A map must be at least {MIN_LENGTH_S:.0f} seconds long.")
    return float(secs)


def fmt_time(ms: float) -> str:
    s = max(0, int(round(ms / 1000)))
    return f"{s // 60}:{s % 60:02d}"


def detail_level(map_seconds: float) -> int:
    """How many versions of each section are generated and compared (1 = no extra passes).
    Shorter maps get more: 1:00 -> 6, 1:30 -> 4, 2:00 -> 3, 3:00 -> 2, 4:00+ -> 1."""
    return int(np.clip(round(360.0 / max(map_seconds, 1.0)), 1, 6))


@dataclass
class CutPlan:
    start_ms: float          # first mapped bar (a section start)
    end_ms: float            # end of the last mapped section
    cut_start_ms: float      # audio actually kept (with pre-roll)
    cut_end_ms: float        # audio actually kept (with fade-out tail)
    reason: str

    @property
    def length_s(self) -> float:
        return (self.end_ms - self.start_ms) / 1000.0


def _boundaries(sa: SongAnalysis) -> List[float]:
    pts = {round(sa.music_start_ms), round(sa.music_end_ms)}
    for s in sa.sections:
        if sa.music_start_ms - 1 <= s.start_ms <= sa.music_end_ms:
            pts.add(round(max(s.start_ms, sa.music_start_ms)))
        if sa.music_start_ms <= s.end_ms <= sa.music_end_ms + 1:
            pts.add(round(min(s.end_ms, sa.music_end_ms)))
    return sorted(pts)


def _window_score(sa: SongAnalysis, a: float, b: float, target_ms: float) -> float:
    err = abs((b - a) - target_ms) / target_ms
    secs = [s for s in sa.sections if s.end_ms > a + 1 and s.start_ms < b - 1]
    if not secs:
        return -1e9
    weights = np.array([min(b, s.end_ms) - max(a, s.start_ms) for s in secs])
    inten = np.array([0.0 if s.is_break else s.intensity for s in secs])
    mean_i = float(np.average(inten, weights=weights)) if weights.sum() > 0 else 0.0
    peak = max((s.intensity for s in sa.sections if not s.is_break), default=1.0)
    has_peak = any(not s.is_break and s.intensity >= peak - 0.08 for s in secs)
    breaks = sum(w for s, w in zip(secs, weights) if s.is_break) / max(weights.sum(), 1.0)
    score = -2.5 * err + 0.6 * mean_i + (0.35 if has_peak else 0.0) - 1.0 * breaks
    if abs(a - sa.music_start_ms) < 1500:
        score += 0.15                       # starting where the song starts reads naturally
    first = secs[0]
    if not first.is_break and first.intensity < mean_i:
        score += 0.1                        # a calmer opening that builds up
    return score


def choose_window(sa: SongAnalysis, target_s: float) -> Optional[CutPlan]:
    """None when the song is already about that long (map it whole)."""
    target_ms = target_s * 1000.0
    music_ms = sa.music_end_ms - sa.music_start_ms
    if music_ms <= target_ms + NO_CUT_MARGIN_S * 1000:
        return None
    pts = _boundaries(sa)
    best = None
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            if b - a < 0.6 * target_ms:
                continue
            if b - a > 1.4 * target_ms:
                break
            sc = _window_score(sa, a, b, target_ms)
            if best is None or sc > best[0]:
                best = (sc, a, b, "section boundaries")
    if best is None:
        # too few sections: start at the music, end on the downbeat nearest the requested length
        a = sa.music_start_ms
        ts = sa.timing_at(a + target_ms)
        bar = ts.beat_ms * ts.meter
        k = round((a + target_ms - ts.offset_ms) / bar)
        b = min(sa.music_end_ms, ts.offset_ms + k * bar)
        best = (0.0, a, b, "bar lines (the song has few clear sections)")
    _, a, b, why = best
    cut_start = 0.0 if a - sa.music_start_ms < 1500 else max(0.0, a - PRE_ROLL_MS)
    cut_end = min(sa.audio.duration_ms, b + FADE_OUT_MS)
    return CutPlan(float(a), float(b), float(cut_start), float(cut_end), why)


def cut_audio(src: str, plan: CutPlan, dst: Path) -> Path:
    """Write the cut as a new MP3 (FFmpeg if available, else libsndfile). Never touches src."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    start_s = plan.cut_start_ms / 1000.0
    dur_s = (plan.cut_end_ms - plan.cut_start_ms) / 1000.0
    fade_out = min(FADE_OUT_MS / 1000.0, max(0.1, dur_s - (plan.end_ms - plan.cut_start_ms) / 1000.0))
    fade_in = 0.03 if start_s > 0 else 0.0
    ffmpeg = find_ffmpeg("ffmpeg")
    if ffmpeg:
        # timestamps restart at 0 for the cut (asetpts), so the fades are placed relative to the cut itself
        af = ["asetpts=PTS-STARTPTS", f"afade=t=out:st={dur_s - fade_out:.3f}:d={fade_out:.3f}"]
        if fade_in:
            af.insert(1, f"afade=t=in:st=0:d={fade_in}")
        cmd = [ffmpeg, "-nostdin", "-v", "error", "-y", "-ss", f"{start_s:.3f}", "-i", src, "-t", f"{dur_s:.3f}",
               "-vn", "-af", ",".join(af), "-codec:a", "libmp3lame", "-q:a", "2", str(dst)]   # keeps title/artist tags
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(cmd, capture_output=True, creationflags=flags, timeout=600)
        if proc.returncode == 0 and dst.is_file() and dst.stat().st_size > 1024:
            return dst
        log.warning("FFmpeg cut failed, using soundfile: %s", proc.stderr.decode("utf-8", "replace")[:300])
    import soundfile as sf
    data, sr = sf.read(src, dtype="float32", always_2d=True)
    a, b = int(start_s * sr), int((start_s + dur_s) * sr)
    seg = data[a:b].copy()
    n_out = int(fade_out * sr)
    if n_out:
        seg[-n_out:] *= np.linspace(1.0, 0.0, n_out)[:, None]
    n_in = int(fade_in * sr)
    if n_in:
        seg[:n_in] *= np.linspace(0.0, 1.0, n_in)[:, None]
    sf.write(str(dst), seg, sr, format="MP3")
    return dst
