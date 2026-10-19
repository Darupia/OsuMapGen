"""Measure osu!standard .osu files so mapping styles can be described with numbers.

    python tools/analyze_maps.py references/ -o references/_analysis/metrics.json
    python tools/analyze_maps.py "some map.osu"

Every metric is computed the same way for human maps and for OsuMapGen output, so the two are
directly comparable. Uses only the standard library plus rosu-pp-py (already a project dependency).
Non-standard game modes (taiko, catch, mania) are skipped.

Definitions
-----------
circle width      one circle diameter at the map's CS (distances are in circle widths)
stream            run of 4+ objects whose gaps are <= 0.3 beat (1/4 notes or faster)
jump gap          a gap of 0.45-1.1 beat; jump distance is measured over these gaps only, from where the
                  cursor leaves an object (slider end for odd slide counts) to the next head
rest              a gap of >= 1.45 beats since the previous object ended, or a slider held >= 0.97 beat
tapping stretch   seconds between rests
fast-tap stretch  consecutive 1 s bins holding >= 8 key presses (stream-speed tapping)
turn angle        change of cursor direction at an object: 0 = straight on, 180 = straight back
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

STREAM_GAP = 0.3
REST_GAP_BEATS = 1.45
HOLD_BEATS = 0.97
FAST_BIN_TAPS = 8


# ------------------------------------------------------------------ parsing
def _sections(text: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    cur = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            cur = line[1:-1]
            out[cur] = []
        elif cur and line and not line.startswith("//"):
            out[cur].append(line)
    return out


def _kv(lines: List[str]) -> Dict[str, str]:
    d = {}
    for line in lines:
        if ":" in line:
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()
    return d


class Beatmap:
    def __init__(self, path: Path):
        self.path = path
        text = path.read_text(encoding="utf-8", errors="replace")
        sec = _sections(text)
        gen, diff, meta = _kv(sec.get("General", [])), _kv(sec.get("Difficulty", [])), _kv(sec.get("Metadata", []))
        self.mode = int(gen.get("Mode", 0))
        self.version = meta.get("Version", "?")
        self.creator = meta.get("Creator", "?")
        self.title = meta.get("Title", "?")
        self.artist = meta.get("Artist", "?")
        self.cs = float(diff.get("CircleSize", 4))
        self.ar = float(diff.get("ApproachRate", diff.get("OverallDifficulty", 5)))
        self.od = float(diff.get("OverallDifficulty", 5))
        self.hp = float(diff.get("HPDrainRate", 5))
        self.sm = float(diff.get("SliderMultiplier", 1.4))
        self.timing = []                       # (time, beat_ms, uninherited, sv)
        for line in sec.get("TimingPoints", []):
            p = line.split(",")
            if len(p) < 2:
                continue
            red = (p[6] == "1") if len(p) > 6 else True
            self.timing.append((float(p[0]), float(p[1]), red))
        self.objs: List[dict] = []
        for line in sec.get("HitObjects", []):
            p = line.split(",")
            if len(p) < 4:
                continue
            ty, t = int(p[3]), int(float(p[2]))
            o = {"t": t, "x": int(float(p[0])), "y": int(float(p[1])),
                 "kind": "spinner" if ty & 8 else "slider" if ty & 2 else "circle"}
            o["ex"], o["ey"] = o["x"], o["y"]            # where the cursor leaves this object
            if o["kind"] == "slider":
                o["shape"], o["slides"], o["len"] = p[5][0], int(p[6]), float(p[7])
                pts = [q.split(":") for q in p[5].split("|")[1:] if ":" in q]
                if pts and o["slides"] % 2 == 1:         # odd slide count ends at the far end (last control point)
                    o["ex"], o["ey"] = int(float(pts[-1][0])), int(float(pts[-1][1]))
            self.objs.append(o)
        self.objs.sort(key=lambda o: o["t"])
        for o in self.objs:
            o["beat"], o["sv"] = self._timing_at(o["t"])
            o["end"] = o["t"]
            if o["kind"] == "slider":
                o["end"] = o["t"] + int(o["len"] / (self.sm * 100 * o["sv"]) * o["beat"] * o["slides"])
            elif o["kind"] == "spinner":
                o["end"] = o["t"]

    def _timing_at(self, t: float):
        beat, sv = 500.0, 1.0
        for pt, bl, red in self.timing:
            if pt <= t + 1:
                if red:
                    beat, sv = bl, 1.0
                elif bl < 0:
                    sv = -100.0 / bl
        return beat, sv

    @property
    def diameter(self) -> float:
        return 2 * (54.4 - 4.48 * self.cs)


# ------------------------------------------------------------------ helpers
def _pct(xs: List[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[int(q * (len(s) - 1))]


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def tapping_stretches(hits: List[dict]) -> List[float]:
    out, start, last_end, hold = [], None, None, False
    for o in hits:
        t, e, beat = o["t"], o["end"], o["beat"]
        if start is None:
            start = t
        elif hold or t - last_end >= REST_GAP_BEATS * beat:
            out.append((last_end - start) / 1000.0)
            start = t
        hold = o["kind"] == "slider" and (e - t) >= HOLD_BEATS * beat
        last_end = e
        if hold:
            out.append((t - start) / 1000.0)
            start = None
    if start is not None:
        out.append((last_end - start) / 1000.0)
    return sorted(out, reverse=True)


def fast_tap_stretches(hits: List[dict]) -> List[int]:
    if not hits:
        return []
    bins = [0] * (hits[-1]["t"] // 1000 + 2)
    for o in hits:
        bins[o["t"] // 1000] += 1
    out, cur = [], 0
    for c in bins:
        if c >= FAST_BIN_TAPS:
            cur += 1
        else:
            if cur:
                out.append(cur)
            cur = 0
    if cur:
        out.append(cur)
    return sorted(out, reverse=True)


def _window_class(hits, gaps, dists, idx) -> str:
    if len(idx) < 3:
        return "."
    g = [gaps[i] for i in idx]
    d = [dists[i] for i in idx]
    fast = sum(1 for x in g if x <= STREAM_GAP) / len(g)
    sl = sum(1 for i in idx if hits[i]["kind"] == "slider") / len(idx)
    jg = [(x, y) for x, y in zip(g, d) if 0.45 <= x <= 1.1]
    far = sum(1 for x, y in jg if y >= 2.2) / max(1, len(jg))
    if fast >= 0.5:
        return "S"
    if sl >= 0.5:
        return "L"
    if far >= 0.5:
        return "J"
    if fast >= 0.2:
        return "B"
    return "m"


def timeline(hits, gaps, dists, window_ms: int = 10000) -> str:
    out = []
    for ws in range(hits[0]["t"], hits[-1]["t"], window_ms):
        idx = [i for i, o in enumerate(hits[:-1]) if ws <= o["t"] < ws + window_ms]
        out.append(_window_class(hits, gaps, dists, idx))
    return "".join(out)


# ------------------------------------------------------------------ main measurement
def measure(path: Path, stars: Optional[float] = None) -> Optional[dict]:
    bm = Beatmap(path)
    if bm.mode != 0:
        return None
    hits = [o for o in bm.objs if o["kind"] != "spinner"]
    if len(hits) < 20:
        return None
    if stars is None:
        import rosu_pp_py as rp
        stars = rp.Difficulty().calculate(rp.Beatmap(path=str(path))).stars
    diam = bm.diameter
    n = len(hits)
    gaps, dists = [], []
    for a, b in zip(hits, hits[1:]):
        gaps.append((b["t"] - a["t"]) / a["beat"])
        dists.append(math.dist((a["ex"], a["ey"]), (b["x"], b["y"])) / diam)

    # streams
    runs, cur, cur_d, cur_idx = [], 0, [], []
    for i, (g, d) in enumerate(zip(gaps, dists)):
        if g <= STREAM_GAP:
            cur += 1
            cur_d.append(d)
            cur_idx.append(i)
        else:
            if cur >= 3:
                runs.append((cur + 1, _mean(cur_d), cur_idx[:]))
            cur, cur_d, cur_idx = 0, [], []
    if cur >= 3:
        runs.append((cur + 1, _mean(cur_d), cur_idx[:]))
    stream_notes = sum(r[0] for r in runs)
    run_lengths = [r[0] for r in runs]
    burst_runs = sum(1 for r in run_lengths if r <= 7)

    # turns inside streams and across the map
    def turn(i):
        a, b, c = hits[i], hits[i + 1], hits[i + 2]
        v1 = (b["x"] - a["ex"], b["y"] - a["ey"])
        v2 = (c["x"] - b["ex"], c["y"] - b["ey"])
        if math.hypot(*v1) < 2 or math.hypot(*v2) < 2:
            return None
        ang = abs(math.degrees(math.atan2(v2[1], v2[0]) - math.atan2(v1[1], v1[0])))
        return 360 - ang if ang > 180 else ang
    turns_all, turns_stream = [], []
    stream_idx = {i for r in runs for i in r[2]}
    for i in range(len(hits) - 2):
        t = turn(i)
        if t is None or gaps[i] > 1.1 or gaps[i + 1] > 1.1:
            continue
        turns_all.append(t)
        if i in stream_idx and (i + 1) in stream_idx:
            turns_stream.append(t)

    jd = [d for g, d in zip(gaps, dists) if 0.45 <= g <= 1.1]
    jd_mean = _mean(jd)
    jd_cv = (math.sqrt(_mean((x - jd_mean) ** 2 for x in jd)) / jd_mean) if jd_mean else 0.0

    # rhythm
    snaps = collections.Counter()
    for g in gaps:
        for name, v in (("1/1", 1.0), ("1/2", .5), ("1/3", 1 / 3), ("1/4", .25), ("1/6", 1 / 6), ("1/8", .125), ("2/3", 2 / 3), ("3/4", .75), ("3/2", 1.5)):
            if abs(g - v) < 0.04:
                snaps[name] += 1
                break
        else:
            snaps[">2" if g > 2.04 else "other"] += 1
    odd = (snaps["1/3"] + snaps["1/6"] + snaps["2/3"] + snaps["3/4"]) / max(1, len(gaps))

    # sliders
    sl = [o for o in hits if o["kind"] == "slider"]
    sl_beats = [(o["end"] - o["t"]) / (o["beat"] * o["slides"]) for o in sl]
    buzz = sum(1 for o in sl if o["slides"] >= 4 and o["len"] < 90)
    kick = sum(1 for o, b in zip(sl, sl_beats) if o["slides"] == 2 and b <= 0.55)

    stack = sum(1 for d, g in zip(dists, gaps) if d < 0.05 and g <= 0.55)

    # repetition: share of 8-note windows (rhythm, distance, turn) that occur 3+ times
    toks = []
    for i, (g, d) in enumerate(zip(gaps, dists)):
        t = turn(i - 1) if i > 0 else None
        toks.append((round(g * 4) / 4, min(int(d * 1.5), 8), None if t is None else int(t // 45)))
    grams = collections.Counter(tuple(toks[i:i + 8]) for i in range(len(toks) - 7))
    rep8 = sum(c for c in grams.values() if c >= 3) / max(1, sum(grams.values()))

    tl = timeline(hits, gaps, dists)
    tl_counts = collections.Counter(tl)
    stretches = tapping_stretches(hits)
    fast = fast_tap_stretches(hits)
    dur_min = (hits[-1]["end"] - hits[0]["t"]) / 60000.0
    per10 = collections.Counter(o["t"] // 10000 for o in hits)

    bpms = sorted({round(60000 / bl, 1) for _, bl, red in bm.timing if red and bl > 0})
    return {
        "file": str(path), "title": bm.title, "artist": bm.artist, "mapper": bm.creator, "version": bm.version,
        "stars": round(stars, 2), "ar": bm.ar, "od": bm.od, "cs": bm.cs, "hp": bm.hp,
        "bpm_min": bpms[0] if bpms else 0, "bpm_max": bpms[-1] if bpms else 0, "bpm_changes": len(bpms),
        "objects": n, "minutes": round(dur_min, 2), "objects_per_min": round(n / max(0.1, dur_min)),
        "peak_objects_per_10s": max(per10.values()),
        "circles_pct": round(100 * sum(o["kind"] == "circle" for o in hits) / n, 1),
        "slider_pct": round(100 * len(sl) / n, 1),
        "slider_repeat_pct": round(100 * sum(o["slides"] >= 2 for o in sl) / max(1, len(sl)), 1),
        "slider_short_pct": round(100 * sum(b < 1.0 for b in sl_beats) / max(1, len(sl)), 1),
        "slider_beats_median": round(_pct(sl_beats, .5), 2), "slider_beats_p90": round(_pct(sl_beats, .9), 2),
        "buzz_sliders": buzz, "kick_sliders": kick,
        "slider_shapes": dict(collections.Counter(o["shape"] for o in sl)),
        "spinners": len(bm.objs) - n,
        "stream_pct": round(100 * stream_notes / n, 1), "stream_runs": len(runs),
        "burst_runs_3_7": burst_runs,
        "run_mean": round(_mean(run_lengths), 1), "run_median": _pct(run_lengths, .5), "run_p90": _pct(run_lengths, .9),
        "run_max": max(run_lengths, default=0),
        "run_length_distinct": len(set(run_lengths)),
        "stream_spacing": round(_mean(r[1] for r in runs), 2),
        "stream_turn_mean_deg": round(_mean(turns_stream), 1),
        "jump_mean": round(jd_mean, 2), "jump_p50": round(_pct(jd, .5), 2), "jump_p90": round(_pct(jd, .9), 2),
        "jump_max": round(max(jd, default=0), 2), "jump_cv": round(jd_cv, 2),
        "turn_mean_deg": round(_mean(turns_all), 1),
        "sharp_turn_pct": round(100 * sum(t >= 120 for t in turns_all) / max(1, len(turns_all)), 1),
        "straight_pct": round(100 * sum(t <= 30 for t in turns_all) / max(1, len(turns_all)), 1),
        "stack_pct": round(100 * stack / n, 1), "stacks": stack,
        "snaps": dict(snaps), "odd_rhythm_pct": round(100 * odd, 1),
        "rep8_pct": round(100 * rep8, 1),
        "longest_tap_s": round(stretches[0], 1) if stretches else 0,
        "tap_over_15s": sum(x > 15 for x in stretches), "tap_over_10s": sum(x > 10 for x in stretches),
        "longest_fast_tap_s": fast[0] if fast else 0, "fast_over_10s": sum(x > 10 for x in fast),
        "fast_tap_total_s": sum(fast),
        "sv_changes": len({round(sv, 2) for o in hits for sv in [o["sv"]]}) - 1,
        "timeline": tl, "timeline_share": {k: round(v / len(tl), 2) for k, v in tl_counts.items()},
    }


def collect(paths: List[str]) -> List[Path]:
    out = []
    for p in paths:
        p = Path(p)
        out.extend(sorted(p.rglob("*.osu")) if p.is_dir() else [p])
    return [p for p in out if "_analysis" not in p.parts]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help=".osu files or folders (searched recursively)")
    ap.add_argument("-o", "--out", help="write all metrics to this JSON file")
    args = ap.parse_args(argv)
    rows, skipped = [], []
    for p in collect(args.paths):
        try:
            m = measure(p)
        except Exception as e:                      # one bad file must not stop the batch
            skipped.append((str(p), f"error: {e}"))
            continue
        if m is None:
            skipped.append((str(p), "not osu!standard or too few objects"))
            continue
        # group = first folder under the references root, if any
        parts = p.parts
        m["group"] = next((parts[i + 1] for i, s in enumerate(parts) if s == "references" and i + 1 < len(parts) - 1), "")
        m["mapset"] = p.parent.name
        rows.append(m)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"maps": rows, "skipped": skipped}, indent=1), encoding="utf-8")
    else:
        for m in rows:
            print(f"{m['mapper']} [{m['version']}] {m['stars']}* | streams {m['stream_pct']}% (max run {m['run_max']}) | "
                  f"jumps {m['jump_mean']} | sliders {m['slider_pct']}% | {m['timeline']}")
    print(f"measured {len(rows)} maps, skipped {len(skipped)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
