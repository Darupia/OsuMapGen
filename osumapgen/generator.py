"""Builds a complete GeneratedMap for one knob value (rhythm + placement + extras)."""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from . import rhythm
from .model import GeneratedMap, HitObject, SongAnalysis
from .params import difficulty_settings, make_section_params
from .placement import Placer, preempt_ms


def _rng_factory(seed: int, attempts: Dict[int, int]):
    def rng_for(section_index: int):
        return np.random.default_rng([seed & 0xFFFFFFFF, section_index + 1, attempts.get(section_index, 0)])
    return rng_for


def sanitize(objs: List[HitObject], duration_ms: float, min_gap_ms: float = 20.0) -> List[HitObject]:
    """Structural guarantees: increasing times, nothing starting before the
    previous object ends, nothing ending after the audio."""
    out: List[HitObject] = []
    limit = duration_ms - 50
    for o in sorted(objs, key=lambda o: o.time_ms):
        if o.time_ms < 0 or o.time_ms > limit:
            continue
        if out:
            prev = out[-1]
            prev_end = prev.end_time_ms if prev.kind in ("slider", "spinner") else prev.time_ms
            if o.time_ms < prev_end + min_gap_ms:
                continue
        if o.kind in ("slider", "spinner") and o.end_time_ms > limit:
            if o.kind == "spinner":
                o.end_time_ms = int(limit)
                if o.end_time_ms - o.time_ms < 500:
                    continue
            else:
                o.kind, o.curve_type, o.curve_points, o.end_time_ms = "circle", "", [], 0
                o.end_x, o.end_y = o.x, o.y
        o.x = int(np.clip(o.x, 0, 512))
        o.y = int(np.clip(o.y, 0, 384))
        out.append(o)
    if out:
        out[0].new_combo = True
    return out


def compute_breaks(objs: List[HitObject], preempt: float) -> List[tuple]:
    breaks = []
    for a, b in zip(objs[:-1], objs[1:]):
        a_end = a.end_time_ms if a.kind in ("slider", "spinner") else a.time_ms
        if b.time_ms - a_end >= 5000:
            start = a_end + 200
            end = int(b.time_ms - max(preempt, 900))
            if end - start >= 1500:
                breaks.append((int(start), int(end)))
                b.new_combo = True
    return breaks


def green_lines(sa: SongAnalysis) -> List[tuple]:
    """(time, sv multiplier, volume, kiai) at section changes only when something changes."""
    lines = []
    prev = None
    for s in sa.sections:
        vol = 45 if s.intensity < 0.4 else 60 if s.intensity < 0.82 else 70
        state = (vol, s.kiai)
        if state != prev:
            # place on the beat grid
            ts = sa.timing_at(s.start_ms)
            k = round((s.start_ms - ts.offset_ms) / ts.beat_ms)
            t = int(round(ts.offset_ms + k * ts.beat_ms))
            lines.append((max(t, int(round(sa.timing[0].offset_ms))), 1.0, vol, s.kiai))
            prev = state
    # collapse duplicates at the same time (keep the last)
    out = {}
    for t, sv, v, k in lines:
        out[t] = (t, sv, v, k)
    return sorted(out.values())


def preview_time(sa: SongAnalysis) -> int:
    chorus = [s for s in sa.sections if s.label == "chorus"]
    t = chorus[0].start_ms if chorus else sa.music_start_ms + 0.4 * (sa.music_end_ms - sa.music_start_ms)
    ts = sa.timing_at(t)
    k = round((t - ts.offset_ms) / ts.beat_ms)
    return int(max(0, round(ts.offset_ms + k * ts.beat_ms)))


def generate(sa: SongAnalysis, stars: float, style: str, knob: float, seed: int,
             attempts: Optional[Dict[int, int]] = None) -> GeneratedMap:
    attempts = attempts or {}
    diff = difficulty_settings(stars)
    P = make_section_params(stars, knob, style, sa)
    rng_for = _rng_factory(seed, attempts)
    events = rhythm.plan_rhythm(sa, P, diff.slider_multiplier, rng_for)
    objs = Placer(sa, P, diff, rng_for).place(events)
    objs = sanitize(objs, sa.audio.duration_ms)
    breaks = compute_breaks(objs, preempt_ms(diff.ar))
    divisor = 12 if any(s.snap == 3 for s in sa.sections) and any(s.snap == 4 for s in sa.sections) else \
        (3 if all(s.snap == 3 for s in sa.sections) else 4)
    stats = {
        "objects": len(objs),
        "circles": sum(o.kind == "circle" for o in objs),
        "sliders": sum(o.kind == "slider" for o in objs),
        "spinners": sum(o.kind == "spinner" for o in objs),
        "stream_notes": sum(e.stream for e in events),
    }
    if P.mixed:
        stats["section_styles"] = P.styles()
    return GeneratedMap(difficulty=diff, objects=objs, knob=knob, style=style, breaks=breaks,
                        green_lines=green_lines(sa), preview_ms=preview_time(sa), beat_divisor=divisor,
                        stats=stats)
