"""Entry point.

  python -m osumapgen                 -> graphical interface
  python -m osumapgen song.mp3 4.5    -> command line generation
  python -m osumapgen --check         -> dependency check
"""

from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="osumapgen", description="Generate an osu!standard beatmap from an MP3.")
    ap.add_argument("mp3", nargs="?", help="input MP3 (omit to open the GUI)")
    ap.add_argument("stars", nargs="?", type=float, help="target star rating, e.g. 4.5")
    ap.add_argument("--style", default="Auto", help="Auto, Simple and readable, Stream-focused, Jump-focused, "
                                                    "Technical, Slider-focused, 'Balanced mix (all styles)'")
    ap.add_argument("--out", default="", help="output folder (default: Documents/OsuMapGen Output)")
    ap.add_argument("--title")
    ap.add_argument("--artist")
    ap.add_argument("--username", help="your osu! username for the Creator field (CASE-SENSITIVE: "
                                       "must match your profile exactly)")
    ap.add_argument("--tolerance", type=float, default=0.5)
    ap.add_argument("--mapset", action="store_true", help="make a full mapset: several difficulties from Easy "
                                                          "up to the target stars, in one .osz")
    ap.add_argument("--check", action="store_true", help="check dependencies and exit")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    from .infra import setup_logging
    setup_logging(args.verbose)
    if args.check:
        from .deps import check_dependencies
        rep = check_dependencies()
        print(rep.describe())
        return 0 if rep.ok else 1
    if not args.mp3:
        from .gui import run_gui
        run_gui()
        return 0
    if args.stars is None:
        ap.error("a target star rating is required in command-line mode")

    from .infra import Progress, UserFacingError, Cancelled
    from .pipeline import GenerationRequest, run

    def cb(v, msg):
        print(f"\r[{v * 100:5.1f}%] {msg[:70]:<70}", end="", flush=True)

    req = GenerationRequest(mp3_path=args.mp3, stars=args.stars, style=args.style, output_dir=args.out,
                            title=args.title, artist=args.artist, tolerance=args.tolerance,
                            creator=args.username, mapset=args.mapset)
    try:
        res = run(req, Progress(callback=cb))
    except (UserFacingError, Cancelled) as e:
        print(f"\nError: {e}")
        return 2
    print()
    print(res.message)
    if res.style_breakdown:
        print(res.style_breakdown)
    for d in res.difficulties:
        print(f"  [{d.version}] requested {d.requested_stars:.2f}, estimated {d.estimated_stars:.2f} (lazer) / "
              f"{d.estimated_stars_stable:.2f} (stable), {d.objects} objects"
              + ("" if d.ok else "  SKIPPED: failed validation"))
    if res.estimated_stars is not None and not res.mapset:
        print(f"Requested {res.requested_stars:.2f} stars; estimated {res.estimated_stars:.2f} (lazer) / "
              f"{res.estimated_stars_stable:.2f} (stable)")
    for w in res.warnings:
        print("warning:", w)
    for e in res.errors:
        print("error:", e)
    if res.osz_path:
        print("Package:", res.osz_path)
    if res.report_path:
        print("Report: ", res.report_path)
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
