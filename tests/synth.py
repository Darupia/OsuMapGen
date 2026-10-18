"""Procedural, copyright-free test songs with known ground truth.

Every fixture is synthesised from oscillators and filtered noise, so there is
no third-party audio involved. render() returns the signal plus the exact
beat/section times used to build it.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

SR = 44100
SCALE = [0, 2, 4, 7, 9, 12, 14, 16]          # major pentatonic (semitones)
PROGRESSION = [0, -3, 5, 7]                   # I vi IV V roots (semitones from A2)


@dataclass
class Segment:
    bars: int
    bpm: float
    kind: str              # silence | pad | intro | verse | chorus | triplet | sparse
    gain: float = 1.0


@dataclass
class Rendered:
    audio: np.ndarray
    sr: int
    beats_ms: List[float] = field(default_factory=list)
    segments_ms: List[tuple] = field(default_factory=list)   # (start, end, kind, bpm)
    lead_silence_ms: float = 0.0
    tail_silence_ms: float = 0.0


def _env(n, attack, decay, sr=SR):
    t = np.arange(n) / sr
    a = np.minimum(1.0, t / max(attack, 1e-4))
    return a * np.exp(-t / max(decay, 1e-4))


def _add(buf, start, x):
    i = int(round(start * SR))
    if i >= len(buf):
        return
    # fade out the tail so truncated samples do not produce click artefacts
    n = min(len(x), int(0.015 * SR))
    x = x.copy()
    x[-n:] *= 0.5 * (1 + np.cos(np.linspace(0, np.pi, n)))
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i]


class Kit:
    def __init__(self, seed=1):
        rng = np.random.default_rng(seed)
        n = int(0.35 * SR)
        t = np.arange(n) / SR
        freq = 50 + 90 * np.exp(-t * 30)
        self.kick = np.sin(2 * np.pi * np.cumsum(freq) / SR) * _env(n, 0.001, 0.12) * 0.9
        n = int(0.2 * SR)
        noise = rng.standard_normal(n)
        noise = np.convolve(noise, np.ones(3) / 3, mode="same") - np.convolve(noise, np.ones(30) / 30, mode="same")
        self.snare = (0.5 * noise + 0.4 * np.sin(2 * np.pi * 185 * np.arange(n) / SR)) * _env(n, 0.001, 0.06) * 0.7
        n = int(0.06 * SR)
        hn = np.diff(rng.standard_normal(n + 1))
        self.hat = hn * _env(n, 0.0005, 0.015) * 0.18


def _tone(freq, dur, harmonics=(1.0,), attack=0.01, decay=0.4):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = sum(a * np.sin(2 * np.pi * freq * (h + 1) * t) for h, a in enumerate(harmonics))
    return x * _env(n, attack, decay)


def render(segments: List[Segment], lead_silence: float = 0.0, tail_silence: float = 0.0,
           seed: int = 7) -> Rendered:
    rng = np.random.default_rng(seed)
    kit = Kit(seed)
    total = lead_silence + tail_silence + sum(s.bars * 4 * 60 / s.bpm for s in segments) + 1.0
    buf = np.zeros(int(total * SR) + SR)
    out = Rendered(audio=buf, sr=SR, lead_silence_ms=lead_silence * 1000, tail_silence_ms=tail_silence * 1000)
    t0 = lead_silence
    bar_counter = 0
    motif = [rng.choice(SCALE) for _ in range(16)]
    for seg in segments:
        beat = 60.0 / seg.bpm
        seg_start = t0
        g = seg.gain
        for bar in range(seg.bars):
            root = 110.0 * 2 ** (PROGRESSION[bar_counter % 4] / 12)
            bar_t = t0 + bar * 4 * beat
            for b in range(4):
                bt = bar_t + b * beat
                if seg.kind not in ("silence", "pad"):
                    out.beats_ms.append(bt * 1000)
                k = seg.kind
                if k in ("verse", "chorus", "triplet") or (k == "intro" and b == 0) or (k == "sparse" and b in (0, 3)):
                    if k == "chorus" or b in (0, 2) or k == "intro" or k == "sparse":
                        _add(buf, bt, kit.kick * g)
                if k in ("verse", "chorus", "triplet") and b in (1, 3):
                    _add(buf, bt, kit.snare * g)
                if k == "sparse" and b == 2:
                    _add(buf, bt + beat * 0.5, kit.snare * g)       # syncopated, ambiguous
                if k in ("intro", "verse"):
                    for s in (0, 0.5):
                        _add(buf, bt + s * beat, kit.hat * g * (1.0 if s == 0 else 0.6))
                if k == "chorus":
                    for s in (0, 0.25, 0.5, 0.75):
                        _add(buf, bt + s * beat, kit.hat * g * (1.0 if s in (0, 0.5) else 0.55))
                if k == "triplet":
                    for s in (0, 1 / 3, 2 / 3):
                        _add(buf, bt + s * beat, kit.hat * g * 1.2)
                # bass on 8ths
                if k in ("verse", "chorus", "triplet"):
                    for s in (0, 0.5):
                        _add(buf, bt + s * beat, _tone(root / 2, beat * 0.45, (1, .5, .33, .25), 0.005, 0.15) * 0.25 * g)
                # lead melody
                if k in ("verse", "chorus"):
                    steps = (0, 0.5) if k == "verse" else (0, 0.25, 0.5, 0.75)
                    for s in steps:
                        idx = (bar * 4 + b) * len(steps) + int(s * len(steps))
                        if k == "verse" and idx % 3 == 2:
                            continue
                        note = motif[idx % 16]
                        f = 440.0 * 2 ** ((note + PROGRESSION[bar_counter % 4]) / 12)
                        _add(buf, bt + s * beat, _tone(f, beat * 0.5, (1, .3), 0.004, 0.12) * 0.12 * g)
            # pads (sustained chords)
            if seg.kind in ("pad", "intro", "verse", "chorus"):
                chord = sum(_tone(root * 2 * 2 ** (iv / 12), 4 * beat, (1,), 0.3, 3.0) for iv in (0, 4, 7))
                _add(buf, bar_t, chord * (0.05 if seg.kind != "pad" else 0.08) * g)
            bar_counter += 1
        t0 += seg.bars * 4 * beat
        out.segments_ms.append((seg_start * 1000, t0 * 1000, seg.kind, seg.bpm))
    end = int((t0 + tail_silence) * SR)
    buf = buf[:end]
    peak = np.max(np.abs(buf)) or 1.0
    out.audio = (buf / peak * 0.89).astype(np.float32)
    return out


def write_mp3(audio: np.ndarray, path: Path, sr: int = SR) -> Path:
    """Encode with FFmpeg (libmp3lame) if available, else libsndfile's MP3 writer."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    from osumapgen.deps import find_ffmpeg
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        cmd = [ffmpeg, "-y", "-v", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", "-",
               "-codec:a", "libmp3lame", "-b:a", "192k", str(path)]
        subprocess.run(cmd, input=pcm, check=True, capture_output=True)
    else:
        import soundfile as sf
        sf.write(str(path), audio, sr, format="MP3")
    return path


# ---- named fixtures -------------------------------------------------------

def fixture(name: str) -> Rendered:
    if name == "short":
        return render([Segment(2, 128, "intro"), Segment(6, 128, "verse"), Segment(4, 128, "chorus")],
                      lead_silence=0.5, tail_silence=0.5)
    if name == "full":
        bpm = 140
        return render([Segment(8, bpm, "intro", 0.5), Segment(16, bpm, "verse", 0.8),
                       Segment(16, bpm, "chorus"), Segment(8, bpm, "pad", 0.6),
                       Segment(16, bpm, "verse", 0.8), Segment(24, bpm, "chorus"),
                       Segment(8, bpm, "intro", 0.5)],
                      lead_silence=1.2, tail_silence=1.0)
    if name == "long":       # ~6 minutes, 174 BPM
        bpm = 174
        segs = [Segment(8, bpm, "intro", 0.5)]
        for _ in range(4):
            segs += [Segment(16, bpm, "verse", 0.8), Segment(24, bpm, "chorus"), Segment(8, bpm, "pad", 0.6)]
        segs += [Segment(48, bpm, "chorus"), Segment(8, bpm, "intro", 0.5)]
        return render(segs, lead_silence=0.8, tail_silence=2.0)
    if name == "ambiguous":
        return render([Segment(24, 96, "sparse")], lead_silence=0.3, tail_silence=0.3)
    if name == "tempo_change":
        return render([Segment(16, 120, "verse"), Segment(16, 150, "chorus")], lead_silence=0.4, tail_silence=0.4)
    if name == "long_break":
        return render([Segment(12, 130, "verse"), Segment(6, 130, "silence"), Segment(12, 130, "chorus")],
                      lead_silence=0.4, tail_silence=0.4)
    if name == "trailing_silence":
        return render([Segment(12, 150, "verse"), Segment(8, 150, "chorus")], lead_silence=0.2, tail_silence=12.0)
    if name == "quiet_intro":
        return render([Segment(8, 125, "intro", 0.25), Segment(16, 125, "chorus", 1.0)],
                      lead_silence=0.5, tail_silence=0.5)
    if name == "triplet":
        return render([Segment(16, 110, "triplet")], lead_silence=0.3, tail_silence=0.3)
    raise KeyError(name)


def clicks(times_s, total_s, sr=SR) -> np.ndarray:
    buf = np.zeros(int(total_s * sr))
    n = int(0.02 * sr)
    click = np.random.default_rng(0).standard_normal(n) * _env(n, 0.0002, 0.004)
    for t in times_s:
        _add(buf, t, click)
    return (buf / np.max(np.abs(buf)) * 0.9).astype(np.float32)


def ensure_fixture(name: str, folder: Path) -> tuple:
    """Write fixture MP3 (cached) and return (path, Rendered)."""
    r = fixture(name)
    p = Path(folder) / f"{name}.mp3"
    if not p.exists():
        write_mp3(r.audio, p)
    return p, r


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures")
    for n in ("short", "full", "ambiguous", "tempo_change", "long_break", "trailing_silence",
              "quiet_intro", "triplet"):
        p, r = ensure_fixture(n, out)
        print(p, f"{len(r.audio) / r.sr:.1f}s")
