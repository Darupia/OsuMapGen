"""Copy the .osu files out of sorted .osz mapsets into references/<style>/<mapset>/.

Usage:
    python tools/import_references.py "C:/Users/you/Documents/References" references

The source folder holds one sub-folder per style (Balance/Balanced, Jump, Stream, Tech) with
.osz files (or already-extracted mapset folders) inside. Only .osu files are copied: no audio,
images or storyboards. Existing files in the destination are left alone, so re-running is safe.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

GROUPS = {"balance": "balanced", "balanced": "balanced", "jump": "jump", "stream": "stream", "tech": "tech",
          "technical": "tech", "simple": "simple", "slider": "slider"}


def safe_name(name: str, limit: int = 90) -> str:
    """Windows-safe name. Long names keep their END (the "(mapper) [difficulty].osu" part that
    the audit exclusions in docs/styles/data/*.json match on), so paths stay under MAX_PATH."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")
    if len(name) > limit:
        name = name[-limit:].lstrip(" -_")
    return name or "mapset"


def import_refs(src: Path, dst: Path) -> dict:
    counts: dict = {}
    for group_dir in sorted(p for p in src.iterdir() if p.is_dir()):
        group = GROUPS.get(group_dir.name.lower())
        if group is None:
            print(f"skip folder {group_dir.name!r} (not a known style name)")
            continue
        for item in sorted(group_dir.iterdir()):
            mapset = safe_name(item.stem if item.is_file() else item.name, limit=60)
            out = dst / group / mapset
            n = 0
            if item.is_file() and item.suffix.lower() == ".osz":
                with zipfile.ZipFile(item) as z:
                    for info in z.infolist():
                        base = Path(info.filename.replace("\\", "/")).name      # never trust paths in the zip
                        if not base.lower().endswith(".osu") or info.file_size > 20_000_000:
                            continue
                        target = out / safe_name(base)
                        if target.exists():
                            continue
                        out.mkdir(parents=True, exist_ok=True)
                        with z.open(info) as fsrc, open(target, "wb") as fdst:
                            shutil.copyfileobj(fsrc, fdst)
                        n += 1
            elif item.is_dir():
                for osu in item.rglob("*.osu"):
                    target = out / safe_name(osu.name)
                    if not target.exists():
                        out.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(osu, target)
                        n += 1
            counts.setdefault(group, [0, 0])
            counts[group][0] += 1
            counts[group][1] += n
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source")
    ap.add_argument("dest", nargs="?", default="references")
    args = ap.parse_args(argv)
    src, dst = Path(args.source), Path(args.dest)
    if not src.is_dir():
        print(f"not a folder: {src}")
        return 1
    for group, (mapsets, osus) in import_refs(src, dst).items():
        print(f"{group:9s} {mapsets:3d} mapsets, {osus:4d} new .osu files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
