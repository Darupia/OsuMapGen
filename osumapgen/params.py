"""Mapping parameters derived from target stars, style and the search knob.

`knob` in [0, 1] is the single control the star-rating search adjusts. It
scales rhythm density and spacing together so calm and intense sections keep
their relative character at every difficulty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from .model import DifficultySettings, SongAnalysis

#            stars: 1.0  2.0  3.0  4.0  5.0  6.0  7.0  8.0
_STARS = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
_AR = [3.5, 5.0, 6.5, 7.8, 8.8, 9.2, 9.5, 9.7]
_OD = [3.0, 4.0, 5.5, 7.0, 8.0, 8.5, 9.0, 9.2]
_CS = [3.0, 3.3, 3.8, 4.0, 4.0, 4.0, 4.2, 4.2]
_HP = [3.0, 3.5, 4.5, 5.0, 5.5, 6.0, 6.0, 6.0]
_SM = [1.0, 1.2, 1.4, 1.6, 1.7, 1.8, 1.9, 2.0]

STYLE_KEYS = {
    "Auto": "auto",
    "Simple and readable": "simple",
    "Stream-focused": "stream",
    "Jump-focused": "jump",
    "Technical": "tech",
    "Slider-focused": "slider",
    "Balanced mix (all styles)": "mix",
}


def difficulty_settings(stars: float) -> DifficultySettings:
    s = float(np.clip(stars, 0.5, 10.0))
    interp = lambda ys: round(float(np.interp(s, _STARS, ys)), 1)
    return DifficultySettings(hp=interp(_HP), cs=interp(_CS), od=interp(_OD), ar=interp(_AR),
                              slider_multiplier=round(float(np.interp(s, _STARS, _SM)), 2),
                              slider_tick_rate=1.0)


def resolve_style(style: str, sa: SongAnalysis, stars: float) -> str:
    key = STYLE_KEYS.get(style, style if style in STYLE_KEYS.values() else "auto")
    if key != "auto":
        return key
    bpm = max(sa.timing, key=lambda t: t.end_ms - t.start_ms).bpm
    # how much of the loud music has dense (1/4) onsets?
    dense = sum(1 for g in sa.ticks if g.sub % 2 == 1 and g.snap == 4 and g.onset > 0.35)
    total = max(1, sum(1 for g in sa.ticks if g.sub == 0))
    quarter_ratio = dense / total
    if stars < 2.5:
        return "simple"
    if quarter_ratio > 0.8 and bpm <= 190:
        return "stream"
    if bpm >= 185 or quarter_ratio < 0.2:
        return "jump"
    return "balanced"


@dataclass
class MapParams:
    stars: float
    knob: float
    style: str
    level_lo: float          # rhythm level for the calmest music
    level_hi: float          # rhythm level for the most intense music
    spacing: float           # px per ms for normal gaps
    jump_boost: float        # extra spacing multiplier on accented notes
    stream_spacing: float    # px per ms inside streams/bursts
    max_burst: int           # longest 1/4 run allowed at the top level
    slider_rate: float       # 0..1 preference for sliders on long gaps
    angle_sharpness: float   # 0 = flowing curves, 1 = sharp jumps
    max_distance: float      # hard cap for one jump (px)
    quarter_bias: float = 0.0     # >0 maps more 1/4 notes (streams), <0 fewer
    slider_min_gap: float = 0.99  # shortest gap (in beats) a slider may fill
    slider_force: float = 0.0     # minimum slider probability once a musical slider end exists
    slider_repeat: float = 0.18   # chance of a repeat slider on a long gap

    def level(self, intensity: float) -> float:
        return self.level_lo + (self.level_hi - self.level_lo) * intensity


KNOB_MAX = 1.35   # above 1.0 only spacing grows; rhythm density is already at its musical maximum


def make_params(stars: float, knob: float, style: str) -> MapParams:
    k = float(np.clip(knob, 0.0, KNOB_MAX))
    kd = min(k, 1.0)
    p = MapParams(
        stars=stars, knob=k, style=style,
        level_lo=0.1 + 1.3 * kd,
        level_hi=0.6 + 3.4 * kd,
        spacing=0.13 + 1.15 * k ** 1.2,
        jump_boost=1.0 + 0.45 * k,
        stream_spacing=0.12 + 0.30 * kd + 0.6 * max(0.0, k - 1.0),
        max_burst=int(round(3 + 29 * max(0.0, kd - 0.45) / 0.55)) if kd > 0.45 else 3,
        slider_rate=0.62 - 0.32 * kd,
        angle_sharpness=min(1.0, 0.15 + 0.6 * k),
        max_distance=min(440.0, 170 + 220 * k),
    )
    if style == "simple":
        p.level_hi = min(p.level_hi, 0.6 + 2.6 * k)
        p.jump_boost = 1.0 + 0.1 * k
        p.max_burst = min(p.max_burst, 3)
        p.angle_sharpness *= 0.4
        p.spacing *= 0.8
        p.slider_rate = min(0.9, p.slider_rate + 0.15)
        p.quarter_bias = -0.4
    elif style == "stream":
        p.level_hi += 0.6
        p.quarter_bias = 0.45
        p.spacing *= 0.7
        p.max_burst = max(p.max_burst, int(10 + 22 * k))
        p.stream_spacing *= 1.1
        p.slider_rate *= 0.4
        p.angle_sharpness *= 0.6
    elif style == "jump":
        p.level_hi = min(p.level_hi, 2.6)
        p.level_lo = min(p.level_lo, 2.0)
        p.quarter_bias = -1.0              # no streams: difficulty comes from distance
        p.spacing *= 1.7
        p.jump_boost += 0.5
        p.max_burst = 2
        p.angle_sharpness = min(1.0, p.angle_sharpness + 0.3)
        p.slider_rate *= 0.4
        p.max_distance = min(470.0, p.max_distance + 60)
    elif style == "tech":
        p.angle_sharpness = min(1.0, p.angle_sharpness + 0.25)
        p.slider_rate = min(0.9, p.slider_rate + 0.25)
        p.slider_min_gap = 0.74
        p.slider_repeat = 0.5
        p.quarter_bias = 0.1
        p.max_burst = min(p.max_burst, 6)
    elif style == "slider":
        p.slider_rate = 0.95
        p.slider_force = 0.8
        p.slider_min_gap = 0.49
        p.slider_repeat = 0.3
        p.level_hi -= 0.2
        p.max_burst = min(p.max_burst, 3)
        p.quarter_bias = -0.3
    return p


class SectionParams:
    """Mapping parameters per section. One style for the whole map, or (Balanced mix)
    a different preset per section, all sharing the same difficulty knob."""

    def __init__(self, base: MapParams, per_section: Optional[Dict[int, MapParams]] = None):
        self.base = base
        self.per_section = per_section or {}

    def of(self, section_index: int) -> MapParams:
        return self.per_section.get(section_index, self.base)

    @property
    def mixed(self) -> bool:
        return bool(self.per_section)

    def styles(self) -> Dict[int, str]:
        return {i: p.style for i, p in self.per_section.items()}


def section_features(sa: SongAnalysis, s) -> dict:
    ticks = [g for g in sa.ticks if g.section_index == s.index]
    beats = max(1, sum(1 for g in ticks if g.sub == 0))
    fast = sum(1 for g in ticks if g.sub % 2 == 1 and g.onset > 0.35) / beats       # 1/4 (or 1/3) notes per beat
    sustain = float(np.mean([g.sustain for g in ticks])) if ticks else 0.0
    accents = float(np.mean([g.onset * g.low for g in ticks if g.sub == 0])) if ticks else 0.0
    return {"fast": fast, "sustain": sustain, "accents": accents}


def mix_styles(sa: SongAnalysis, stars: float) -> Dict[int, str]:
    """Choose a preset for each section from what the music does there, then vary
    neighbours so the map moves between styles instead of repeating one."""
    choice: Dict[int, str] = {}
    used: Dict[str, float] = {}
    prev = None
    for s in sa.sections:
        if s.is_break:
            continue
        f = section_features(sa, s)
        I = s.intensity
        # presets that suit this section, best fit first
        if I < 0.4 or s.label in ("intro", "outro", "breakdown"):
            fits = ["slider", "simple"] if f["sustain"] > 0.35 else ["simple", "slider"]
        elif I >= 0.75 and f["fast"] > 0.6:
            fits = ["stream", "jump", "tech"]
        elif I >= 0.75:
            fits = ["jump", "tech", "balanced"]
        elif f["fast"] > 0.4:
            fits = ["tech", "stream", "balanced", "jump"]
        else:
            fits = ["balanced", "tech", "slider", "jump"]
        if stars < 3.0:   # streams and technical patterns don't belong in easy maps
            fits = [x for x in fits if x not in ("stream", "tech")] or ["balanced"]
        minutes = (s.end_ms - s.start_ms) / 60000.0

        def cost(k_st):
            k, st = k_st
            return k * 0.6 + used.get(st, 0.0) * 4.0 + (5.0 if st == prev and len(fits) > 1 else 0.0)

        pick = min(enumerate(fits), key=cost)[1]
        choice[s.index] = pick
        used[pick] = used.get(pick, 0.0) + minutes      # least-used presets get the next turn
        prev = pick
    return choice


def make_section_params(stars: float, knob: float, style: str, sa: SongAnalysis) -> SectionParams:
    if style != "mix":
        return SectionParams(make_params(stars, knob, style))
    styles = mix_styles(sa, stars)
    return SectionParams(make_params(stars, knob, "balanced"),
                         {i: make_params(stars, knob, st) for i, st in styles.items()})


def initial_knob(stars: float) -> float:
    return float(np.clip((stars - 1.0) / 6.5, 0.0, 1.0))
