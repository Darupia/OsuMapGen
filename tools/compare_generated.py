"""Score generated maps against the measured human ranges in docs/styles/data/*.json.

    python tools/compare_generated.py references/_analysis/generated.json
    python tools/compare_generated.py generated.json --style stream --band 5.5-6.5 --metrics stream_pct,run_max

The input is a JSON file written by `python tools/analyze_maps.py <maps> -o file.json`; each map must have a
"group" field (stream | jump | tech | balanced) naming the style it was generated as. For every style and star
band the tool prints the generated median next to the human p10 / p50 / p90 and marks each metric:
    ok    generated median is inside the human p10-p90
    LOW   below human p10        HIGH  above human p90
Maps are put in the band of their own estimated star rating, so a 6.0-star map is compared with 5.5-6.5.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "docs" / "styles" / "data"
BANDS = [("4.5-5.5", 4.5, 5.5), ("5.5-6.5", 5.5, 6.5), ("6.5+", 6.5, 99.0)]
DEFAULT_METRICS = [
    "objects_per_min", "stream_pct", "run_median", "run_max", "stream_spacing", "jump_mean", "jump_p90",
    "sharp_turn_pct", "straight_pct", "slider_pct", "slider_repeat_pct", "buzz_sliders", "kick_sliders",
    "stack_pct", "odd_rhythm_pct", "longest_tap_s", "longest_fast_tap_s", "rep8_pct",
]
ALIASES = {"objects_per_min": "objects_per_min"}


def human_bands(style: str) -> dict:
    path = DATA / f"{style}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("bands", {})


def compare(maps: list, style: str, band: str, lo: float, hi: float, metrics: list):
    gen = [m for m in maps if m.get("group") == style and lo <= m["stars"] < hi]
    ref = human_bands(style).get(band)
    if not gen or not ref:
        return None
    rows, ok = [], 0
    for k in metrics:
        h = ref["metrics"].get(k)
        if h is None:
            continue
        g = statistics.median(m[k] for m in gen)
        status = "ok" if h["p10"] <= g <= h["p90"] else ("LOW" if g < h["p10"] else "HIGH")
        ok += status == "ok"
        rows.append((k, g, h, status))
    return len(gen), ref["n"], rows, ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("generated")
    ap.add_argument("--style", action="append", help="stream, jump, tech or balanced (default: all)")
    ap.add_argument("--band", action="append", help="4.5-5.5, 5.5-6.5 or 6.5+ (default: all)")
    ap.add_argument("--metrics", help="comma separated metric names")
    ap.add_argument("--quiet", action="store_true", help="only print the per-style summary")
    args = ap.parse_args(argv)
    maps = json.loads(Path(args.generated).read_text(encoding="utf-8"))["maps"]
    metrics = args.metrics.split(",") if args.metrics else DEFAULT_METRICS
    total_ok = total = 0
    for style in args.style or ["stream", "jump", "tech", "balanced"]:
        for band, lo, hi in BANDS:
            if args.band and band not in args.band:
                continue
            res = compare(maps, style, band, lo, hi, metrics)
            if res is None:
                continue
            n_gen, n_ref, rows, ok = res
            total_ok += ok
            total += len(rows)
            print(f"\n== {style} {band}: {n_gen} generated vs {n_ref} human maps   {ok}/{len(rows)} metrics inside the human p10-p90")
            if args.quiet:
                continue
            for k, g, h, status in rows:
                print(f"   {k:20s} generated {g:8.1f}   human {h['p10']:7.1f} / {h['p50']:7.1f} / {h['p90']:7.1f}   {status}")
    if total:
        print(f"\nOVERALL {total_ok}/{total} metrics inside the human range ({100 * total_ok / total:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
