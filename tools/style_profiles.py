"""Turn analyze_maps.py output into per-style, per-star-band target ranges.

    python tools/style_profiles.py references/_analysis/metrics.json --group jump --min-stars 4.5
    python tools/style_profiles.py references/_analysis/metrics.json --group tech --exclude "Taiko" --json

Prints, for each star band, the number of maps and the 10th / 50th / 90th percentile of every key metric.
Use --exclude (a substring of the .osu path, repeatable) to drop maps an audit judged mislabeled.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BANDS = [("easy <3", 0, 3), ("3-4.5", 3, 4.5), ("4.5-5.5", 4.5, 5.5), ("5.5-6.5", 5.5, 6.5), ("6.5+", 6.5, 99)]

KEY_METRICS = [
    "objects_per_min", "peak_objects_per_10s",
    "stream_pct", "run_median", "run_p90", "run_max", "stream_spacing", "stream_turn_mean_deg", "burst_runs_3_7",
    "jump_mean", "jump_p90", "jump_cv", "turn_mean_deg", "sharp_turn_pct", "straight_pct",
    "slider_pct", "slider_repeat_pct", "slider_short_pct", "slider_beats_median", "buzz_sliders", "kick_sliders",
    "stack_pct", "odd_rhythm_pct", "spinners",
    "longest_tap_s", "tap_over_15s", "longest_fast_tap_s", "fast_tap_total_s", "rep8_pct",
    "ar", "od", "cs", "hp",
]


def pct(values, q):
    s = sorted(values)
    return s[int(q * (len(s) - 1))] if s else 0.0


def profile(maps, group=None, min_stars=0.0, max_stars=99.0, exclude=()):
    rows = [m for m in maps
            if (group is None or m["group"] == group)
            and min_stars <= m["stars"] < max_stars
            and not any(x in m["file"] for x in exclude)]
    out = {"group": group, "n_maps": len(rows), "mapsets": len({m["mapset"] for m in rows}), "bands": {}}
    for name, lo, hi in BANDS:
        band = [m for m in rows if lo <= m["stars"] < hi]
        if not band:
            continue
        entry = {"n": len(band), "mapsets": len({m["mapset"] for m in band}),
                 "stars": [min(m["stars"] for m in band), max(m["stars"] for m in band)], "metrics": {}}
        for k in KEY_METRICS:
            vals = [m[k] for m in band if k in m]
            entry["metrics"][k] = {"p10": round(pct(vals, .1), 2), "p50": round(pct(vals, .5), 2), "p90": round(pct(vals, .9), 2)}
        shares = {}
        for m in band:
            for kind, v in m["timeline_share"].items():
                shares.setdefault(kind, []).append(v)
        entry["timeline_share_mean"] = {k: round(sum(v) / len(band), 2) for k, v in shares.items()}
        out["bands"][name] = entry
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("metrics")
    ap.add_argument("--group")
    ap.add_argument("--min-stars", type=float, default=0.0)
    ap.add_argument("--max-stars", type=float, default=99.0)
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args(argv)
    maps = json.loads(Path(args.metrics).read_text(encoding="utf-8"))["maps"]
    prof = profile(maps, args.group, args.min_stars, args.max_stars, args.exclude)
    if args.json:
        print(json.dumps(prof, indent=1))
        return 0
    print(f"group={args.group} maps={prof['n_maps']} mapsets={prof['mapsets']}")
    for name, e in prof["bands"].items():
        print(f"\n== {name}  n={e['n']} ({e['mapsets']} mapsets)  stars {e['stars'][0]}-{e['stars'][1]}")
        print(f"   timeline share (10 s windows): {e['timeline_share_mean']}")
        for k, v in e["metrics"].items():
            print(f"   {k:24s} p10 {v['p10']:8} p50 {v['p50']:8} p90 {v['p90']:8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
