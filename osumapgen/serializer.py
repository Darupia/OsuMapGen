"""Deterministic .osu (file format v14) writer."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List

from .model import GeneratedMap, HitObject, SongAnalysis

COMBO_COLOURS = [(255, 128, 64), (72, 160, 255), (120, 220, 110), (240, 90, 160)]


@dataclass
class Metadata:
    title: str
    artist: str
    creator: str = "OsuMapGen"
    version: str = "Generated"
    source: str = ""
    tags: str = "osumapgen generated"


def ascii_fallback(s: str) -> str:
    a = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    a = re.sub(r"\s+", " ", a).strip()
    return a


def clean_field(s: str) -> str:
    return re.sub(r"[\r\n]+", " ", s or "").strip()


def _fmt(v: float) -> str:
    s = f"{v:.12g}"
    return s


def timing_lines(sa: SongAnalysis, m: GeneratedMap) -> List[str]:
    """Red lines for every timing section plus green lines (volume/kiai) at section changes."""
    entries = []
    for ts in sa.timing:
        entries.append((int(round(ts.offset_ms)), 0,
                        f"{int(round(ts.offset_ms))},{_fmt(ts.beat_ms)},{ts.meter},2,0,{{vol}},1,{{fx}}"))
    lines: List[str] = []
    greens = sorted(m.green_lines)

    def state_at(t):
        vol, kiai = 60, False
        for gt, _, gv, gk in greens:
            if gt <= t:
                vol, kiai = gv, gk
        return vol, kiai

    events = sorted([(t, 0, s) for t, _, s in entries] + [(gt, 1, (sv, gv, gk)) for gt, sv, gv, gk in greens],
                    key=lambda e: (e[0], e[1]))
    for t, kind, payload in events:
        vol, kiai = state_at(t)
        if kind == 0:
            lines.append(payload.format(vol=vol, fx=1 if kiai else 0))
        else:
            sv, gv, gk = payload
            lines.append(f"{t},{_fmt(-100.0 / sv)},4,2,0,{gv},0,{1 if gk else 0}")
    return lines


def hitobject_line(o: HitObject) -> str:
    combo = 4 if o.new_combo else 0
    if o.kind == "circle":
        return f"{o.x},{o.y},{o.time_ms},{1 | combo},{o.hitsound},0:0:0:0:"
    if o.kind == "slider":
        pts = "|".join(f"{x}:{y}" for x, y in o.curve_points)
        edge_sounds = "|".join([str(o.hitsound)] + ["0"] * o.slides)
        edge_sets = "|".join(["0:0"] * (o.slides + 1))
        return (f"{o.x},{o.y},{o.time_ms},{2 | combo},{o.hitsound},{o.curve_type}|{pts},"
                f"{o.slides},{_fmt(round(o.length, 4))},{edge_sounds},{edge_sets},0:0:0:0:")
    if o.kind == "spinner":
        return f"256,192,{o.time_ms},{8 | 4},{o.hitsound},{o.end_time_ms},0:0:0:0:"
    raise ValueError(f"unknown object kind {o.kind}")


def serialize(sa: SongAnalysis, m: GeneratedMap, meta: Metadata, audio_filename: str,
              lead_in_ms: int = 0) -> str:
    d = m.difficulty
    title_u = clean_field(meta.title) or "Unknown Title"
    artist_u = clean_field(meta.artist) or "Unknown Artist"
    title = ascii_fallback(title_u) or "Unknown Title"
    artist = ascii_fallback(artist_u) or "Unknown Artist"
    out: List[str] = ["osu file format v14", ""]
    out += ["[General]",
            f"AudioFilename: {audio_filename}",
            f"AudioLeadIn: {int(lead_in_ms)}",
            f"PreviewTime: {int(m.preview_ms)}",
            "Countdown: 0",
            "SampleSet: Soft",
            "StackLeniency: 0.7",
            "Mode: 0",
            "LetterboxInBreaks: 0",
            "WidescreenStoryboard: 0",
            ""]
    out += ["[Editor]",
            "DistanceSpacing: 1",
            f"BeatDivisor: {m.beat_divisor}",
            "GridSize: 32",
            "TimelineZoom: 1",
            ""]
    out += ["[Metadata]",
            f"Title:{title}",
            f"TitleUnicode:{title_u}",
            f"Artist:{artist}",
            f"ArtistUnicode:{artist_u}",
            f"Creator:{clean_field(meta.creator) or 'OsuMapGen'}",
            f"Version:{clean_field(meta.version) or 'Generated'}",
            f"Source:{clean_field(meta.source)}",
            f"Tags:{clean_field(meta.tags)}",
            "BeatmapID:0",
            "BeatmapSetID:-1",
            ""]
    out += ["[Difficulty]",
            f"HPDrainRate:{_fmt(d.hp)}",
            f"CircleSize:{_fmt(d.cs)}",
            f"OverallDifficulty:{_fmt(d.od)}",
            f"ApproachRate:{_fmt(d.ar)}",
            f"SliderMultiplier:{_fmt(d.slider_multiplier)}",
            f"SliderTickRate:{_fmt(d.slider_tick_rate)}",
            ""]
    out += ["[Events]",
            "//Background and Video events",
            "//Break Periods"]
    out += [f"2,{a},{b}" for a, b in m.breaks]
    out += ["//Storyboard Layer 0 (Background)",
            "//Storyboard Layer 1 (Fail)",
            "//Storyboard Layer 2 (Pass)",
            "//Storyboard Layer 3 (Foreground)",
            "//Storyboard Sound Samples",
            ""]
    out += ["[TimingPoints]"] + timing_lines(sa, m) + ["", ""]
    out += ["[Colours]"] + [f"Combo{i + 1} : {r},{g},{b}" for i, (r, g, b) in enumerate(COMBO_COLOURS)] + [""]
    out += ["[HitObjects]"] + [hitobject_line(o) for o in m.objects]
    return "\r\n".join(out) + "\r\n"


def safe_filename(s: str, limit: int = 120) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s).strip().rstrip(".")
    return (s or "map")[:limit]


def osu_filename(meta: Metadata) -> str:
    artist = ascii_fallback(clean_field(meta.artist)) or "Unknown Artist"
    title = ascii_fallback(clean_field(meta.title)) or "Unknown Title"
    return safe_filename(f"{artist} - {title} ({meta.creator}) [{meta.version}]", 200) + ".osu"
