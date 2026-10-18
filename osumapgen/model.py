"""Structured intermediate representation of a whole song and its map.

All times are float milliseconds from the start of the audio file unless a
name says otherwise. Hit objects are serialized with integer milliseconds.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple


# --------------------------------------------------------------------------
# Audio / analysis
# --------------------------------------------------------------------------

@dataclass
class AudioInfo:
    path: str
    duration_ms: float
    sample_rate: int          # native sample rate of the file
    channels: int
    bitrate_kbps: Optional[int]
    decoder: str              # "ffmpeg" or "soundfile"
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None


@dataclass
class Onset:
    time_ms: float
    strength: float           # 0..1, normalised to local loudness
    low: float                # low-band (kick) share 0..1
    high: float               # high-band (snare/hat) share 0..1


@dataclass
class TimingSection:
    """One red (uninherited) timing point and the region it governs."""
    offset_ms: float          # time of a downbeat
    beat_ms: float            # milliseconds per beat
    start_ms: float           # region start (== offset for all but the first)
    end_ms: float             # region end (exclusive)
    confidence: float         # 0..1 phase-coherence of onsets with this grid
    meter: int = 4
    downbeat_phase: int = 0   # beat k (counted from offset) is a downbeat when (k - phase) % meter == 0

    @property
    def bpm(self) -> float:
        return 60000.0 / self.beat_ms


@dataclass
class Section:
    """A musical section (intro / verse / chorus / break ...)."""
    index: int
    start_ms: float
    end_ms: float
    label: str                # intro, verse, build, chorus, break, outro
    intensity: float          # 0..1 relative to the song
    energy_db: float          # mean RMS in dB relative to song peak
    onset_density: float      # onsets per beat
    is_break: bool = False
    snap: int = 4             # 4 = straight (1/4) grid, 3 = triplet (1/3) grid
    kiai: bool = False


@dataclass
class GridTick:
    time_ms: float
    beat_index: int           # beat number inside its timing section
    sub: int                  # position inside the beat (0..snap-1)
    snap: int                 # 4 or 3
    timing_index: int
    section_index: int
    metric: float             # metrical weight 0..1
    onset: float              # onset strength at tick 0..1
    low: float
    high: float
    sustain: float            # held-energy measure 0..1 after this tick

    @property
    def is_beat(self) -> bool:
        return self.sub == 0

    @property
    def is_downbeat(self) -> bool:
        return self.sub == 0 and self.beat_index % 4 == 0


@dataclass
class SongAnalysis:
    audio: AudioInfo
    music_start_ms: float
    music_end_ms: float
    timing: List[TimingSection]
    tempo_confidence: float
    tempo_candidates: List[Tuple[float, float]]   # (bpm, score)
    onsets: List[Onset]
    sections: List[Section]
    ticks: List[GridTick]
    analysed_ms: float                            # decoded audio length
    warnings: List[str] = field(default_factory=list)
    content_hash: str = ""

    def timing_at(self, t: float) -> TimingSection:
        cur = self.timing[0]
        for ts in self.timing:
            if ts.start_ms <= t + 1e-6:
                cur = ts
        return cur

    def section_at(self, t: float) -> Section:
        cur = self.sections[0]
        for s in self.sections:
            if s.start_ms <= t + 1e-6:
                cur = s
        return cur

    def summary(self) -> dict:
        return {
            "duration_ms": round(self.audio.duration_ms),
            "analysed_ms": round(self.analysed_ms),
            "music_start_ms": round(self.music_start_ms),
            "music_end_ms": round(self.music_end_ms),
            "tempo_confidence": round(self.tempo_confidence, 3),
            "tempo_candidates": [(round(b, 2), round(s, 3)) for b, s in self.tempo_candidates],
            "timing": [
                {"offset_ms": round(t.offset_ms, 2), "bpm": round(t.bpm, 3),
                 "start_ms": round(t.start_ms), "end_ms": round(t.end_ms),
                 "confidence": round(t.confidence, 3)} for t in self.timing],
            "sections": [
                {"start_ms": round(s.start_ms), "end_ms": round(s.end_ms), "label": s.label,
                 "intensity": round(s.intensity, 2), "energy_db": round(s.energy_db, 1),
                 "snap": s.snap, "kiai": s.kiai} for s in self.sections],
            "onset_count": len(self.onsets),
            "tick_count": len(self.ticks),
        }


# --------------------------------------------------------------------------
# Map
# --------------------------------------------------------------------------

@dataclass
class DifficultySettings:
    hp: float
    cs: float
    od: float
    ar: float
    slider_multiplier: float
    slider_tick_rate: float = 1.0


@dataclass
class RhythmEvent:
    """A planned object in time only (before placement)."""
    time_ms: float
    tick_index: int
    kind: str                       # "circle", "slider", "spinner"
    end_tick_index: int = -1        # sliders / spinners
    repeats: int = 1                # slider slides (1 = no repeat)
    stream: bool = False            # part of a 1/4 (or 1/3) run
    new_combo: bool = False
    hitsound: int = 0
    emphasis: float = 0.0           # 0..1, how strongly the music accents it


@dataclass
class HitObject:
    time_ms: int
    kind: str                       # "circle", "slider", "spinner"
    x: int
    y: int
    new_combo: bool = False
    hitsound: int = 0
    # slider data
    curve_type: str = ""            # L, P, B
    curve_points: List[Tuple[int, int]] = field(default_factory=list)
    slides: int = 1
    length: float = 0.0             # pixel length
    end_time_ms: int = 0            # computed end (sliders / spinners)
    end_x: int = 0
    end_y: int = 0
    section_index: int = 0
    pattern: str = ""               # placement pattern id (diagnostics)
    body: List[Tuple[float, float]] = field(default_factory=list, repr=False)  # sampled slider path


@dataclass
class GeneratedMap:
    difficulty: DifficultySettings
    objects: List[HitObject]
    knob: float
    style: str
    breaks: List[Tuple[int, int]]
    green_lines: List[Tuple[int, float, int, bool]]  # (time, sv-mult, volume, kiai)
    preview_ms: int
    beat_divisor: int
    stats: dict = field(default_factory=dict)


def to_dict(obj) -> dict:
    return asdict(obj)
