"""Draw osu!standard pattern excerpts as SVG (standard library only).

    # one explicit excerpt per panel:  file | start_s | end_s | label
    python tools/pattern_svg.py out.svg --panel "map.osu|61.0|69.0|stream section"

    # let the tool find the best excerpt of a kind in a map:  stream jump slider buzz stack odd
    python tools/pattern_svg.py out.svg --auto "map.osu|stream|8|label" --auto "other.osu|jump|8|label"

Each panel shows the playfield (512x384) with every object in the window, numbered in play order and
coloured from blue (first) to orange (last). Grey lines are the cursor path between objects. Slider
bodies are drawn through their control points, so curves are approximate. Circle size follows the map's CS.
Convert to PNG with tools/svg_to_png.mjs (needs the Chromium that Playwright ships).
"""

from __future__ import annotations

import argparse
import html
import math
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_maps import Beatmap, STREAM_GAP  # noqa: E402

SCALE = 0.95
PW, PH = 512 * SCALE, 384 * SCALE
HEAD = 66
GAP = 18
KINDS = ("stream", "jump", "slider", "buzz", "stack", "odd")


def _hits(bm: Beatmap):
    return [o for o in bm.objs if o["kind"] != "spinner"]


def window_score(bm: Beatmap, hits, t0: int, t1: int, kind: str) -> float:
    idx = [i for i, o in enumerate(hits) if t0 <= o["t"] < t1]
    if len(idx) < 6:
        return -1.0
    diam = bm.diameter
    gaps = [(hits[i + 1]["t"] - hits[i]["t"]) / hits[i]["beat"] for i in idx if i + 1 < len(hits)]
    dists = [math.dist((hits[i]["ex"], hits[i]["ey"]), (hits[i + 1]["x"], hits[i + 1]["y"])) / diam
             for i in idx if i + 1 < len(hits)]
    if kind == "stream":
        return float(sum(1 for g in gaps if g <= STREAM_GAP))
    if kind == "jump":
        jd = [d for g, d in zip(gaps, dists) if 0.45 <= g <= 1.1]
        return (sum(jd) / len(jd)) * min(1.0, len(jd) / 8.0) if len(jd) >= 6 else -1.0
    if kind == "slider":
        return float(sum(1 for i in idx if hits[i]["kind"] == "slider"))
    if kind == "buzz":
        return float(sum(1 for i in idx if hits[i]["kind"] == "slider" and hits[i]["slides"] >= 4 and hits[i]["len"] < 90))
    if kind == "stack":
        return float(sum(1 for d, g in zip(dists, gaps) if d < 0.05 and g <= 0.55))
    if kind == "odd":
        return float(sum(1 for g in gaps if any(abs(g - v) < 0.04 for v in (1 / 3, 1 / 6, 2 / 3, 0.75))))
    raise ValueError(f"unknown kind {kind!r}; choose from {KINDS}")


def best_window(bm: Beatmap, kind: str, seconds: float) -> Tuple[float, float]:
    hits = _hits(bm)
    best, best_t = -1.0, hits[0]["t"]
    w = int(seconds * 1000)
    for o in hits:
        s = window_score(bm, hits, o["t"], o["t"] + w, kind)
        if s > best:
            best, best_t = s, o["t"]
    return best_t / 1000.0, (best_t + w) / 1000.0


def _circumcircle(p1, p2, p3):
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-6:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy, math.hypot(ax - ux, ay - uy)


def _slider_path(o, line: str) -> str:
    pts = [(o["x"], o["y"])] + [tuple(float(v) for v in q.split(":")) for q in line.split("|")[1:] if ":" in q]
    s = lambda p: (p[0] * SCALE, p[1] * SCALE)
    pts = [s(p) for p in pts]
    if o["shape"] == "P" and len(pts) == 3:
        cc = _circumcircle(*pts)
        if cc:
            ux, uy, r = cc
            a0 = math.atan2(pts[0][1] - uy, pts[0][0] - ux)
            a1 = math.atan2(pts[1][1] - uy, pts[1][0] - ux)
            a2 = math.atan2(pts[2][1] - uy, pts[2][0] - ux)
            two_pi = 2 * math.pi
            ccw = ((a1 - a0) % two_pi) < ((a2 - a0) % two_pi)
            sweep = (a2 - a0) % two_pi if ccw else (a0 - a2) % two_pi
            return f"M{pts[0][0]:.1f},{pts[0][1]:.1f} A{r:.1f},{r:.1f} 0 {1 if sweep > math.pi else 0} {1 if ccw else 0} {pts[2][0]:.1f},{pts[2][1]:.1f}"
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def _colour(frac: float) -> str:
    hue = 215 - 195 * frac                      # blue -> orange
    return f"hsl({hue:.0f},70%,52%)"


def render_panel(bm: Beatmap, t0_s: float, t1_s: float, label: str, x0: float, y0: float, raw_lines,
                 max_objects: int = 26) -> str:
    hits = [o for o in _hits(bm) if t0_s * 1000 <= o["t"] < t1_s * 1000][:max_objects]
    if hits:
        t1_s = min(t1_s, hits[-1]["t"] / 1000.0)
    r = (54.4 - 4.48 * bm.cs) * SCALE
    g = [f'<g transform="translate({x0:.0f},{y0:.0f})">']
    g.append(f'<text x="0" y="16" font-size="15" font-weight="600">{html.escape(label)}</text>')
    stars = getattr(bm, "stars", None)
    ver = bm.version if len(bm.version) <= 34 else bm.version[:33] + "..."
    sub = f"{ver} ({bm.creator})" + (f"  {stars:.2f}*" if stars else "")
    g.append(f'<text x="0" y="33" font-size="11" fill="#555">{html.escape(sub)}</text>')
    dur = max(0.1, t1_s - t0_s)
    g.append(f'<text x="0" y="47" font-size="11" fill="#555">{t0_s:.1f}s-{t1_s:.1f}s  {len(hits)} objects in {dur:.1f}s  CS{bm.cs:g} AR{bm.ar:g}</text>')
    g.append(f'<g transform="translate(0,{HEAD - 12})"><rect width="{PW:.0f}" height="{PH:.0f}" fill="#f7f6f1" stroke="#999"/>')
    # cursor path
    prev = None
    for o in hits:
        if prev is not None:
            g.append(f'<line x1="{prev["ex"] * SCALE:.1f}" y1="{prev["ey"] * SCALE:.1f}" x2="{o["x"] * SCALE:.1f}" y2="{o["y"] * SCALE:.1f}" stroke="#777" stroke-width="1.2" opacity="0.55"/>')
        prev = o
    n = max(1, len(hits) - 1)
    for k, o in enumerate(hits):
        col = _colour(k / n)
        if o["kind"] == "slider":
            line = raw_lines.get((o["t"], o["x"], o["y"]), "")
            if line:
                g.append(f'<path d="{_slider_path(o, line)}" fill="none" stroke="{col}" stroke-opacity="0.35" stroke-width="{2 * r:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
                g.append(f'<path d="{_slider_path(o, line)}" fill="none" stroke="{col}" stroke-opacity="0.9" stroke-width="1.5"/>')
                if o["slides"] > 1:
                    g.append(f'<text x="{o["ex"] * SCALE:.1f}" y="{o["ey"] * SCALE + 4:.1f}" font-size="10" text-anchor="middle" fill="#222">x{o["slides"]}</text>')
        g.append(f'<circle cx="{o["x"] * SCALE:.1f}" cy="{o["y"] * SCALE:.1f}" r="{r:.1f}" fill="{col}" fill-opacity="0.82" stroke="#222" stroke-width="1"/>')
        g.append(f'<text x="{o["x"] * SCALE:.1f}" y="{o["y"] * SCALE + 3.5:.1f}" font-size="{max(7, r * 0.7):.0f}" text-anchor="middle" fill="#fff" font-weight="700">{k + 1}</text>')
    g.append("</g></g>")
    return "\n".join(g)


def _raw_slider_lines(path: Path):
    lines, in_obj = {}, False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line == "[HitObjects]":
            in_obj = True
        elif line.startswith("[") and in_obj:
            break
        elif in_obj and line:
            p = line.split(",")
            if len(p) > 5 and int(p[3]) & 2:
                lines[(int(float(p[2])), int(float(p[0])), int(float(p[1])))] = p[5]
    return lines


def build_sheet(panels: List[Tuple[Path, float, float, str]], cols: int = 3, title: str = "", max_objects: int = 26) -> str:
    cw, ch = PW + GAP, PH + HEAD + GAP
    rows = math.ceil(len(panels) / cols)
    ncols = min(cols, len(panels))
    width = ncols * cw + GAP
    top = 44 if title else GAP
    height = rows * ch + top + GAP
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" font-family="Segoe UI, Helvetica, Arial, sans-serif">',
           f'<rect width="100%" height="100%" fill="#ffffff"/>']
    if title:
        out.append(f'<text x="{GAP}" y="30" font-size="22" font-weight="700">{html.escape(title)}</text>')
    for i, (path, t0, t1, label) in enumerate(panels):
        bm = Beatmap(path)
        try:
            import rosu_pp_py as rp
            bm.stars = rp.Difficulty().calculate(rp.Beatmap(path=str(path))).stars
        except Exception:
            pass
        x = GAP + (i % cols) * cw
        y = top + (i // cols) * ch
        out.append(render_panel(bm, t0, t1, label, x, y, _raw_slider_lines(path), max_objects))
    out.append("</svg>")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--panel", action="append", default=[], help="file|start_s|end_s|label")
    ap.add_argument("--auto", action="append", default=[], help="file|kind|seconds|label")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--title", default="")
    ap.add_argument("--max-objects", type=int, default=26, help="objects drawn per panel (keeps excerpts legible)")
    args = ap.parse_args(argv)
    panels = []
    for spec in args.panel:
        f, a, b, label = (spec.split("|") + [""])[:4]
        panels.append((Path(f), float(a), float(b), label))
    for spec in args.auto:
        f, kind, secs, label = (spec.split("|") + [""])[:4]
        t0, t1 = best_window(Beatmap(Path(f)), kind, float(secs))
        panels.append((Path(f), t0, t1, label or kind))
    if not panels:
        ap.error("give at least one --panel or --auto")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(build_sheet(panels, args.cols, args.title, args.max_objects), encoding="utf-8")
    print(f"wrote {args.out} ({len(panels)} panels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
