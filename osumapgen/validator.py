"""Independent validation of a generated .osu file (and its .osz package).

The file is re-parsed from text, so this checks what was actually written,
not the in-memory objects. Structural problems are errors; musical/quality
concerns are warnings unless they make the map unusable (e.g. a mapped
section left empty, or a map that stops long before the song does).
"""

from __future__ import annotations

import math
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from . import curves
from .model import SongAnalysis

REQUIRED_SECTIONS = ["General", "Editor", "Metadata", "Difficulty", "Events", "TimingPoints", "HitObjects"]


@dataclass
class Issue:
    severity: str            # "error" | "warning"
    code: str
    message: str
    time_ms: Optional[int] = None
    section: Optional[int] = None

    def __str__(self):
        where = f" @ {self.time_ms / 1000:.2f}s" if self.time_ms is not None else ""
        return f"[{self.severity}] {self.code}{where}: {self.message}"


@dataclass
class ValidationReport:
    issues: List[Issue] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code, msg, t=None, sec=None):
        self.issues.append(Issue("error", code, msg, None if t is None else int(t), sec))

    def warn(self, code, msg, t=None, sec=None):
        self.issues.append(Issue("warning", code, msg, None if t is None else int(t), sec))

    def failing_sections(self) -> List[int]:
        return sorted({i.section for i in self.errors if i.section is not None})


# ---------------------------------------------------------------- parsing

@dataclass
class ParsedObject:
    x: int
    y: int
    time: int
    kind: str
    new_combo: bool
    end_time: float = 0.0
    curve_type: str = ""
    points: list = field(default_factory=list)
    slides: int = 1
    length: float = 0.0
    line_no: int = 0


def split_sections(text: str):
    sections: Dict[str, List[str]] = {}
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        m = re.fullmatch(r"\[(\w+)\]", line)
        if m:
            cur = m.group(1)
            sections.setdefault(cur, [])
            continue
        if cur:
            sections[cur].append(line)
    return sections


def background_of(text: str) -> Optional[str]:
    """File name of the map's background image event (0,0,"name",x,y), if any."""
    for line in split_sections(text).get("Events", []):
        m = re.match(r'^(?:0|Background)\s*,\s*0\s*,\s*"?([^",]+?)"?\s*(?:,|$)', line)
        if m:
            return m.group(1)
    return None


def kv(lines: List[str]) -> Dict[str, str]:
    out = {}
    for l in lines:
        if ":" in l:
            k, v = l.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def parse_timing(lines, rep: ValidationReport):
    pts = []
    for l in lines:
        f = l.split(",")
        if len(f) < 8:
            rep.error("timing.fields", f"Timing point has {len(f)} fields (expected 8): {l}")
            continue
        try:
            t, bl = float(f[0]), float(f[1])
            meter, sset, sidx, vol, unin, fx = (int(x) for x in f[2:8])
        except ValueError:
            rep.error("timing.syntax", f"Unparseable timing point: {l}")
            continue
        if not math.isfinite(bl):
            rep.error("timing.value", f"Non-finite beat length: {l}", t)
            continue
        pts.append((t, bl, meter, vol, unin, fx))
    return pts


def parse_objects(lines, rep: ValidationReport) -> List[ParsedObject]:
    objs = []
    for n, l in enumerate(lines):
        f = l.split(",")
        try:
            x, y, t, typ, hs = int(f[0]), int(f[1]), int(f[2]), int(f[3]), int(f[4])
        except (ValueError, IndexError):
            rep.error("object.syntax", f"Unparseable hit object line {n + 1}: {l}")
            continue
        kinds = [k for bit, k in ((1, "circle"), (2, "slider"), (8, "spinner"), (128, "hold")) if typ & bit]
        if len(kinds) != 1 or kinds[0] == "hold":
            rep.error("object.type", f"Invalid object type {typ} on line {n + 1}", t)
            continue
        o = ParsedObject(x, y, t, kinds[0], bool(typ & 4), line_no=n + 1)
        if o.kind == "slider":
            try:
                curve = f[5].split("|")
                o.curve_type = curve[0]
                o.points = [(int(a), int(b)) for a, b in (p.split(":") for p in curve[1:])]
                o.slides = int(f[6])
                o.length = float(f[7])
            except (ValueError, IndexError):
                rep.error("slider.syntax", f"Unparseable slider on line {n + 1}: {l}", t)
                continue
            if o.curve_type not in ("L", "P", "B", "C"):
                rep.error("slider.curve", f"Unknown curve type '{o.curve_type}'", t)
            if not o.points:
                rep.error("slider.points", "Slider has no control points", t)
            if o.curve_type == "P" and len(o.points) != 2:
                rep.error("slider.points", "Perfect-circle slider must have exactly 2 control points", t)
            if not (1 <= o.slides <= 50):
                rep.error("slider.slides", f"Invalid slide count {o.slides}", t)
            if not (o.length > 0 and math.isfinite(o.length)):
                rep.error("slider.length", f"Invalid slider length {o.length}", t)
        elif o.kind == "spinner":
            try:
                o.end_time = float(int(f[5]))
            except (ValueError, IndexError):
                rep.error("spinner.syntax", f"Unparseable spinner on line {n + 1}", t)
                continue
            if o.end_time <= t:
                rep.error("spinner.duration", "Spinner ends before it starts", t)
        objs.append(o)
    return objs


def _timing_at(pts, t):
    red = [p for p in pts if p[4] == 1]
    beat = red[0][1]
    sv = 1.0
    for p in pts:
        if p[0] <= t + 0.5:
            if p[4] == 1:
                beat, sv = p[1], 1.0
            else:
                sv = -100.0 / p[1] if p[1] < 0 else 1.0
    return beat, sv


# ---------------------------------------------------------------- validation

def validate_text(text: str, sa: Optional[SongAnalysis] = None, audio_dir: Optional[Path] = None,
                  audio_duration_ms: Optional[float] = None) -> ValidationReport:
    rep = ValidationReport()
    try:
        text.encode("utf-8")
    except UnicodeError:
        rep.error("encoding", "File is not valid UTF-8")
    if not text.lstrip("﻿").startswith("osu file format v14"):
        rep.error("header", "Missing 'osu file format v14' header")
    secs = split_sections(text)
    for s in REQUIRED_SECTIONS:
        if s not in secs:
            rep.error("section.missing", f"Missing [{s}] section")
    if not rep.ok:
        return rep

    gen, meta, diff = kv(secs["General"]), kv(secs["Metadata"]), kv(secs["Difficulty"])
    audio_name = gen.get("AudioFilename", "")
    if not audio_name:
        rep.error("general.audio", "AudioFilename is empty")
    if gen.get("Mode", "0") != "0":
        rep.error("general.mode", "Mode is not osu!standard (0)")
    for k in ("Title", "Artist", "Creator", "Version"):
        if not meta.get(k):
            rep.error("metadata.missing", f"Metadata field {k} is empty")
        elif k in ("Title", "Artist") and not meta[k].isascii():
            rep.error("metadata.ascii", f"{k} must be ASCII (the Unicode form goes in {k}Unicode)")
    ranges = {"HPDrainRate": (0, 10), "CircleSize": (0, 10), "OverallDifficulty": (0, 10),
              "ApproachRate": (0, 10), "SliderMultiplier": (0.4, 3.6), "SliderTickRate": (0.5, 8)}
    dvals = {}
    for k, (lo, hi) in ranges.items():
        try:
            v = float(diff[k])
            dvals[k] = v
            if not (lo <= v <= hi):
                rep.error("difficulty.range", f"{k}={v} outside [{lo}, {hi}]")
        except (KeyError, ValueError):
            rep.error("difficulty.missing", f"Difficulty field {k} missing or invalid")
    if audio_dir is not None and audio_name and not (Path(audio_dir) / audio_name).is_file():
        rep.error("audio.missing", f"Audio file '{audio_name}' not found next to the map")
    bg = background_of(text)
    if bg is not None:
        if Path(bg).name != bg or not bg.lower().endswith((".jpg", ".jpeg", ".png")):
            rep.error("background.name", f"Background '{bg}' must be a .jpg/.png file next to the map")
        elif audio_dir is not None and not (Path(audio_dir) / bg).is_file():
            rep.error("background.missing", f"Background image '{bg}' not found next to the map")

    pts = parse_timing(secs["TimingPoints"], rep)
    red = [p for p in pts if p[4] == 1]
    if not red:
        rep.error("timing.none", "No uninherited (red) timing point")
        return rep
    for a, b in zip(pts[:-1], pts[1:]):
        if b[0] < a[0]:
            rep.error("timing.order", "Timing points are not in time order", b[0])
    for p in red:
        if p[1] <= 0:
            rep.error("timing.beatlength", f"Red line with non-positive beat length {p[1]}", p[0])
        elif not (60000 / 1000 <= 60000 / p[1] <= 1000):
            rep.warn("timing.bpm", f"Unusual BPM {60000 / p[1]:.1f}", p[0])
    red_times = Counter(int(p[0]) for p in red)
    for t, c in red_times.items():
        if c > 1:
            rep.error("timing.duplicate", "Two red lines at the same time", t)
    for p in pts:
        if p[4] == 0 and p[1] >= 0:
            rep.error("timing.inherited", f"Inherited point with non-negative value {p[1]}", p[0])

    objs = parse_objects(secs["HitObjects"], rep)
    if not objs:
        rep.error("objects.none", "The map has no hit objects")
        return rep
    if not objs[0].new_combo:
        rep.warn("combo.first", "First object does not start a new combo", objs[0].time)
    sm = dvals.get("SliderMultiplier", 1.4)
    duration = audio_duration_ms if audio_duration_ms else (sa.audio.duration_ms if sa else None)

    # slider end times and geometry
    for o in objs:
        if not (0 <= o.x <= 512 and 0 <= o.y <= 384):
            rep.error("object.bounds", f"Object outside playfield ({o.x},{o.y})", o.time,
                      _section_of(sa, o.time))
        if o.kind == "slider" and o.points:
            beat, sv = _timing_at(pts, o.time)
            span = o.length / (sm * 100.0 * sv) * beat
            o.end_time = o.time + span * o.slides
            ctype = o.curve_type if o.curve_type in ("L", "P", "B") else "B"
            path = curves.sample_path(ctype, [(o.x, o.y)] + o.points, o.length)
            if not curves.in_bounds(path, margin=-8):
                rep.error("slider.bounds", "Slider path leaves the playfield", o.time, _section_of(sa, o.time))
            if span < 20:
                rep.error("slider.short", f"Slider span {span:.0f} ms is implausibly short", o.time)
        elif o.kind == "circle":
            o.end_time = o.time
        if duration is not None and max(o.end_time, o.time) > duration:
            rep.error("object.after_audio", "Object ends after the audio does", o.time, _section_of(sa, o.time))
        if o.time < 0:
            rep.error("object.negative", "Object before the start of the audio", o.time)

    for a, b in zip(objs[:-1], objs[1:]):
        if b.time <= a.time:
            rep.error("object.order", "Objects not strictly increasing in time (duplicate or unsorted)", b.time,
                      _section_of(sa, b.time))
        elif b.time < max(a.end_time, a.time) + 10:
            rep.error("object.overlap", "Object starts before the previous one has finished", b.time,
                      _section_of(sa, b.time))
        elif b.time - max(a.end_time, a.time) < 30:
            rep.error("object.too_close", "Objects less than 30 ms apart", b.time, _section_of(sa, b.time))
    if red[0][0] > objs[0].time + 1:
        rep.warn("timing.first", "First object is before the first timing point", objs[0].time)

    rep.metrics["objects"] = len(objs)
    rep.metrics["first_object_ms"] = objs[0].time
    rep.metrics["last_object_end_ms"] = max(max(o.end_time, o.time) for o in objs)
    if sa is not None:
        _coverage(rep, objs, sa)
        _quality(rep, objs, sa, pts, sm)
    return rep


def _section_of(sa: Optional[SongAnalysis], t: float) -> Optional[int]:
    if sa is None:
        return None
    return sa.section_at(t).index


def _coverage(rep: ValidationReport, objs: List[ParsedObject], sa: SongAnalysis):
    spans = [(o.time, max(o.end_time, o.time)) for o in objs]
    starts = np.array([s for s, _ in spans])
    ends = np.array([e for _, e in spans])
    total = covered = 0.0
    for s in sa.sections:
        if s.is_break:
            continue
        beat = sa.timing_at(s.start_ms).beat_ms
        win = beat * 4
        lo, hi = max(s.start_ms, sa.music_start_ms), min(s.end_ms, sa.music_end_ms)
        sec_objs = int(((starts >= lo - 5) & (starts < hi)).sum())
        if hi - lo >= 2 * win and sec_objs == 0:
            rep.error("coverage.empty_section", f"{s.label} section {lo / 1000:.1f}-{hi / 1000:.1f}s has no objects",
                      lo, s.index)
        t = lo
        while t < hi:
            w_end = min(hi, t + win)
            frac = (w_end - t)
            total += frac
            if np.any((starts < w_end + 1) & (ends >= t - 1)):
                covered += frac
            t += win
    pct = covered / total * 100 if total else 0.0
    rep.metrics["coverage_pct"] = round(pct, 1)
    mapped_end = float(ends.max())
    last_strong = max((o.time_ms for o in sa.onsets if o.strength > 0.35 and o.time_ms <= sa.music_end_ms),
                      default=sa.music_end_ms)
    beat = sa.timing_at(last_strong).beat_ms
    rep.metrics["music_start_ms"] = round(sa.music_start_ms)
    rep.metrics["music_end_ms"] = round(sa.music_end_ms)
    rep.metrics["last_strong_onset_ms"] = round(last_strong)
    if pct < 90:
        rep.error("coverage.low", f"Only {pct:.0f}% of the music (outside breaks) is mapped")
    elif pct < 97:
        rep.warn("coverage.partial", f"{pct:.0f}% of the music (outside breaks) is mapped")
    if mapped_end < last_strong - 8 * beat:
        rep.error("coverage.ends_early", f"Map ends at {mapped_end / 1000:.1f}s but music continues to "
                                         f"{last_strong / 1000:.1f}s", mapped_end, sa.sections[-1].index)
    first_music = next((s for s in sa.sections if not s.is_break), sa.sections[0])
    if starts.min() > max(sa.music_start_ms, first_music.start_ms) + max(8 * beat, 6000):
        rep.warn("coverage.late_start", f"First object at {starts.min() / 1000:.1f}s; music starts at "
                                        f"{sa.music_start_ms / 1000:.1f}s", starts.min())
    if mapped_end > sa.music_end_ms + 2 * beat:
        rep.warn("coverage.after_music", "Objects continue after the music has ended", mapped_end)


def _quality(rep: ValidationReport, objs: List[ParsedObject], sa: SongAnalysis, pts, sm: float):
    ticks = np.array([g.time_ms for g in sa.ticks])
    on_grid = supported = 0
    support_flags = []
    for o in objs:
        i = int(np.clip(np.searchsorted(ticks, o.time), 1, len(ticks) - 1)) if len(ticks) > 1 else 0
        j = i if abs(ticks[i] - o.time) < abs(ticks[i - 1] - o.time) else i - 1
        if abs(ticks[j] - o.time) <= 2.0:
            on_grid += 1
        g = sa.ticks[j]
        sup = g.onset > 0.2 or g.metric >= 0.65 or g.sustain > 0.5
        supported += sup
        support_flags.append(sup)
    n = len(objs)
    rep.metrics["on_grid_pct"] = round(on_grid / n * 100, 1)
    rep.metrics["music_supported_pct"] = round(supported / n * 100, 1)
    if on_grid / n < 0.98:
        rep.error("rhythm.off_grid", f"Only {on_grid / n * 100:.0f}% of objects are snapped to the beat grid")
    if supported / n < 0.7:
        rep.warn("rhythm.unsupported", f"Only {supported / n * 100:.0f}% of objects coincide with audible "
                                       "onsets or strong beats")

    # repetition: identical 8-object movement signatures
    sigs = []
    for k in range(0, n - 8, 4):
        win = objs[k:k + 8]
        sig = tuple((round((b.x - a.x) / 16), round((b.y - a.y) / 16), b.kind) for a, b in zip(win[:-1], win[1:]))
        sigs.append(sig)
    if sigs:
        c = Counter(sigs)
        rep_frac = sum(v for v in c.values() if v > 1) / len(sigs)
        rep.metrics["repeated_pattern_pct"] = round(rep_frac * 100, 1)
        if rep_frac > 0.3:
            rep.warn("quality.repetitive", f"{rep_frac * 100:.0f}% of 8-note windows repeat exactly")

    # spacing outliers
    fast = 0
    for a, b in zip(objs[:-1], objs[1:]):
        end_x, end_y = (a.x, a.y)
        if a.kind == "slider" and a.points:
            path = curves.sample_path(a.curve_type if a.curve_type in "LPB" else "B",
                                      [(a.x, a.y)] + a.points, a.length)
            end = path[-1] if a.slides % 2 == 1 else path[0]
            end_x, end_y = end
        gap = b.time - max(a.end_time, a.time)
        if gap > 0 and math.hypot(b.x - end_x, b.y - end_y) / gap > 4.0:
            fast += 1
    rep.metrics["extreme_jumps"] = fast
    if fast > max(3, 0.02 * n):
        rep.warn("quality.extreme_spacing", f"{fast} jumps exceed 4 px/ms")

    # density vs intensity per section
    dens = {}
    for s in sa.sections:
        if s.is_break:
            continue
        beats = (s.end_ms - s.start_ms) / sa.timing_at(s.start_ms).beat_ms
        cnt = sum(1 for o in objs if s.start_ms <= o.time < s.end_ms)
        if beats >= 8:
            dens[s.index] = (s.intensity, cnt / beats)
    if dens:
        loud = [d for i, d in dens.values() if i >= 0.7]
        calm = [(k, d) for k, (i, d) in dens.items() if i < 0.4]
        if loud:
            for k, d in calm:
                if d > 1.5 * max(loud) and d > 1.0:
                    rep.warn("quality.density", f"Calm section {k} is denser than the intense sections",
                             sa.sections[k].start_ms, k)
        ordered = sorted(dens.items())
        for (k1, (i1, d1)), (k2, (i2, d2)) in zip(ordered[:-1], ordered[1:]):
            if min(d1, d2) > 0 and max(d1, d2) / min(d1, d2) > 4 and abs(i1 - i2) < 0.2:
                rep.warn("quality.density_jump", f"Density changes {max(d1, d2) / min(d1, d2):.1f}x between "
                                                 f"sections {k1} and {k2} without a matching change in the music",
                         sa.sections[k2].start_ms, k2)
    rep.metrics["section_density"] = {str(k): round(d, 2) for k, (_, d) in dens.items()}


def validate_osz(osz_path: Path, osu_name, osu_bytes: Optional[bytes], audio_name: str) -> ValidationReport:
    """Check the package. osu_name is one file name (with osu_bytes), or a {name: bytes} dict of every
    difficulty expected in a mapset (osu_bytes is then ignored). Every .osu inside is checked."""
    rep = ValidationReport()
    expected = dict(osu_name) if isinstance(osu_name, dict) else {osu_name: osu_bytes}
    try:
        with zipfile.ZipFile(osz_path) as z:
            bad = z.testzip()
            if bad:
                rep.error("osz.corrupt", f"Corrupt entry in package: {bad}")
            names = z.namelist()
            for name, data in expected.items():
                if name not in names:
                    rep.error("osz.osu_missing", f"{name} missing from package")
                elif z.read(name) != data:
                    rep.error("osz.osu_mismatch", f"Packaged {name} differs from the exported file")
            versions: Dict[str, str] = {}
            for name in names:
                if not name.lower().endswith(".osu"):
                    continue
                if name not in expected:
                    rep.error("osz.osu_unexpected", f"Unexpected .osu in package: {name}")
                text = z.read(name).decode("utf-8", errors="replace")
                if not text.lstrip("﻿").startswith("osu file format v14"):
                    rep.error("osz.osu_header", f"{name} has no 'osu file format v14' header")
                    continue
                meta = kv(split_sections(text).get("Metadata", []))
                ver = meta.get("Version", "")
                if ver in versions:
                    rep.error("osz.version_duplicate",
                              f"{name} and {versions[ver]} share the difficulty name '{ver}'")
                versions[ver] = name
                gen = kv(split_sections(text).get("General", []))
                if gen.get("AudioFilename", "") != audio_name:
                    rep.error("osz.audio_ref", f"{name} does not reference the packaged audio '{audio_name}'")
                bg = background_of(text)
                if bg is not None and bg not in names:
                    rep.error("osz.background_missing", f"{name} references background '{bg}', "
                                                        "which is not in the package")
            if not versions:
                rep.error("osz.no_osu", "Package contains no .osu file")
            if audio_name not in names:
                rep.error("osz.audio_missing", f"Audio '{audio_name}' missing from package")
            elif z.getinfo(audio_name).file_size < 1024:
                rep.error("osz.audio_small", "Packaged audio file is suspiciously small")
    except zipfile.BadZipFile as e:
        rep.error("osz.invalid", f"Package is not a valid zip: {e}")
    return rep
