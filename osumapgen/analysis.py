"""Whole-song analysis: music extent, timing, sections, intensity and the tick grid."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from . import audio_io, features, timing
from .infra import Progress, UserFacingError, get_logger
from .model import GridTick, Onset, Section, SongAnalysis, TimingSection

log = get_logger("analysis")

SILENCE_DB = -52.0          # relative to the song's 95th-percentile loudness
# Loud modern masters put quiet intros 40-50 dB below the peak, so "audible" must reach that low.
ACTIVE_DB = -50.0


@dataclass
class Bar:
    start: float
    end: float
    timing_index: int
    loud_db: float = 0.0
    density: float = 0.0     # onsets per beat
    high: float = 0.0
    feat: Optional[np.ndarray] = None
    silent: bool = False
    quiet: bool = False


def music_extent(f: features.Features):
    active = f.rms_db > ACTIVE_DB
    # require ~0.3 s of sustained activity to avoid isolated clicks
    k = max(1, int(round(300 / f.frame_ms)))
    run = np.convolve(active.astype(float), np.ones(k) / k, mode="same") > 0.6
    idx = np.where(run)[0]
    if idx.size == 0:
        idx = np.where(active)[0]
    if idx.size == 0:
        raise UserFacingError("No audible music was found in the file.")
    start = max(0.0, f.times_ms[idx[0]] - k * f.frame_ms / 2)
    end = f.times_ms[idx[-1]] + k * f.frame_ms / 2
    return float(start), float(min(end, f.times_ms[-1]))


def make_bars(tsecs: List[TimingSection], music_start: float, music_end: float) -> List[Bar]:
    bars: List[Bar] = []
    for ti, ts in enumerate(tsecs):
        lo = max(ts.start_ms, music_start - ts.beat_ms * 4) if ti == 0 else ts.start_ms
        hi = min(ts.end_ms, music_end + ts.beat_ms)
        if hi <= lo:
            continue
        k0 = int(np.floor((lo - ts.offset_ms) / ts.beat_ms))
        while (k0 - ts.downbeat_phase) % ts.meter:
            k0 -= 1
        k = k0
        while True:
            s = ts.offset_ms + k * ts.beat_ms
            e = s + ts.meter * ts.beat_ms
            if s >= hi:
                break
            s_c, e_c = max(s, ts.start_ms if ti > 0 else s), min(e, ts.end_ms)
            if e_c > s_c and e_c > music_start - 1:
                bars.append(Bar(s_c, e_c, ti))
            k += ts.meter
    return bars


def bar_features(bars: List[Bar], f: features.Features, on: features.OnsetPeaks, tsecs):
    for b in bars:
        i0, i1 = f.frame_of(b.start), max(f.frame_of(b.end), f.frame_of(b.start) + 1)
        seg = slice(i0, i1)
        b.loud_db = float(np.mean(f.rms_db[seg]))
        beats = (b.end - b.start) / tsecs[b.timing_index].beat_ms
        sel = (on.times_ms >= b.start) & (on.times_ms < b.end) & (on.strength > 0.25)
        b.density = float(sel.sum() / max(beats, 0.5))
        b.high = float(np.mean(f.env_high[seg]))
        b.feat = np.concatenate([f.mfcc[:, seg].mean(axis=1), [b.loud_db / 6.0, b.density, b.high * 4]])
        b.silent = b.loud_db < SILENCE_DB or float(np.max(f.rms_db[seg])) < SILENCE_DB + 6
        b.quiet = (not b.silent) and b.density < 0.12 and b.loud_db < -22


def novelty_boundaries(bars: List[Bar], kernel: int = 4) -> List[int]:
    n = len(bars)
    if n < 2 * kernel + 2:
        return []
    X = np.array([b.feat for b in bars])
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-6)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    S = X @ X.T
    g = np.outer(np.r_[-np.ones(kernel), np.ones(kernel)], np.r_[-np.ones(kernel), np.ones(kernel)]) * -1
    taper = np.exp(-0.5 * (np.linspace(-1.5, 1.5, 2 * kernel)) ** 2)
    g *= np.outer(taper, taper)
    nov = np.zeros(n)
    Sp = np.pad(S, kernel, mode="edge")
    for i in range(n):
        nov[i] = -np.sum(Sp[i:i + 2 * kernel, i:i + 2 * kernel] * g)
    nov = np.maximum(nov, 0)
    thr = nov.mean() + 0.5 * nov.std()
    peaks = []
    for i in range(2, n - 2):
        if nov[i] >= thr and nov[i] == nov[max(0, i - 3):i + 4].max():
            j = i
            # prefer phrase starts (multiples of 4 bars) when the novelty is nearly as high
            for c in (i - (i % 4), i - (i % 4) + 4):
                if 0 < c < n and abs(c - i) <= 2 and nov[c] >= 0.7 * nov[i]:
                    j = c
                    break
            if not peaks or j - peaks[-1] >= 4:
                peaks.append(j)
    return peaks


def build_sections(bars: List[Bar], tsecs, music_start, music_end, onsets_t, onsets_s) -> List[Section]:
    n = len(bars)
    cuts = set(novelty_boundaries(bars))
    # silence / quiet runs form breaks
    flags = [("silent" if b.silent else "quiet" if b.quiet else "music") for b in bars]
    i = 0
    breaks = []
    while i < n:
        if flags[i] != "music":
            j = i
            while j < n and flags[j] != "music":
                j += 1
            dur = bars[j - 1].end - bars[i].start
            silent_bars = sum(1 for k in range(i, j) if flags[k] == "silent")
            if (silent_bars >= 2 and dur >= 3000) or (j - i >= 4 and dur >= 6000):
                breaks.append((i, j))
            i = j
        else:
            i += 1
    for a, b in breaks:
        cuts.add(a)
        cuts.add(b)
    cuts = sorted(c for c in cuts if 0 < c < n)
    spans = []
    prev = 0
    for c in cuts + [n]:
        if c > prev:
            spans.append([prev, c])
        prev = c
    is_brk = lambda s: any(a <= s[0] and s[1] <= b for a, b in breaks)
    # merge very short non-break spans into the more similar neighbour
    changed = True
    while changed and len(spans) > 1:
        changed = False
        for k, s in enumerate(spans):
            if s[1] - s[0] < 4 and not is_brk(s):
                left = spans[k - 1] if k > 0 and not is_brk(spans[k - 1]) else None
                right = spans[k + 1] if k + 1 < len(spans) and not is_brk(spans[k + 1]) else None
                if left is None and right is None:
                    continue
                if left is not None and (right is None or (right[1] - right[0]) >= (left[1] - left[0])):
                    left[1] = s[1]
                else:
                    right[0] = s[0]
                spans.pop(k)
                changed = True
                break

    sections: List[Section] = []
    for k, (a, b) in enumerate(spans):
        sb = bars[a:b]
        brk = is_brk((a, b))
        start = max(sb[0].start, music_start - 1) if k == 0 else sb[0].start
        end = sb[-1].end if k + 1 < len(spans) else max(sb[-1].end, music_end)
        sections.append(Section(
            index=k, start_ms=float(start), end_ms=float(end), label="break" if brk else "",
            intensity=0.0, energy_db=float(np.mean([x.loud_db for x in sb])),
            onset_density=float(np.mean([x.density for x in sb])), is_break=brk))

    music = [s for s in sections if not s.is_break]
    if music:
        # relative to the most intense part of the song: 15 dB quieter -> 0 loudness score
        loud = np.array([s.energy_db for s in music])
        dens = np.array([s.onset_density for s in music])
        nl = np.clip(1.0 + (loud - loud.max()) / 15.0, 0.0, 1.0)
        nd = dens / max(dens.max(), 1e-6)
        absolute = 0.6 * nl + 0.4 * nd
        # Compressed masters keep every section within a few dB, so the absolute score sits
        # near 1 everywhere. Blend in the section's time-weighted rank within this song so
        # verses and choruses still differ.
        dur = np.array([s.end_ms - s.start_ms for s in music])
        order = np.argsort(absolute, kind="stable")
        rank = np.empty(len(music))
        acc = 0.0
        for i in order:
            rank[i] = (acc + dur[i] / 2) / dur.sum()
            acc += dur[i]
        if np.ptp(absolute) < 0.03:
            rank[:] = 0.5                      # genuinely uniform song: no invented contrast
        for s, a, r in zip(music, absolute, rank):
            s.intensity = float(np.clip(0.5 * a + 0.5 * r, 0.0, 1.0))
    for k, s in enumerate(sections):
        if s.is_break:
            continue
        nxt = sections[k + 1] if k + 1 < len(sections) else None
        bars_len = sum(1 for b in bars if s.start_ms <= b.start < s.end_ms)
        if k == 0 and s.intensity < 0.45:
            s.label = "intro"
        elif nxt is None and s.intensity < 0.5:
            s.label = "outro"
        elif s.intensity >= 0.82:
            s.label = "chorus"
            s.kiai = bars_len >= 8
        elif nxt is not None and not nxt.is_break and nxt.intensity >= 0.82 and s.intensity < nxt.intensity - 0.1:
            s.label = "build"
        elif s.intensity < 0.42:
            s.label = "breakdown"
        else:
            s.label = "verse"
    # snap divisor per section (straight vs triplet subdivision)
    for s in sections:
        s.snap = section_snap(s, tsecs, onsets_t, onsets_s)
    return sections


def section_snap(s: Section, tsecs, t, w) -> int:
    sel = (t >= s.start_ms) & (t < s.end_ms) & (w > 0.25)
    if sel.sum() < 8:
        return 4
    quarter = triplet = 0.0
    for tt, ww in zip(t[sel], w[sel]):
        ts = next((x for x in reversed(tsecs) if x.start_ms <= tt), tsecs[0])
        x = ((tt - ts.offset_ms) / ts.beat_ms) % 1.0
        if min(abs(x - 0.25), abs(x - 0.75)) < 0.06:
            quarter += ww
        if min(abs(x - 1 / 3), abs(x - 2 / 3)) < 0.06:
            triplet += ww
    total = w[sel].sum()
    return 3 if triplet > 1.5 * quarter and triplet > 0.15 * total else 4


def metric_weight(beat_in_bar: int, sub: int, snap: int) -> float:
    if sub == 0:
        return {0: 1.0, 2: 0.8}.get(beat_in_bar, 0.65)
    if snap == 4:
        return 0.45 if sub == 2 else 0.25
    return 0.3


def build_ticks(tsecs, sections: List[Section], f: features.Features, on: features.OnsetPeaks,
                music_start: float, music_end: float) -> List[GridTick]:
    ticks: List[GridTick] = []
    sec_starts = np.array([s.start_ms for s in sections])
    for ti, ts in enumerate(tsecs):
        lo = max(ts.start_ms, music_start - ts.beat_ms * 0.5)
        hi = min(ts.end_ms, music_end + ts.beat_ms * 0.25)
        if hi <= lo:
            continue
        k = int(np.floor((lo - ts.offset_ms) / ts.beat_ms))
        while True:
            bt = ts.offset_ms + k * ts.beat_ms
            if bt >= hi:
                break
            si = int(np.clip(np.searchsorted(sec_starts, bt, side="right") - 1, 0, len(sections) - 1))
            snap = sections[si].snap
            for sub in range(snap):
                t = bt + sub * ts.beat_ms / snap
                if lo <= t < hi:
                    sj = int(np.clip(np.searchsorted(sec_starts, t, side="right") - 1, 0, len(sections) - 1))
                    bib = (k - ts.downbeat_phase) % ts.meter
                    ticks.append(GridTick(time_ms=float(t), beat_index=int(k - ts.downbeat_phase), sub=sub,
                                          snap=snap, timing_index=ti, section_index=sj,
                                          metric=metric_weight(bib, sub, snap),
                                          onset=0.0, low=0.0, high=0.0, sustain=0.0))
            k += 1
    # attach onsets to their nearest tick
    if ticks and on.times_ms.size:
        tt = np.array([x.time_ms for x in ticks])
        # salience for mapping: half local prominence, half song-wide loudness
        sal = 0.5 * on.strength + 0.5 * on.glob
        for t, s, lw, hg in zip(on.times_ms, sal, on.low, on.high):
            i = int(np.searchsorted(tt, t))
            best = None
            for j in (i - 1, i):
                if 0 <= j < len(ticks):
                    d = abs(tt[j] - t)
                    spacing = tsecs[ticks[j].timing_index].beat_ms / ticks[j].snap
                    if d <= min(40.0, 0.35 * spacing) and (best is None or d < best[0]):
                        best = (d, j)
            if best is not None:
                g = ticks[best[1]]
                if s > g.onset:
                    g.onset, g.low, g.high = float(s), float(lw), float(hg)
    # sustain: does mid-band energy hold after the tick (held notes, vocals)?
    for g in ticks:
        beat = tsecs[g.timing_index].beat_ms
        i0 = f.frame_of(g.time_ms + 25)
        i1 = max(i0 + 1, f.frame_of(g.time_ms + beat * 0.75))
        at = f.mid_energy_db[i0]
        after = float(np.mean(f.mid_energy_db[i0:i1]))
        g.sustain = float(np.clip(1.0 + (after - at) / 8.0, 0.0, 1.0)) * float(f.rms_db[i0] > -30)
    return ticks


def analyse(path: str, progress: Progress, offset_ms: float = 0.0) -> SongAnalysis:
    progress.update("decode", 0.0, "Reading audio file")
    info = audio_io.probe(path)
    y, sr = audio_io.decode(info)
    progress.update("decode", 1.0, f"Decoded {info.duration_ms / 1000:.1f}s of audio ({info.decoder})")

    progress.update("features", 0.0, "Computing spectral features")
    f = features.compute(y, sr, progress=lambda x: progress.update("features", x * 0.8, "Computing spectral features"))
    on = features.detect_onsets(f)
    if offset_ms:
        on.times_ms = on.times_ms + offset_ms
    analysed_ms = len(y) / sr * 1000.0
    progress.update("features", 1.0, f"Found {len(on.times_ms)} onsets")

    progress.update("timing", 0.0, "Detecting tempo and beat grid")
    music_start, music_end = music_extent(f)
    try:
        tsecs, conf, cands, warns = timing.detect_timing(on.times_ms, on.timing_weight, on.low,
                                                         music_start, music_end, info.duration_ms)
    except ValueError as e:
        raise UserFacingError(str(e)) from e
    progress.update("timing", 1.0, "Beat grid: " + ", ".join(f"{t.bpm:.2f} BPM" for t in tsecs))

    progress.update("structure", 0.0, "Finding sections")
    bars = make_bars(tsecs, music_start, music_end)
    bar_features(bars, f, on, tsecs)
    sections = build_sections(bars, tsecs, music_start, music_end, on.times_ms, on.strength)
    ticks = build_ticks(tsecs, sections, f, on, music_start, music_end)
    progress.update("structure", 1.0, f"{len(sections)} sections")

    onsets = [Onset(float(t), float(s), float(lo), float(hi))
              for t, s, lo, hi in zip(on.times_ms, on.strength, on.low, on.high)]
    if analysed_ms < info.duration_ms - 1500:
        warns.append(f"Only {analysed_ms / 1000:.1f}s of {info.duration_ms / 1000:.1f}s were analysed.")
    sa = SongAnalysis(audio=info, music_start_ms=music_start, music_end_ms=music_end, timing=tsecs,
                      tempo_confidence=conf, tempo_candidates=cands, onsets=onsets, sections=sections,
                      ticks=ticks, analysed_ms=analysed_ms, warnings=warns,
                      content_hash=audio_io.file_hash(path))
    log.info("Sections: %s", [(s.label, round(s.start_ms), round(s.end_ms), round(s.intensity, 2), s.snap)
                               for s in sections])
    return sa
