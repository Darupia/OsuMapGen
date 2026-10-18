"""End-to-end generation: analyse -> refine to target stars -> validate -> export."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__, analysis, generator, packaging, serializer, star_rating, validator
from .infra import Cancelled, Progress, UserFacingError, check_username, get_logger
from .model import GeneratedMap, SongAnalysis
from .params import KNOB_MAX, STYLE_KEYS, initial_knob, resolve_style
from .placement import preempt_ms

log = get_logger("pipeline")

MAX_SEARCH_ITERS = 12
MAX_REPAIR_ATTEMPTS = 3
STYLE_NAMES = {"simple": "Simple", "stream": "Streams", "jump": "Jumps", "tech": "Technical",
               "slider": "Sliders", "balanced": "Balanced", "mix": "Mixed"}


@dataclass
class GenerationRequest:
    mp3_path: str
    stars: float
    style: str = "Auto"
    output_dir: str = ""
    title: Optional[str] = None
    artist: Optional[str] = None
    tolerance: float = 0.5
    offset_ms: float = 0.0
    creator: Optional[str] = None     # the player's osu! username, exactly as on their profile


@dataclass
class GenerationResult:
    ok: bool
    message: str
    requested_stars: float
    estimated_stars: Optional[float] = None
    estimated_stars_stable: Optional[float] = None
    within_tolerance: bool = False
    output_folder: Optional[str] = None
    osu_path: Optional[str] = None
    osz_path: Optional[str] = None
    report_path: Optional[str] = None
    duration_s: float = 0.0
    coverage_pct: Optional[float] = None
    style_used: str = ""
    style_breakdown: str = ""          # Balanced mix: which preset each section got
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timeline: List[Tuple[float, int]] = field(default_factory=list)   # (time_s, objects per bar) for preview


# ---------------------------------------------------------------- metadata

def resolve_metadata(sa: SongAnalysis, req: GenerationRequest) -> Tuple[str, str]:
    title = (req.title or "").strip() or (sa.audio.title or "")
    artist = (req.artist or "").strip() or (sa.audio.artist or "")
    if not title or not artist:
        stem = Path(req.mp3_path).stem
        stem = re.sub(r"[_]+", " ", stem).strip()
        m = re.match(r"^\s*(.+?)\s+-\s+(.+?)\s*$", stem)
        if m:
            artist = artist or m.group(1)
            title = title or m.group(2)
        else:
            title = title or stem
    return title or "Unknown Title", artist or "Unknown Artist"


# ---------------------------------------------------------------- star search

@dataclass
class Candidate:
    knob: float
    stars: float
    stars_stable: float
    gmap: GeneratedMap
    text: str


def _evaluate(sa, stars_target, style_key, knob, seed, attempts, meta, audio_name) -> Candidate:
    m = generator.generate(sa, stars_target, style_key, knob, seed, attempts)
    lead = _lead_in(m)
    text = serializer.serialize(sa, m, meta, audio_name, lead)
    sr = star_rating.calculate(text)
    return Candidate(knob, sr.stars, sr.stars_stable, m, text)


def _lead_in(m: GeneratedMap) -> int:
    if not m.objects:
        return 0
    need = preempt_ms(m.difficulty.ar) + 600 - m.objects[0].time_ms
    return int(max(0, round(need / 100.0) * 100))


def search_knob(sa, target, style_key, seed, meta, audio_name, progress: Progress, tol: float):
    history: List[Candidate] = []
    lo, hi = 0.0, KNOB_MAX
    knob = initial_knob(target)
    best: Optional[Candidate] = None
    for it in range(MAX_SEARCH_ITERS):
        progress.update("generate", it / MAX_SEARCH_ITERS,
                        f"Generating and rating map (attempt {it + 1}/{MAX_SEARCH_ITERS})")
        c = _evaluate(sa, target, style_key, knob, seed, {}, meta, audio_name)
        history.append(c)
        log.info("search it=%d knob=%.3f stars=%.3f objects=%d", it, knob, c.stars, len(c.gmap.objects))
        if best is None or abs(c.stars - target) < abs(best.stars - target):
            best = c
        if abs(c.stars - target) <= min(0.08, tol / 4):
            break
        if c.stars < target:
            lo = knob
        else:
            hi = knob
        if hi - lo < 0.004:
            break
        # interpolate inside the bracket when both ends have been measured, else bisect
        below = [h for h in history if h.knob == lo]
        above = [h for h in history if h.knob == hi]
        if below and above and above[0].stars > below[0].stars:
            f = (target - below[0].stars) / (above[0].stars - below[0].stars)
            knob = lo + (hi - lo) * min(0.85, max(0.15, f))
        else:
            knob = (lo + hi) / 2
    progress.update("generate", 1.0, f"Estimated {best.stars:.2f} stars")
    return best, history


# ---------------------------------------------------------------- main entry

def run(req: GenerationRequest, progress: Optional[Progress] = None) -> GenerationResult:
    progress = progress or Progress()
    progress.plan([("decode", 8), ("features", 14), ("timing", 10), ("structure", 6),
                   ("generate", 45), ("validate", 7), ("package", 10)])
    t0 = time.time()
    target = float(req.stars)
    res = GenerationResult(ok=False, message="", requested_stars=target)
    if not (0.5 <= target <= 12.0):
        raise UserFacingError("Please enter a star rating between 0.5 and 12.")
    creator = req.creator or ""
    if creator and check_username(creator):
        raise UserFacingError(f"osu! username '{creator}': {check_username(creator)}")

    sa = analysis.analyse(req.mp3_path, progress, offset_ms=req.offset_ms)
    res.warnings.extend(sa.warnings)
    title, artist = resolve_metadata(sa, req)
    style_key = resolve_style(req.style, sa, target)
    res.style_used = STYLE_NAMES.get(style_key, style_key)
    version = f"Generated {target:.1f} Stars - {res.style_used}"
    meta =serializer.Metadata(title=title, artist=artist, version=version, creator=creator or "OsuMapGen",
                               tags=f"osumapgen generated {res.style_used.lower()}")
    if not creator:
        res.warnings.append("No osu! username set: the map's creator is 'OsuMapGen'. Set your username "
                            "(case-sensitive) if you want to upload it.")
    audio_name = packaging.audio_filename(req.mp3_path)
    seed = int(sa.content_hash[:8], 16)

    progress.check()
    best, history = search_knob(sa, target, style_key, seed, meta, audio_name, progress, req.tolerance)

    # ---- validation with bounded, section-targeted regeneration
    attempts: Dict[int, int] = {}
    cand = best
    rep = None
    for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
        progress.update("validate", attempt / (MAX_REPAIR_ATTEMPTS + 1), "Validating map")
        rep = validator.validate_text(cand.text, sa, audio_duration_ms=sa.audio.duration_ms)
        if rep.ok:
            break
        bad = rep.failing_sections()
        log.warning("Validation attempt %d failed: %s", attempt, [str(i) for i in rep.errors[:10]])
        if attempt == MAX_REPAIR_ATTEMPTS or not bad:
            break
        for s in bad:
            attempts[s] = attempts.get(s, 0) + 1
        cand = _evaluate(sa, target, style_key, cand.knob, seed, attempts, meta, audio_name)
    progress.update("validate", 1.0, "Validation finished")

    res.estimated_stars = round(cand.stars, 2)
    res.estimated_stars_stable = round(cand.stars_stable, 2)
    res.within_tolerance = abs(cand.stars - target) <= req.tolerance
    res.coverage_pct = rep.metrics.get("coverage_pct") if rep else None
    if not res.within_tolerance:
        res.warnings.append(_star_explanation(target, cand, history))
    res.warnings.extend(str(i) for i in rep.warnings)
    res.timeline = _timeline(sa, cand.gmap)
    styles = cand.gmap.stats.get("section_styles") or {}
    if styles:
        parts = []
        for s in sa.sections:
            if s.index in styles:
                t = max(0.0, s.start_ms) / 1000
                parts.append(f"{int(t // 60)}:{int(t % 60):02d} {STYLE_NAMES.get(styles[s.index])}")
        res.style_breakdown = "Styles by section: " + ", ".join(parts)

    # ---- export
    progress.update("package", 0.0, "Writing files")
    base = Path(req.output_dir) if req.output_dir else Path.home() / "Documents" / "OsuMapGen Output"
    folder = packaging.make_output_folder(base, artist, title, target, res.style_used)
    res.output_folder = str(folder)
    osu_name = serializer.osu_filename(meta)
    if len(str((folder / osu_name).resolve())) > 240:      # stay below Windows' MAX_PATH
        osu_name = serializer.safe_filename(f"{packaging.ascii_fallback(title)[:40]} [{version}]") + ".osu"
        if len(str((folder / osu_name).resolve())) > 240:
            osu_name = "map.osu"
    osu_bytes = cand.text.encode("utf-8")
    report_payload = _report_payload(req, res, sa, cand, history, rep, meta, style_key, time.time() - t0)
    if not rep.ok:
        # never present an invalid map as complete: keep the draft for diagnosis only
        (folder / ("INVALID DRAFT - " + osu_name)).write_bytes(osu_bytes)
        res.errors = [str(i) for i in rep.errors]
        res.message = ("The generated map failed validation after "
                       f"{MAX_REPAIR_ATTEMPTS} repair attempts; no .osz was created. See the report.")
        res.report_path = str(_write_report(folder, report_payload, res))
        return res

    packaging.copy_audio(req.mp3_path, folder)
    (folder / osu_name).write_bytes(osu_bytes)
    progress.update("package", 0.4, "Packaging .osz")
    osz_name = serializer.safe_filename(f"{packaging.ascii_fallback(artist) or 'Unknown Artist'} - "
                                        f"{packaging.ascii_fallback(title) or 'Unknown Title'} "
                                        f"({target:.1f} stars)", 150) + ".osz"
    if len(str((folder / osz_name).resolve())) > 240:
        osz_name = "map.osz"
    osz = packaging.build_osz(folder, osu_name, audio_name, osz_name)
    vrep = validator.validate_text((folder / osu_name).read_bytes().decode("utf-8"), sa, audio_dir=folder,
                                   audio_duration_ms=sa.audio.duration_ms)
    orep = validator.validate_osz(osz, osu_name, osu_bytes, audio_name)
    if not (vrep.ok and orep.ok):
        res.errors = [str(i) for i in vrep.errors + orep.errors]
        res.message = "Exported files failed their final check; see the report."
        osz.unlink(missing_ok=True)
        res.report_path = str(_write_report(folder, report_payload, res))
        return res
    res.osu_path = str(folder / osu_name)
    res.osz_path = str(osz)
    res.duration_s = round(time.time() - t0, 1)
    report_payload["elapsed_s"] = res.duration_s
    res.ok = True
    res.message = (f"Done: estimated {res.estimated_stars:.2f} stars (requested {target:.2f}), "
                   f"{len(cand.gmap.objects)} objects, {res.coverage_pct:.0f}% of the music mapped.")
    res.report_path = str(_write_report(folder, report_payload, res))
    progress.update("package", 1.0, "Finished")
    return res


def _star_explanation(target: float, cand: Candidate, history: List[Candidate]) -> str:
    lo = min(h.stars for h in history)
    hi = max(h.stars for h in history)
    if target > cand.stars:
        return (f"Requested {target:.2f} stars, but the closest musically reasonable map rates {cand.stars:.2f}. "
                f"The densest/widest version tried rated {hi:.2f}: this song's tempo and rhythm do not support more "
                "difficulty without artificial density or unreasonable spacing, so quality was kept.")
    return (f"Requested {target:.2f} stars, but the simplest version of this song still rates {lo:.2f} "
            "(its tempo makes even sparse rhythm harder than the target). The easiest readable map was kept.")


def _timeline(sa: SongAnalysis, m: GeneratedMap) -> List[Tuple[float, int]]:
    if not m.objects:
        return []
    bins: Dict[int, int] = {}
    for o in m.objects:
        k = int(o.time_ms // 2000)
        bins[k] = bins.get(k, 0) + 1
    n = int(sa.audio.duration_ms // 2000) + 1
    return [(k * 2.0, bins.get(k, 0)) for k in range(n)]


def _report_payload(req, res, sa, cand: Candidate, history, rep, meta, style_key, elapsed) -> dict:
    client = packaging.osu_client_name()
    return {
        "generator": f"OsuMapGen {__version__}",
        "input": str(req.mp3_path),
        "metadata": {"title": meta.title, "artist": meta.artist, "version": meta.version, "creator": meta.creator,
                     "title_source": "user" if req.title else ("id3" if sa.audio.title else "filename"),
                     "artist_source": "user" if req.artist else ("id3" if sa.audio.artist else
                                                                 "filename/unknown")},
        "stars": {
            "requested": req.stars,
            "estimated_lazer": round(cand.stars, 3),
            "estimated_stable": round(cand.stars_stable, 3),
            "calculator": star_rating.calculator_version(),
            "tolerance": req.tolerance,
            "within_tolerance": abs(cand.stars - req.stars) <= req.tolerance,
            "installed_client": client or "not found",
            "client_rating": "Not read automatically: open the map in osu! to see the client's own rating.",
            "search": [{"knob": round(h.knob, 4), "stars": round(h.stars, 3), "objects": len(h.gmap.objects)}
                       for h in history],
        },
        "style": {"requested": req.style, "used": style_key},
        "difficulty_settings": asdict(cand.gmap.difficulty),
        "audio": {"duration_s": round(sa.audio.duration_ms / 1000, 2),
                  "analysed_s": round(sa.analysed_ms / 1000, 2),
                  "analysed_pct": round(min(100.0, sa.analysed_ms / sa.audio.duration_ms * 100), 1),
                  "sample_rate": sa.audio.sample_rate, "channels": sa.audio.channels,
                  "bitrate_kbps": sa.audio.bitrate_kbps, "decoder": sa.audio.decoder},
        "analysis": sa.summary(),
        "map": dict(cand.gmap.stats, breaks=cand.gmap.breaks, knob=round(cand.knob, 4)),
        "validation": {"ok": rep.ok, "metrics": rep.metrics,
                       "errors": [str(i) for i in rep.errors], "warnings": [str(i) for i in rep.warnings]},
        "elapsed_s": round(elapsed, 1),
    }


def _write_report(folder: Path, payload: dict, res: GenerationResult) -> Path:
    payload["result"] = {"ok": res.ok, "message": res.message, "warnings": res.warnings, "errors": res.errors}
    (folder / "report.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    s = payload["stars"]
    a = payload["audio"]
    an = payload["analysis"]
    v = payload["validation"]
    lines = [
        f"OsuMapGen generation report ({payload['generator']})",
        "=" * 60,
        f"Status:              {'COMPLETE' if res.ok else 'FAILED'} - {res.message}",
        f"Input:               {payload['input']}",
        f"Title / Artist:      {payload['metadata']['title']} / {payload['metadata']['artist']}"
        f"  (from {payload['metadata']['title_source']} / {payload['metadata']['artist_source']})",
        f"Creator:             {payload['metadata']['creator']}",
        "",
        "Star rating",
        f"  Requested:                 {s['requested']:.2f}",
        f"  Estimated (lazer algo):    {s['estimated_lazer']:.2f}   [{s['calculator']}]",
        f"  Estimated (stable algo):   {s['estimated_stable']:.2f}",
        f"  Within +/-{s['tolerance']}:          {'yes' if s['within_tolerance'] else 'NO'}",
        f"  Installed osu! client:     {s['installed_client']}",
        f"  Client's own rating:       {s['client_rating']}",
        "",
        "Audio",
        f"  Duration:     {a['duration_s']:.1f}s   analysed: {a['analysed_s']:.1f}s ({a['analysed_pct']:.0f}%)",
        f"  Music span:   {an['music_start_ms'] / 1000:.1f}s - {an['music_end_ms'] / 1000:.1f}s",
        f"  Decoder:      {a['decoder']}, {a['sample_rate']} Hz, {a['channels']} ch, {a['bitrate_kbps']} kbps",
        f"  Timing:       " + "; ".join(f"{t['bpm']} BPM @ {t['offset_ms']}ms (conf {t['confidence']})"
                                         for t in an["timing"]),
        "",
        "Sections",
    ]
    m = payload["map"]
    sec_styles = m.get("section_styles") or {}
    for i, sec in enumerate(an["sections"]):
        st = sec_styles.get(i) or sec_styles.get(str(i))
        lines.append(f"  {sec['start_ms'] / 1000:7.1f}s - {sec['end_ms'] / 1000:7.1f}s  {sec['label']:<10}"
                     f" intensity {sec['intensity']:.2f}{'  kiai' if sec['kiai'] else ''}"
                     f"{f'  style: {STYLE_NAMES.get(st, st)}' if st else ''}")
    lines += ["",
              "Map",
              f"  Objects: {m.get('objects')} (circles {m.get('circles')}, sliders {m.get('sliders')}, "
              f"spinners {m.get('spinners')}, stream notes {m.get('stream_notes')})",
              f"  Breaks:  {len(m.get('breaks', []))}",
              f"  Settings: " + ", ".join(f"{k}={v}" for k, v in payload["difficulty_settings"].items()),
              "",
              "Validation",
              f"  Passed: {'yes' if v['ok'] else 'NO'}",
              "  " + ", ".join(f"{k}={val}" for k, val in v["metrics"].items() if k != "section_density")]
    if res.errors:
        lines += ["", "Errors"] + [f"  - {e}" for e in res.errors]
    if res.warnings:
        lines += ["", "Warnings"] + [f"  - {w}" for w in res.warnings]
    lines += ["", "Star-rating search"] + [f"  knob {h['knob']:.3f} -> {h['stars']:.2f} stars ({h['objects']} objects)"
                                           for h in s["search"]]
    p = folder / "report.txt"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
