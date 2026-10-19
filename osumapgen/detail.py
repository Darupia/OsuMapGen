"""Detail passes: generate several versions of each section and keep the cleanest one.

Used more for shorter maps (see length.detail_level). Sections are improved in song order;
each one keeps the version whose objects read best (fewest overlaps with notes still on
screen, least copy-paste, most pattern and angle variety, least hugging of the playfield
edge). Rhythm comes from the music and does not change between versions; only the random
choices of placement and slider shapes do.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Callable, Dict, List

from . import generator
from .model import GeneratedMap, HitObject, SongAnalysis
from .placement import circle_radius, preempt_ms

VARIANT_BASE = 100     # attempt numbers used for variants (repairs use 1, 2, 3)


def section_quality(objs: List[HitObject], start_ms: float, end_ms: float, cs: float, ar: float) -> float:
    """Higher is better. Only the objects that start inside [start_ms, end_ms) are scored."""
    idx = [i for i, o in enumerate(objs) if start_ms <= o.time_ms < end_ms and o.kind != "spinner"]
    if len(idx) < 3:
        return 0.0
    r = circle_radius(cs)
    window = preempt_ms(ar)
    overlaps = edge = 0
    for i in idx:
        o = objs[i]
        if min(o.x, 512 - o.x, o.y, 384 - o.y) < 24:
            edge += 1
        j = i - 2                          # the previous note is approached on purpose
        while j >= 0 and o.time_ms - max(objs[j].time_ms, objs[j].end_time_ms or 0) < window:
            p = objs[j]
            for px, py in ((p.x, p.y), (p.end_x, p.end_y)) if p.kind == "slider" else ((p.x, p.y),):
                d = math.hypot(o.x - px, o.y - py)
                if 3.0 < d < 1.2 * r:      # under 3 px is an intended stack, not an overlap
                    overlaps += 1
                    break
            j -= 1
    n = len(idx)
    sigs = [tuple((round((objs[b].x - objs[a].x) / 16), round((objs[b].y - objs[a].y) / 16), objs[b].kind)
                  for a, b in zip(idx[k:k + 5], idx[k + 1:k + 6])) for k in range(max(0, n - 5))]
    repeats = sum(c for c in Counter(sigs).values() if c > 1) / max(1, len(sigs))
    turns = set()
    for a, b, c in zip(idx, idx[1:], idx[2:]):
        o1, o2, o3 = objs[a], objs[b], objs[c]
        v1 = (o2.x - o1.end_x, o2.y - o1.end_y)
        v2 = (o3.x - o2.end_x, o3.y - o2.end_y)
        if math.hypot(*v1) > 5 and math.hypot(*v2) > 5:
            ang = math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1]))
            turns.add(int(ang // 30))
    patterns = {objs[i].pattern for i in idx}
    variety = min(1.0, len(turns) / 8.0) * 0.6 + min(1.0, len(patterns) / 4.0) * 0.4
    return variety - 3.0 * overlaps / n - 1.0 * repeats - 0.5 * edge / n


def refine_sections(sa: SongAnalysis, stars: float, style: str, knob: float, seed: int, versions: int,
                    on_step: Callable[[float], None] = lambda f: None) -> Dict[int, int]:
    """Per-section attempt numbers that give the best-reading map. versions = 1 does nothing."""
    attempts: Dict[int, int] = {}
    if versions <= 1:
        return attempts
    secs = [s for s in sa.sections if not s.is_break]
    current: GeneratedMap = generator.generate(sa, stars, style, knob, seed, attempts)
    d = current.difficulty
    for n, s in enumerate(secs):
        best_q = section_quality(current.objects, s.start_ms, s.end_ms, d.cs, d.ar)
        best_k, best_map = 0, current
        for v in range(1, versions):
            trial = dict(attempts)
            trial[s.index] = VARIANT_BASE + v
            m = generator.generate(sa, stars, style, knob, seed, trial)
            q = section_quality(m.objects, s.start_ms, s.end_ms, d.cs, d.ar)
            if q > best_q + 1e-6:
                best_q, best_k, best_map = q, VARIANT_BASE + v, m
        if best_k:
            attempts[s.index] = best_k
            current = best_map
        on_step((n + 1) / len(secs))
    return attempts
