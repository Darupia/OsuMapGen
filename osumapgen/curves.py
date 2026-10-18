"""Slider path geometry compatible with osu!'s L / P / B curve types.

Paths are sampled densely and truncated to the slider's pixel length, which
is how the game interprets them.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np

Point = Tuple[float, float]

PLAYFIELD_W, PLAYFIELD_H = 512, 384


def _bezier(points: np.ndarray, n: int = 64) -> np.ndarray:
    t = np.linspace(0, 1, n)[:, None]
    pts = points.copy()
    k = len(pts)
    # de Casteljau, vectorised over t
    work = np.repeat(pts[None, :, :], n, axis=0)
    for r in range(1, k):
        work = (1 - t[:, :, None]) * work[:, :-1, :] + t[:, :, None] * work[:, 1:, :]
    return work[:, 0, :]


def circle_through(p0, p1, p2):
    (ax, ay), (bx, by), (cx, cy) = p0, p1, p2
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-6:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy


def sample_path(curve_type: str, points: List[Point], length: float, step: float = 2.0) -> np.ndarray:
    """Points along the path from the head, truncated (or linearly extended) to `length`."""
    pts = np.array(points, dtype=float)
    if curve_type == "P" and len(pts) == 3:
        c = circle_through(*pts)
        if c is not None:
            cx, cy = c
            r = math.hypot(pts[0][0] - cx, pts[0][1] - cy)
            a0 = math.atan2(pts[0][1] - cy, pts[0][0] - cx)
            a1 = math.atan2(pts[1][1] - cy, pts[1][0] - cx)
            a2 = math.atan2(pts[2][1] - cy, pts[2][0] - cx)
            # direction: does going from a0 to a2 counter-clockwise pass a1?
            ccw = ((a1 - a0) % (2 * math.pi)) < ((a2 - a0) % (2 * math.pi))
            sign = 1.0 if ccw else -1.0
            n = max(2, int(length / step) + 1)
            ang = a0 + sign * np.linspace(0, length / r, n)
            return np.stack([cx + r * np.cos(ang), cy + r * np.sin(ang)], axis=1)
        curve_type = "L"
    if curve_type == "L":
        poly = pts
    else:  # B: segments split at repeated control points
        segs, cur = [], [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            if np.allclose(a, b):
                segs.append(np.array(cur))
                cur = [b]
            else:
                cur.append(b)
        segs.append(np.array(cur))
        poly = np.concatenate([_bezier(s) if len(s) > 2 else s for s in segs if len(s) >= 2])
    # resample by arc length
    d = np.r_[0.0, np.cumsum(np.hypot(*np.diff(poly, axis=0).T))]
    total = d[-1]
    if total < length and len(poly) >= 2:
        # osu! extends the final segment in a straight line
        v = poly[-1] - poly[-2]
        nv = np.linalg.norm(v)
        if nv > 1e-9:
            poly = np.vstack([poly, poly[-1] + v / nv * (length - total)])
            d = np.r_[d, length]
    s = np.linspace(0, length, max(2, int(length / step) + 1))
    return np.stack([np.interp(s, d, poly[:, 0]), np.interp(s, d, poly[:, 1])], axis=1)


def path_length(curve_type: str, points: List[Point]) -> float:
    pts = np.array(points, dtype=float)
    if curve_type == "P" and len(pts) == 3:
        c = circle_through(*pts)
        if c is not None:
            cx, cy = c
            r = math.hypot(pts[0][0] - cx, pts[0][1] - cy)
            a0 = math.atan2(pts[0][1] - cy, pts[0][0] - cx)
            a1 = math.atan2(pts[1][1] - cy, pts[1][0] - cx)
            a2 = math.atan2(pts[2][1] - cy, pts[2][0] - cx)
            ccw = ((a1 - a0) % (2 * math.pi)) < ((a2 - a0) % (2 * math.pi))
            sweep = ((a2 - a0) % (2 * math.pi)) if ccw else ((a0 - a2) % (2 * math.pi))
            return r * sweep
    if curve_type == "B":
        poly = _bezier(pts, 128)
    else:
        poly = pts
    return float(np.sum(np.hypot(*np.diff(poly, axis=0).T)))


def in_bounds(path: np.ndarray, margin: float = 8.0) -> bool:
    return bool(np.all(path[:, 0] >= margin) and np.all(path[:, 0] <= PLAYFIELD_W - margin)
                and np.all(path[:, 1] >= margin) and np.all(path[:, 1] <= PLAYFIELD_H - margin))


def make_arc(head: Point, direction: float, length: float, sweep: float) -> List[Point]:
    """Perfect-circle arc of given length starting at head heading `direction` and
    turning by `sweep` radians in total (sign = turn direction)."""
    r = length / abs(sweep)
    side = 1.0 if sweep > 0 else -1.0
    cx = head[0] + r * math.cos(direction + side * math.pi / 2)
    cy = head[1] + r * math.sin(direction + side * math.pi / 2)
    a0 = math.atan2(head[1] - cy, head[0] - cx)
    am = a0 + sweep / 2
    ae = a0 + sweep
    return [head, (cx + r * math.cos(am), cy + r * math.sin(am)), (cx + r * math.cos(ae), cy + r * math.sin(ae))]


def make_s_curve(head: Point, direction: float, length: float, bend: float) -> List[Point]:
    """Cubic bezier S-shape (two control points bent to opposite sides)."""
    ux, uy = math.cos(direction), math.sin(direction)
    px, py = -uy, ux
    span = length * 0.86
    pts = [head,
           (head[0] + ux * span / 3 + px * bend * span, head[1] + uy * span / 3 + py * bend * span),
           (head[0] + ux * 2 * span / 3 - px * bend * span, head[1] + uy * 2 * span / 3 - py * bend * span),
           (head[0] + ux * span, head[1] + uy * span)]
    # make sure the control path is at least as long as the slider so the game truncates, not extends
    for _ in range(12):
        if path_length("B", pts) >= length * 1.01:
            break
        pts = [pts[0]] + [(pts[0][0] + (x - pts[0][0]) * 1.06, pts[0][1] + (y - pts[0][1]) * 1.06) for x, y in pts[1:]]
    return pts


def end_tangent(path: np.ndarray) -> float:
    a, b = path[-2], path[-1]
    return math.atan2(b[1] - a[1], b[0] - a[0])
