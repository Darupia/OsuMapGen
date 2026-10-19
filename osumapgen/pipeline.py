"""End-to-end generation: analyse -> refine to target stars -> validate -> export."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import __version__, analysis, audio_io, generator, packaging, preview, serializer, star_rating, validator
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
    mapset: bool = False              # several difficulties (Easy up to `stars`) in one .osz


@dataclass
class DifficultyResult:
    """One difficulty of a full mapset."""
    version: str
    requested_stars: float
    estimated_stars: float
    estimated_stars_stable: float
    within_tolerance: bool
    ok: bool                           # validated and packaged
    style_used: str = ""
    objects: int = 0
    coverage_pct: Optional[float] = None
    osu_path: Optional[str] = None
    errors: List[str] = field(default_factory=list)


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
    preview_path: Optional[str] = None      # song + click track, for checking timing by ear (not in the .osz)
    background_path: Optional[str] = None   # cover art from the MP3, used as the map background
    mapset: bool = False
    difficulties: List[DifficultyResult] = field(default_factory=list)  # mapset only, easiest first
    skipped: List[str] = field(default_factory=list)                    # mapset difficulties not exported


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


def search_knob(sa, target, style_key, seed, meta, audio_name, progress: Progress, tol: float,
                stage: str = "generate"):
    history: List[Candidate] = []
    lo, hi = 0.0, KNOB_MAX
    knob = initial_knob(target)
    best: Optional[Candidate] = None
    for it in range(MAX_SEARCH_ITERS):
        progress.update(stage, it / MAX_SEARCH_ITERS,
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
    progress.update(stage, 1.0, f"Estimated {best.stars:.2f} stars")
    return best, history




# ---------------------------------------------------------------- mapset spread

MAPSET_SPREAD = [2.0, 3.2, 4.4, 5.6]
MAPSET_MIN_GAP = 0.5        # a spread entry this close below the target is dropped (the target replaces it)
# osu!'s difficulty-name convention, by star rating
VERSION_NAMES = [(2.0, "Easy"), (2.7, "Normal"), (4.0, "Hard"), (5.3, "Insane"), (6.5, "Expert")]


def mapset_targets(stars: float) -> List[float]:
    """Easiest first; the requested stars are always the hardest difficulty."""
    return [t for t in MAPSET_SPREAD if t <= stars - MAPSET_MIN_GAP] + [round(float(stars), 2)]


def version_name(stars: float) -> str:
    for limit, name in VERSION_NAMES:
        if stars < limit:
            return name
    return "Expert+"


def unique_versions(stars: List[float]) -> List[str]:
    """Names by estimated stars; difficulties that land in the same band get their stars appended."""
    names = [version_name(x) for x in stars]
    out: List[str] = []
    for name, x in zip(names, stars):
        v = f"{name} {x:.1f}" if names.count(name) > 1 else name
        while v in out:
            v += "+"
        out.append(v)
    return out


# ---------------------------------------------------------------- main entry

def _prepare(req: GenerationRequest, res: GenerationResult, progress: Progress):
    target = float(req.stars)
    if not (0.5 <= target <= 12.0):
        raise UserFacingError("Please enter a star rating between 0.5 and 12.")
    creator = req.creator or ""
    if creator and check_username(creator):
        raise UserFacingError(f"osu! username '{creator}': {check_username(creator)}")
    sa = analysis.analyse(req.mp3_path, progress, offset_ms=req.offset_ms)
    res.warnings.extend(sa.warnings)
    title, artist = resolve_metadata(sa, req)
    if not creator:
        res.warnings.append("No osu! username set: the map's creator is 'OsuMapGen'. Set your username "
                            "(case-sensitive) if you want to upload it.")
    audio_name = packaging.audio_filename(req.mp3_path)
    seed = int(sa.content_hash[:8], 16)
    return sa, title, artist, creator or "OsuMapGen", audio_name, seed


def _build(sa, target, style_key, seed, meta, audio_name, progress, tol, gen_stage="generate",
           val_stage="validate"):
    """Star search, then validation with bounded, section-targeted regeneration."""
    progress.check()
    best, history = search_knob(sa, target, style_key, seed, meta, audio_name, progress, tol, gen_stage)
    attempts: Dict[int, int] = {}
    cand = best
    rep = None
    for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
        progress.update(val_stage, attempt / (MAX_REPAIR_ATTEMPTS + 1), "Validating map")
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
    progress.update(val_stage, 1.0, "Validation finished")
    return cand, history, rep


def _style_breakdown(sa: SongAnalysis, cand: Candidate) -> str:
    styles = cand.gmap.stats.get("section_styles") or {}
    if not styles:
        return ""
    parts = []
    for s in sa.sections:
        if s.index in styles:
            t = max(0.0, s.start_ms) / 1000
            parts.append(f"{int(t // 60)}:{int(t % 60):02d} {STYLE_NAMES.get(styles[s.index])}")
    return "Styles by section: " + ", ".join(parts)


def _osu_name(folder: Path, meta, title: str, fallback: str = "map.osu") -> str:
    osu_name = serializer.osu_filename(meta)
    if len(str((folder / osu_name).resolve())) > 240:      # stay below Windows' MAX_PATH
        osu_name = serializer.safe_filename(f"{packaging.ascii_fallback(title)[:40]} [{meta.version}]") + ".osu"
        if len(str((folder / osu_name).resolve())) > 240:
            osu_name = fallback
    return osu_name


def _osz_name(folder: Path, artist: str, title: str, label: str) -> str:
    osz_name = serializer.safe_filename(f"{packaging.ascii_fallback(artist) or 'Unknown Artist'} - "
                                        f"{packaging.ascii_fallback(title) or 'Unknown Title'} "
                                        f"({label})", 150) + ".osz"
    if len(str((folder / osz_name).resolve())) > 240:
        osz_name = "map.osz"
    return osz_name


def _cover(req: GenerationRequest):
    """(art, background file name) from the MP3's embedded cover; (None, "") when it has none."""
    art = audio_io.cover_art(req.mp3_path)
    return art, (packaging.background_filename(art[1]) if art else "")


def _write_background(art, folder: Path, res: GenerationResult) -> List[str]:
    if not art:
        return []
    name = packaging.write_background(art, folder)
    res.background_path = str(folder / name)
    return [name]


def _write_preview(sa: SongAnalysis, objects, folder: Path, res: GenerationResult, progress: Progress) -> None:
    progress.update("package", 0.7, "Writing timing preview (song + clicks)")
    try:
        res.preview_path = str(preview.write_preview(sa.audio, objects, folder))
    except Exception as e:  # the map itself is fine; the preview is a convenience
        log.warning("Timing preview failed: %s", e, exc_info=True)
        res.warnings.append(f"The timing preview could not be written ({type(e).__name__}: {e}).")


def _output_base(req: GenerationRequest) -> Path:
    return Path(req.output_dir) if req.output_dir else Path.home() / "Documents" / "OsuMapGen Output"


def run(req: GenerationRequest, progress: Optional[Progress] = None) -> GenerationResult:
    progress = progress or Progress()
    if req.mapset:
        return run_mapset(req, progress)
    progress.plan([("decode", 8), ("features", 14), ("timing", 10), ("structure", 6),
                   ("generate", 45), ("validate", 7), ("package", 10)])
    t0 = time.time()
    target = float(req.stars)
    res = GenerationResult(ok=False, message="", requested_stars=target)
    sa, title, artist, creator, audio_name, seed = _prepare(req, res, progress)
    style_key = resolve_style(req.style, sa, target)
    res.style_used = STYLE_NAMES.get(style_key, style_key)
    version = f"Generated {target:.1f} Stars - {res.style_used}"
    art, bg_name = _cover(req)
    meta = serializer.Metadata(title=title, artist=artist, version=version, creator=creator,
                               tags=f"osumapgen generated {res.style_used.lower()}", background=bg_name)

    cand, history, rep = _build(sa, target, style_key, seed, meta, audio_name, progress, req.tolerance)

    res.estimated_stars = round(cand.stars, 2)
    res.estimated_stars_stable = round(cand.stars_stable, 2)
    res.within_tolerance = abs(cand.stars - target) <= req.tolerance
    res.coverage_pct = rep.metrics.get("coverage_pct") if rep else None
    if not res.within_tolerance:
        res.warnings.append(_star_explanation(target, cand, history))
    res.warnings.extend(str(i) for i in rep.warnings)
    res.timeline = _timeline(sa, cand.gmap)
    res.style_breakdown = _style_breakdown(sa, cand)

    # ---- export
    progress.update("package", 0.0, "Writing files")
    folder = packaging.make_output_folder(_output_base(req), artist, title, target, res.style_used)
    res.output_folder = str(folder)
    osu_name = _osu_name(folder, meta, title)
    osu_bytes = cand.text.encode("utf-8")
    report_payload = _report_payload(req, target, sa, cand, history, rep, meta, style_key, time.time() - t0)
    if not rep.ok:
        # never present an invalid map as complete: keep the draft for diagnosis only
        (folder / ("INVALID DRAFT - " + osu_name)).write_bytes(osu_bytes)
        res.errors = [str(i) for i in rep.errors]
        res.message = ("The generated map failed validation after "
                       f"{MAX_REPAIR_ATTEMPTS} repair attempts; no .osz was created. See the report.")
        res.report_path = str(_write_report(folder, report_payload, res))
        return res

    packaging.copy_audio(req.mp3_path, folder)
    extra = _write_background(art, folder, res)
    (folder / osu_name).write_bytes(osu_bytes)
    progress.update("package", 0.4, "Packaging .osz")
    osz = packaging.build_osz(folder, osu_name, audio_name,
                              _osz_name(folder, artist, title, f"{target:.1f} stars"), extra_files=extra)
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
    _write_preview(sa, cand.gmap.objects, folder, res, progress)
    res.duration_s = round(time.time() - t0, 1)
    report_payload["elapsed_s"] = res.duration_s
    res.ok = True
    res.message = (f"Done: estimated {res.estimated_stars:.2f} stars (requested {target:.2f}), "
                   f"{len(cand.gmap.objects)} objects, {res.coverage_pct:.0f}% of the music mapped.")
    res.report_path = str(_write_report(folder, report_payload, res))
    progress.update("package", 1.0, "Finished")
    return res


def run_mapset(req: GenerationRequest, progress: Optional[Progress] = None) -> GenerationResult:
    """Several difficulties from ONE audio analysis, packaged together in one .osz."""
    progress = progress or Progress()
    t0 = time.time()
    top = float(req.stars)
    targets = mapset_targets(top) if 0.5 <= top <= 12.0 else [top]
    n = len(targets)
    stages = [("decode", 8), ("features", 14), ("timing", 10), ("structure", 6)]
    for i in range(n):
        stages += [(f"generate{i}", 45 / n), (f"validate{i}", 7 / n)]
    progress.plan(stages + [("package", 10)])
    res = GenerationResult(ok=False, message="", requested_stars=top, mapset=True)
    sa, title, artist, creator, audio_name, seed = _prepare(req, res, progress)

    # ---- every difficulty comes from the same analysis
    built = []
    art, bg_name = _cover(req)
    for i, target in enumerate(targets):
        style_key = resolve_style(req.style, sa, target)
        style_name = STYLE_NAMES.get(style_key, style_key)
        meta = serializer.Metadata(title=title, artist=artist, version=f"Generated {target:.1f} Stars",
                                   creator=creator, tags=f"osumapgen generated mapset {style_name.lower()}",
                                   background=bg_name)
        cand, history, rep = _build(sa, target, style_key, seed, meta, audio_name, progress, req.tolerance,
                                    f"generate{i}", f"validate{i}")
        built.append((target, style_key, meta, cand, history, rep))

    # ---- name difficulties by their estimated stars, then re-serialize with the final Version
    # (Version does not affect the star rating or any validation check)
    versions = unique_versions([b[3].stars for b in built])
    entries = []
    for (target, style_key, meta, cand, history, rep), version in zip(built, versions):
        meta = replace(meta, version=version)
        cand = replace(cand, text=serializer.serialize(sa, cand.gmap, meta, audio_name, _lead_in(cand.gmap)))
        d = DifficultyResult(version=version, requested_stars=target, estimated_stars=round(cand.stars, 2),
                             estimated_stars_stable=round(cand.stars_stable, 2),
                             within_tolerance=abs(cand.stars - target) <= req.tolerance, ok=rep.ok,
                             style_used=STYLE_NAMES.get(style_key, style_key), objects=len(cand.gmap.objects),
                             coverage_pct=rep.metrics.get("coverage_pct"),
                             errors=[str(i) for i in rep.errors])
        if not d.within_tolerance:
            res.warnings.append(f"[{version}] " + _star_explanation(target, cand, history))
        res.warnings.extend(f"[{version}] {i}" for i in rep.warnings)
        entries.append((d, target, style_key, meta, cand, history, rep))
    res.difficulties = [e[0] for e in entries]

    # ---- export: write every difficulty, re-check each written file, package the ones that pass
    progress.update("package", 0.0, "Writing files")
    folder = packaging.make_output_folder(_output_base(req), artist, title, top, "Full mapset")
    res.output_folder = str(folder)
    extra: List[str] = []
    if any(e[0].ok for e in entries):
        packaging.copy_audio(req.mp3_path, folder)
        extra = _write_background(art, folder, res)
    exported: Dict[str, bytes] = {}
    names: Dict[str, str] = {}
    for k, (d, *_rest) in enumerate(entries):
        meta, cand = _rest[2], _rest[3]
        osu_name = _osu_name(folder, meta, title, f"map {k + 1}.osu")
        names[d.version] = osu_name
        data = cand.text.encode("utf-8")
        if d.ok:
            (folder / osu_name).write_bytes(data)
            vrep = validator.validate_text((folder / osu_name).read_bytes().decode("utf-8"), sa,
                                           audio_dir=folder, audio_duration_ms=sa.audio.duration_ms)
            if vrep.ok:
                d.osu_path = str(folder / osu_name)
                exported[osu_name] = data
                continue
            d.ok = False
            d.errors = [str(i) for i in vrep.errors]
            (folder / osu_name).unlink()
        # never present an invalid map as complete: keep the draft for diagnosis only
        (folder / ("INVALID DRAFT - " + osu_name)).write_bytes(data)
        res.skipped.append(d.version)
        res.errors.append(f"[{d.version}] SKIPPED (failed validation)"
                          + (f": {d.errors[0]}" if d.errors else ""))
    payloads = [dict(_report_payload(req, target, sa, cand, history, rep, meta, style_key, 0.0),
                     exported=d.ok, osu_file=names[d.version] if d.ok else None)
                for d, target, style_key, meta, cand, history, rep in entries]

    def finish(ok: bool, message: str) -> GenerationResult:
        res.ok = ok
        res.message = message
        res.duration_s = round(time.time() - t0, 1)
        res.report_path = str(_write_mapset_report(folder, req, sa, payloads, res))
        return res

    if not exported:
        return finish(False, f"All {n} difficulties failed validation after {MAX_REPAIR_ATTEMPTS} repair "
                             "attempts; no .osz was created. See the report.")

    progress.update("package", 0.4, "Packaging .osz")
    osz = packaging.build_osz(folder, list(exported), audio_name, _osz_name(folder, artist, title, "full mapset"),
                              extra_files=extra)
    orep = validator.validate_osz(osz, exported, None, audio_name)
    if not orep.ok:
        res.errors.extend(str(i) for i in orep.errors)
        osz.unlink(missing_ok=True)
        return finish(False, "Exported files failed their final check; see the report.")

    ok_entries = [e for e in entries if e[0].ok]
    hardest, cand = ok_entries[-1][0], ok_entries[-1][4]
    res.osz_path = str(osz)
    res.osu_path = hardest.osu_path
    res.estimated_stars = hardest.estimated_stars
    res.estimated_stars_stable = hardest.estimated_stars_stable
    res.within_tolerance = all(e[0].within_tolerance for e in ok_entries)
    res.coverage_pct = hardest.coverage_pct
    res.style_used = hardest.style_used
    res.timeline = _timeline(sa, cand.gmap)
    res.style_breakdown = _style_breakdown(sa, cand)
    _write_preview(sa, cand.gmap.objects, folder, res, progress)        # clicks of the hardest difficulty
    listing =", ".join(f"{e[0].version} {e[0].estimated_stars:.2f}" for e in ok_entries)
    msg = f"Done: full mapset with {len(ok_entries)} difficulties ({listing} stars) in one .osz."
    if res.skipped:
        msg += f" SKIPPED (failed validation, not in the .osz): {', '.join(res.skipped)}."
    out = finish(True, msg)
    progress.update("package", 1.0, "Finished")
    return out


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


def _report_payload(req, target, sa, cand: Candidate, history, rep, meta, style_key, elapsed) -> dict:
    client = packaging.osu_client_name()
    return {
        "generator": f"OsuMapGen {__version__}",
        "input": str(req.mp3_path),
        "metadata": {"title": meta.title, "artist": meta.artist, "version": meta.version, "creator": meta.creator,
                     "title_source": "user" if req.title else ("id3" if sa.audio.title else "filename"),
                     "artist_source": "user" if req.artist else ("id3" if sa.audio.artist else
                                                                 "filename/unknown")},
        "stars": {
            "requested": target,
            "estimated_lazer": round(cand.stars, 3),
            "estimated_stable": round(cand.stars_stable, 3),
            "calculator": star_rating.calculator_version(),
            "tolerance": req.tolerance,
            "within_tolerance": abs(cand.stars - target) <= req.tolerance,
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


# ---------------------------------------------------------------- reports

def _head_lines(payload: dict, res: GenerationResult) -> List[str]:
    return [
        f"OsuMapGen generation report ({payload['generator']})",
        "=" * 60,
        f"Status:              {'COMPLETE' if res.ok else 'FAILED'} - {res.message}",
        f"Input:               {payload['input']}",
        f"Title / Artist:      {payload['metadata']['title']} / {payload['metadata']['artist']}"
        f"  (from {payload['metadata']['title_source']} / {payload['metadata']['artist_source']})",
        f"Creator:             {payload['metadata']['creator']}",
    ]


def _extras(res: GenerationResult) -> dict:
    return {"timing_preview": Path(res.preview_path).name if res.preview_path else None,
            "background": Path(res.background_path).name if res.background_path else None}


def _extra_lines(res: GenerationResult) -> List[str]:
    x = _extras(res)
    return [
        "Timing preview:      " + (f"{x['timing_preview']} (song + a click on every note; not in the .osz)"
                                   if x["timing_preview"] else "not written"),
        "Background:          " + (f"{x['background']} (cover art from the MP3)" if x["background"]
                                   else "none (the MP3 has no embedded cover art)"),
    ]


def _star_lines(s: dict) -> List[str]:
    return [
        "Star rating",
        f"  Requested:                 {s['requested']:.2f}",
        f"  Estimated (lazer algo):    {s['estimated_lazer']:.2f}   [{s['calculator']}]",
        f"  Estimated (stable algo):   {s['estimated_stable']:.2f}",
        f"  Within +/-{s['tolerance']}:          {'yes' if s['within_tolerance'] else 'NO'}",
        f"  Installed osu! client:     {s['installed_client']}",
        f"  Client's own rating:       {s['client_rating']}",
    ]


def _audio_lines(a: dict, an: dict) -> List[str]:
    return [
        "Audio",
        f"  Duration:     {a['duration_s']:.1f}s   analysed: {a['analysed_s']:.1f}s ({a['analysed_pct']:.0f}%)",
        f"  Music span:   {an['music_start_ms'] / 1000:.1f}s - {an['music_end_ms'] / 1000:.1f}s",
        f"  Decoder:      {a['decoder']}, {a['sample_rate']} Hz, {a['channels']} ch, {a['bitrate_kbps']} kbps",
        f"  Timing:       " + "; ".join(f"{t['bpm']} BPM @ {t['offset_ms']}ms (conf {t['confidence']})"
                                         for t in an["timing"]),
    ]


def _section_lines(an: dict, sec_styles: dict) -> List[str]:
    lines = ["Sections"]
    for i, sec in enumerate(an["sections"]):
        st = sec_styles.get(i) or sec_styles.get(str(i))
        lines.append(f"  {sec['start_ms'] / 1000:7.1f}s - {sec['end_ms'] / 1000:7.1f}s  {sec['label']:<10}"
                     f" intensity {sec['intensity']:.2f}{'  kiai' if sec['kiai'] else ''}"
                     f"{f'  style: {STYLE_NAMES.get(st, st)}' if st else ''}")
    return lines


def _map_lines(payload: dict) -> List[str]:
    m = payload["map"]
    v = payload["validation"]
    return ["Map",
            f"  Objects: {m.get('objects')} (circles {m.get('circles')}, sliders {m.get('sliders')}, "
            f"spinners {m.get('spinners')}, stream notes {m.get('stream_notes')})",
            f"  Breaks:  {len(m.get('breaks', []))}",
            f"  Settings: " + ", ".join(f"{k}={v}" for k, v in payload["difficulty_settings"].items()),
            "",
            "Validation",
            f"  Passed: {'yes' if v['ok'] else 'NO'}",
            "  " + ", ".join(f"{k}={val}" for k, val in v["metrics"].items() if k != "section_density")]


def _search_lines(s: dict) -> List[str]:
    return ["Star-rating search"] + [f"  knob {h['knob']:.3f} -> {h['stars']:.2f} stars ({h['objects']} objects)"
                                     for h in s["search"]]


def _write_report(folder: Path, payload: dict, res: GenerationResult) -> Path:
    payload["result"] = {"ok": res.ok, "message": res.message, "warnings": res.warnings, "errors": res.errors}
    payload["extras"] = _extras(res)
    (folder / "report.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    lines = (_head_lines(payload, res) + _extra_lines(res) + [""] + _star_lines(payload["stars"]) + [""]
             + _audio_lines(payload["audio"], payload["analysis"]) + [""]
             + _section_lines(payload["analysis"], payload["map"].get("section_styles") or {}) + [""]
             + _map_lines(payload))
    if res.errors:
        lines += ["", "Errors"] + [f"  - {e}" for e in res.errors]
    if res.warnings:
        lines += ["", "Warnings"] + [f"  - {w}" for w in res.warnings]
    lines += [""] + _search_lines(payload["stars"])
    p = folder / "report.txt"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _write_mapset_report(folder: Path, req: GenerationRequest, sa: SongAnalysis, payloads: List[dict],
                         res: GenerationResult) -> Path:
    first = payloads[0]
    summary = [{"version": d.version, "requested_stars": d.requested_stars, "estimated_lazer": d.estimated_stars,
                "estimated_stable": d.estimated_stars_stable, "within_tolerance": d.within_tolerance,
                "valid": d.ok, "exported": d.ok, "style": d.style_used, "objects": d.objects,
                "coverage_pct": d.coverage_pct, "osu_file": p.get("osu_file"), "errors": d.errors}
               for d, p in zip(res.difficulties, payloads)]
    data = {"generator": first["generator"], "input": first["input"], "mapset": True,
            "metadata": dict(first["metadata"], version=None), "requested_top_stars": req.stars,
            "tolerance": req.tolerance, "audio": first["audio"], "analysis": first["analysis"],
            "difficulties": summary, "skipped": res.skipped,
            "details": {p["metadata"]["version"]: p for p in payloads},
            "elapsed_s": res.duration_s, "extras": _extras(res),
            "result":{"ok": res.ok, "message": res.message, "warnings": res.warnings, "errors": res.errors}}
    (folder / "report.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    lines = _head_lines(first, res) + [f"Mapset:              {len(payloads)} difficulties from one analysis, "
                                       f"one .osz (BeatmapSetID -1)"] + _extra_lines(res) + ["",
                                       "Difficulties (easiest first)",
                                       f"  {'Version':<14}{'requested':>10}{'lazer':>8}{'stable':>8}"
                                       f"  {'tolerance':<10}{'validation':<12}style"]
    for d in res.difficulties:
        lines.append(f"  {d.version:<14}{d.requested_stars:>10.2f}{d.estimated_stars:>8.2f}"
                     f"{d.estimated_stars_stable:>8.2f}  {'ok' if d.within_tolerance else 'OUTSIDE':<10}"
                     f"{'passed' if d.ok else 'FAILED':<12}{d.style_used}")
    if res.skipped:
        lines += ["", "SKIPPED (failed validation, not in the .osz; drafts kept as 'INVALID DRAFT - ...'): "
                  + ", ".join(res.skipped)]
    lines += [""] + _audio_lines(first["audio"], first["analysis"]) + [""] + _section_lines(first["analysis"], {})
    if res.errors:
        lines += ["", "Errors"] + [f"  - {e}" for e in res.errors]
    if res.warnings:
        lines += ["", "Warnings"] + [f"  - {w}" for w in res.warnings]
    for d, p in zip(res.difficulties, payloads):
        lines += ["", "", f"===== [{d.version}] {'' if d.ok else '(SKIPPED) '}" + "=" * 40,
                  f"File: {p.get('osu_file') or '(not exported)'}", ""]
        lines += _star_lines(p["stars"]) + [""]
        if p["map"].get("section_styles"):
            lines += _section_lines(p["analysis"], p["map"]["section_styles"]) + [""]
        lines += _map_lines(p)
        if p["validation"]["errors"]:
            lines += ["  Errors:"] + [f"    - {e}" for e in p["validation"]["errors"]]
        lines += [""] + _search_lines(p["stars"])
    out = folder / "report.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
