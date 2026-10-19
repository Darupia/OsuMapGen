"""Placement: decide WHERE each planned object goes.

Movement is a cursor with a heading. Each combo picks a pattern (flowing
curve, wave, triangle, square, zigzag, back-and-forth, star) that defines
how the heading turns between objects; streams use gentle arcs or S-curves.
Distance comes from the time gap, the difficulty knob, the section's
intensity and how strongly the music accents the note. Every candidate
position is checked against the playfield and recently visible objects;
alternatives are tried in order of least deviation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import curves
from .model import DifficultySettings, HitObject, RhythmEvent, SongAnalysis
from .params import SectionParams

MARGIN = 14.0

PATTERNS = {
    # name: (base turn in degrees, alternate sign each move, sharp?)
    "flow": (40, False),
    "wave": (35, None),       # sign flips every two moves
    "triangle": (120, False),
    "square": (90, False),
    "zigzag": (130, True),
    "backforth": (172, True),
    "star": (144, False),
}

STYLE_PATTERNS = {
    "simple": {"flow": 4, "wave": 3, "triangle": 1},
    "balanced": {"flow": 3, "wave": 2, "triangle": 2, "square": 1, "zigzag": 1},
    "stream": {"flow": 3, "wave": 3, "triangle": 2, "square": 1},
    "jump": {"zigzag": 3, "triangle": 2, "backforth": 2, "star": 2, "square": 1},
    "tech": {"square": 2, "zigzag": 2, "star": 2, "wave": 1, "backforth": 1, "triangle": 1},
    "slider": {"flow": 4, "wave": 3, "triangle": 1},
}


def circle_radius(cs: float) -> float:
    return 54.4 - 4.48 * cs


def preempt_ms(ar: float) -> float:
    return 1200 + 600 * (5 - ar) / 5 if ar < 5 else 1200 - 750 * (ar - 5) / 5


@dataclass
class Cursor:
    x: float = 256.0
    y: float = 192.0
    heading: float = -math.pi / 2
    pattern: str = "flow"
    sign: float = 1.0
    move: int = 0
    stream_turn: float = 0.15
    recent_patterns: List[str] = field(default_factory=list)


def _inside(x, y) -> bool:
    return MARGIN <= x <= 512 - MARGIN and MARGIN <= y <= 384 - MARGIN


class Placer:
    def __init__(self, sa: SongAnalysis, P: SectionParams, diff: DifficultySettings, rng_for):
        self.sa = sa
        self.P = P
        self.p = P.base          # switched to each section's own preset as placement walks the song
        self.diff = diff
        self.rng_for = rng_for
        self.rng = rng_for(-1)
        self.rng_section = -1
        self.r = circle_radius(diff.cs)
        self.preempt = preempt_ms(diff.ar)
        self.objects: List[HitObject] = []
        self.cur = Cursor()

    # ---------------------------------------------------------------- patterns
    def _pick_pattern(self):
        weights: Dict[str, float] = dict(STYLE_PATTERNS.get(self.p.style, STYLE_PATTERNS["balanced"]))
        sharp = self.p.angle_sharpness
        for k in weights:
            if PATTERNS[k][0] >= 120:
                weights[k] *= 0.4 + 1.2 * sharp
            else:
                weights[k] *= 1.4 - 0.8 * sharp
        for k in self.cur.recent_patterns[-2:]:
            weights[k] = weights.get(k, 0) * 0.15          # avoid repeating the same shape
        names = list(weights)
        w = np.array([weights[n] for n in names], dtype=float)
        name = names[int(self.rng.choice(len(names), p=w / w.sum()))]
        self.cur.pattern = name
        self.cur.sign = 1.0 if self.rng.random() < 0.5 else -1.0
        self.cur.move = 0
        self.cur.stream_turn = math.radians(float(self.rng.uniform(7, 18))) * (1 if self.rng.random() < 0.5 else -1)
        self.cur.recent_patterns.append(name)

    def _turn(self, stream: bool) -> float:
        c = self.cur
        if stream:
            if c.move and c.move % 6 == 0 and self.rng.random() < 0.35:
                c.stream_turn = -c.stream_turn                 # S-curve
            return c.stream_turn
        base, alt = PATTERNS[c.pattern]
        jitter = float(self.rng.uniform(-12, 12))
        deg = base + jitter
        if alt is True:
            sign = c.sign * (1 if c.move % 2 == 0 else -1)
        elif alt is None:
            sign = c.sign * (1 if (c.move // 2) % 2 == 0 else -1)
        else:
            sign = c.sign
        return math.radians(deg) * sign

    # ---------------------------------------------------------------- spacing
    def _distance(self, ev: RhythmEvent, gap_ms: float, beat_ms: float, intensity: float, prev_stream: bool) -> float:
        p = self.p
        if ev.stream and prev_stream:
            return float(np.clip(p.stream_spacing * gap_ms, 10.0, 110.0))
        spacing = p.spacing * min(gap_ms, 350.0) + 0.25 * p.spacing * max(0.0, gap_ms - 350.0)
        spacing *= 0.5 + 0.6 * intensity          # calm parts move less than intense ones
        spacing *= 1.0 + (p.jump_boost - 1.0) * ev.emphasis
        ds = self.diff.slider_multiplier * 100.0 * min(gap_ms / beat_ms, 2.0)
        d = max(spacing, 0.85 * ds)
        if prev_stream and not ev.stream and gap_ms >= 0.45 * beat_ms:
            d *= 1.35                       # human maps hop 1.5-5 circle widths out of a stream
        # consecutive notes a 1/2 beat or more apart never overlap; 1/4 doubles may sit close
        floor = 2.1 * self.r if gap_ms >= beat_ms * 0.45 else 0.9 * self.r
        return float(np.clip(d, floor, max(floor, p.max_distance)))

    def _clearance(self, x, y, t, skip: int, stream: bool) -> float:
        """min(distance / required distance) to objects still on screen (>= 1 means clear)."""
        need = (0.9 if stream else 1.7) * self.r
        worst = 10.0
        # the previous object is skipped (we move away from it on purpose), but if it is a
        # slider its head and body are still on screen and must not be covered
        if self.objects and self.objects[-1].kind == "slider" and not stream:
            o = self.objects[-1]
            worst = min(worst, math.hypot(o.x - x, o.y - y) / need)
            for bx, by in o.body:
                if math.hypot(bx - o.end_x, by - o.end_y) > 2 * self.r:
                    worst = min(worst, math.hypot(bx - x, by - y) / (1.6 * self.r))
        for o in reversed(self.objects[:len(self.objects) - skip] if skip else self.objects):
            if o.time_ms < t - self.preempt and (o.end_time_ms or o.time_ms) < t - self.preempt:
                break
            worst = min(worst, math.hypot(o.x - x, o.y - y) / need)
            if o.kind == "slider":
                worst = min(worst, math.hypot(o.end_x - x, o.end_y - y) / need)
                for bx, by in o.body:
                    worst = min(worst, math.hypot(bx - x, by - y) / (1.6 * self.r))
        return worst

    def _clear(self, x, y, t, skip: int, stream: bool) -> bool:
        return self._clearance(x, y, t, skip, stream) >= 1.0

    def _body_clear(self, path: np.ndarray, t: float) -> bool:
        """A new slider's body must not run over other objects still on screen."""
        pts = path[::8]
        pts = pts[np.hypot(pts[:, 0] - path[0, 0], pts[:, 1] - path[0, 1]) > self.r]   # skip the head itself
        if len(pts) == 0:
            return True
        for o in reversed(self.objects):
            if (o.end_time_ms or o.time_ms) < t - self.preempt:
                break
            heads = [(o.x, o.y)] + ([(o.end_x, o.end_y)] if o.kind == "slider" else [])
            for hx, hy in heads:
                if np.any(np.hypot(pts[:, 0] - hx, pts[:, 1] - hy) < 1.6 * self.r):
                    return False
        return True

    def _choose(self, d: float, turn: float, t: float, stream: bool) -> Tuple[float, float, float]:
        c = self.cur
        skip = 2 if stream else 1
        options = [turn, -turn]
        options += [turn + math.radians(a) * s for a in range(20, 181, 20) for s in (1, -1)]
        best = None
        for scale in (1.0, 0.85, 1.15, 0.7, 1.3):
            for opt in options:
                h = c.heading + opt
                x, y = c.x + d * scale * math.cos(h), c.y + d * scale * math.sin(h)
                if not _inside(x, y):
                    continue
                score = self._clearance(x, y, t, skip, stream)
                if score >= 1.0:
                    return x, y, h
                if best is None or score > best[0]:
                    best = (score, x, y, h)
        if best is not None:
            return best[1], best[2], best[3]           # least crowded position that fits
        h = math.atan2(192 - c.y, 256 - c.x)
        x = float(np.clip(c.x + d * math.cos(h), MARGIN, 512 - MARGIN))
        y = float(np.clip(c.y + d * math.sin(h), MARGIN, 384 - MARGIN))
        return x, y, h

    # ---------------------------------------------------------------- sliders
    def _slider(self, obj: HitObject, beats: float, slides: int, intensity: float):
        sm = self.diff.slider_multiplier
        length = round(sm * 100.0 * beats, 2)
        hx, hy = obj.x, obj.y
        c = self.cur
        style = self.p.style
        shapes = ["L"] if length < 60 else (["P", "P", "B", "L"] if style in ("slider", "tech") else ["P", "L", "P", "B"])
        first = shapes[int(self.rng.integers(len(shapes)))]
        order = [first] + [s for s in ("P", "L", "B") if s != first]
        base_dir = c.heading + float(self.rng.uniform(-0.5, 0.5))
        # strict pass keeps the body clear of objects on screen; the relaxed pass only needs to fit
        attempts = [(shape, k, strict) for strict in (True, False) for shape in order for k in range(12)]
        for shape, k, strict in attempts:
            direction = base_dir + (math.pi / 6) * ((k + 1) // 2) * (1 if k % 2 else -1)
            if shape == "L":
                pts = [(hx, hy), (hx + length * math.cos(direction), hy + length * math.sin(direction))]
            elif shape == "P":
                sweep = math.radians(float(self.rng.uniform(35, 110))) * (1 if (k // 2) % 2 == 0 else -1) * c.sign
                pts = curves.make_arc((hx, hy), direction, length, sweep)
            else:
                pts = curves.make_s_curve((hx, hy), direction, length, float(self.rng.uniform(0.18, 0.32)))
            ipts = [(int(round(x)), int(round(y))) for x, y in pts]
            if len(set(ipts)) < len(ipts):
                continue
            path = curves.sample_path(shape, ipts, length)
            if not curves.in_bounds(path, MARGIN * 0.5):
                continue
            if strict and not self._body_clear(path, obj.time_ms):
                continue
            obj.body = [(float(x), float(y)) for x, y in path[::10]]
            obj.curve_type = shape
            obj.curve_points = ipts[1:]
            obj.length = length
            obj.slides = slides
            end = path[-1] if slides % 2 == 1 else path[0]
            obj.end_x, obj.end_y = int(round(end[0])), int(round(end[1]))
            tangent = curves.end_tangent(path)
            c.heading = tangent if slides % 2 == 1 else tangent + math.pi
            c.x, c.y = float(end[0]), float(end[1])
            return True
        return False

    # ---------------------------------------------------------------- streams
    def _plan_stream(self, x0, y0, heading, n, spacing, t) -> List[Tuple[float, float, float]]:
        """Positions for the n notes after (x0, y0): a constant-curvature arc or an S-curve
        that stays inside the playfield and away from objects still on screen."""
        steps = [spacing] * n
        if n >= 9 and self.rng.random() < self.p.stream_step:
            # the stream builds: spacing steps up every few notes, as in human spaced streams
            mult, width = 1.0, int(self.rng.choice([4, 5, 8]))
            for i in range(n):
                if i and i % width == 0:
                    mult = min(1.7, mult * float(self.rng.uniform(1.1, 1.22)))
                steps[i] = spacing * mult
        sign = 1.0 if self.rng.random() < 0.5 else -1.0
        s_curve = n >= 6 and self.rng.random() < 0.4
        # keep the total turn below ~260 degrees so long streams do not loop over themselves
        max_curv = min(0.32, math.radians(260) / max(n, 1))
        curvs = [c for c in (0.22, 0.15, 0.09, 0.04, 0.0) if c <= max_curv] or [max_curv]
        offsets = [0, 25, -25, 50, -50, 80, -80, 120, -120, 180]
        best, best_score = None, -1.0
        for curv in curvs:
            for off in offsets:
                for sg in (sign, -sign):
                    h = heading + math.radians(off)
                    x, y = x0, y0
                    pts = []
                    k = curv * sg
                    for i in range(n):
                        if s_curve and i == n // 2:
                            k = -k
                        h += k
                        x += steps[i] * math.cos(h)
                        y += steps[i] * math.sin(h)
                        pts.append((x, y, h))
                    if not all(_inside(px, py) for px, py, _ in pts):
                        continue
                    score = min(self._clearance(px, py, t, 1, True) for px, py, _ in pts[::3])
                    if score >= 1.0:
                        return pts
                    if score > best_score:
                        best, best_score = pts, score
        if best is not None:
            return best
        # last resort: a straight line toward the centre, folded back inside the playfield
        h = math.atan2(192 - y0, 256 - x0)
        pts, x, y = [], x0, y0
        for _ in range(n):
            nx, ny = x + spacing * math.cos(h), y + spacing * math.sin(h)
            if not _inside(nx, ny):
                h += math.pi * 0.75
                nx, ny = x + spacing * math.cos(h), y + spacing * math.sin(h)
            x, y = float(np.clip(nx, MARGIN, 512 - MARGIN)), float(np.clip(ny, MARGIN, 384 - MARGIN))
            pts.append((x, y, h))
        return pts

    def _stacks_here(self, ev: RhythmEvent, gap_ms: float, beat_ms: float, prev_stream: bool) -> bool:
        """Human maps double- and triple-tap on one spot (pairs at half-beat spacing, triples at 1/4). Only close
        notes, never inside a stream, and at most three in a row."""
        if ev.stream or prev_stream or not self.objects or self.stack_run >= 2:
            return False
        if gap_ms > 0.55 * beat_ms or self.p.stack_rate <= 0:
            return False
        rate = self.p.stack_rate * (1.0 if self.stack_run == 0 else 2.5)     # a stack tends to continue to a triple
        return bool(self.rng.random() < rate)

    # ---------------------------------------------------------------- main
    def place(self, events: List[RhythmEvent]) -> List[HitObject]:
        self.stream_plan: List[Tuple[float, float, float]] = []
        self.stack_run = 0
        sa = self.sa
        ticks = sa.ticks
        prev_end_t = None
        prev_stream = False
        for n, ev in enumerate(events):
            g = ticks[ev.tick_index]
            sec = sa.sections[g.section_index]
            beat_ms = sa.timing[g.timing_index].beat_ms
            t = g.time_ms
            if sec.index != self.rng_section:
                self.rng, self.rng_section = self.rng_for(sec.index), sec.index
                new_p = self.P.of(sec.index)
                if new_p.style != self.p.style:
                    ev.new_combo = True            # a style change starts a fresh pattern
                self.p = new_p
            if ev.kind == "spinner":
                end_t = ticks[ev.end_tick_index].time_ms
                self.objects.append(HitObject(time_ms=int(round(t)), kind="spinner", x=256, y=192, new_combo=True,
                                              end_time_ms=int(round(end_t)), section_index=sec.index,
                                              hitsound=ev.hitsound))
                self.cur.x, self.cur.y = 256.0, 192.0
                prev_end_t = end_t
                continue
            if ev.new_combo or n == 0:
                self._pick_pattern()
            if prev_end_t is None:
                x, y, h = 256.0 + float(self.rng.uniform(-60, 60)), 192.0 + float(self.rng.uniform(-40, 40)), self.cur.heading
            elif ev.stream and prev_stream and self.stream_plan:
                x, y, h = self.stream_plan.pop(0)
            elif self._stacks_here(ev, t - prev_end_t, beat_ms, prev_stream):
                x, y, h = self.cur.x, self.cur.y, self.cur.heading      # a stack: same spot as the previous object
                self.stack_run += 1
            else:
                self.stack_run = 0
                gap = t - prev_end_t
                d = self._distance(ev, gap, beat_ms, sec.intensity, prev_stream)
                if gap > 4 * beat_ms:
                    d = min(d, 160.0)            # gentle re-entry after a long gap
                turn = self._turn(ev.stream and prev_stream)
                x, y, h = self._choose(d, turn, t, ev.stream and prev_stream)
            self.cur.x, self.cur.y, self.cur.heading = x, y, h
            if ev.stream and not prev_stream:
                # plan the whole run now so it fits the playfield as one smooth curve
                run = 0
                step = None
                last_t = t
                while n + 1 + run < len(events):
                    e2 = events[n + 1 + run]
                    t2 = ticks[e2.tick_index].time_ms
                    if not e2.stream or e2.kind != "circle" or (step is not None and t2 - last_t > step * 1.3):
                        break
                    step = step or (t2 - last_t)
                    last_t = t2
                    run += 1
                self.stream_plan = []
                if run:
                    s = float(np.clip(self.p.stream_spacing * step, 10.0, 110.0))
                    self.stream_plan = self._plan_stream(x, y, h, run, s, t)
            self.cur.move += 1
            obj = HitObject(time_ms=int(round(t)), kind="circle", x=int(round(x)), y=int(round(y)),
                            new_combo=ev.new_combo, hitsound=ev.hitsound, section_index=sec.index,
                            pattern=self.cur.pattern if not ev.stream else "stream")
            obj.end_x, obj.end_y = obj.x, obj.y
            end_t = t
            if ev.kind == "slider":
                g_end = ticks[ev.end_tick_index]
                beats = (g_end.time_ms - t) / beat_ms
                if self._slider(obj, beats, ev.repeats, sec.intensity):
                    obj.kind = "slider"
                    end_t = t + beats * beat_ms * ev.repeats
                    obj.end_time_ms = int(round(end_t))
                # if no slider shape fits, the object stays a circle (still on the beat)
            self.objects.append(obj)
            prev_end_t = end_t
            prev_stream = ev.stream
        return self.objects
