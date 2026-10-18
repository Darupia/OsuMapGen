"""Tempo estimation and beat-grid fitting.

The grid is fitted with a phase-coherence ("vector strength") objective over
detected onsets: for a pulse frequency f the sum  sum_k w_k * exp(2*pi*i*f*t_k)
has magnitude near 1 when onsets lock to a grid of period 1/f, and its angle
gives the grid phase. Beat, 1/2, 1/3 and 1/4 harmonics are combined so that
off-beat hats or triplets do not cancel the evidence. Evaluating it over the
whole song gives sub-millisecond BPM resolution for constant-tempo music.

Tempo changes are only introduced when windowed estimates show a different
tempo that clearly explains the onsets better than the current one, for
several consecutive windows. Slowly drifting (live) tempo is handled by
splitting a segment only if that measurably reduces phase error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from .infra import get_logger
from .model import TimingSection

log = get_logger("timing")

BPM_MIN, BPM_MAX = 60.0, 240.0
PRIOR_CENTER = 150.0          # osu! maps are usually timed between ~100 and ~220 BPM
PRIOR_SIGMA_OCT = 0.6
HARMONIC_WEIGHTS = ((1, 1.0), (2, 0.5), (3, 0.35), (4, 0.25))


def _vs(t_s: np.ndarray, w: np.ndarray, freqs) -> np.ndarray:
    """Complex normalised vector strength for each frequency (Hz)."""
    freqs = np.atleast_1d(np.asarray(freqs, dtype=float))
    if t_s.size == 0:
        return np.zeros(len(freqs), complex)
    out = np.empty(len(freqs), complex)
    wsum = w.sum() + 1e-12
    step = max(1, 2_000_000 // max(1, t_s.size))
    for a in range(0, len(freqs), step):
        f = freqs[a:a + step, None]
        out[a:a + step] = (w[None, :] * np.exp(2j * np.pi * f * t_s[None, :])).sum(axis=1) / wsum
    return out


def beat_score(t_s, w, bpms) -> np.ndarray:
    f = np.asarray(bpms, dtype=float) / 60.0
    return sum(c * np.abs(_vs(t_s, w, h * f)) for h, c in HARMONIC_WEIGHTS)


def prior(bpm) -> np.ndarray:
    return np.exp(-0.5 * (np.log2(np.asarray(bpm) / PRIOR_CENTER) / PRIOR_SIGMA_OCT) ** 2)


@dataclass
class GridFit:
    bpm: float
    offset_ms: float      # time of one beat (any beat) in ms
    strength: float       # best harmonic coherence 0..1


HARMONIC_PREF = {1: 1.0, 2: 0.9, 3: 0.75, 4: 0.7}


def grid_phase(times_ms, w, bpm, low=None):
    """Beat phase (ms, in [0, beat)) and coherence for a known BPM.

    Off-beat onsets cancel the beat-rate component, so its angle alone is
    unreliable. The precise phase comes from the most coherent pulse level
    (beat, 1/2, 1/3 or 1/4); which of its sub-positions is the actual beat is
    then voted by the coarser levels, weighted towards low-frequency (kick)
    onsets.
    """
    beat_ms = 60000.0 / bpm
    f = bpm / 60.0
    t = times_ms / 1000.0
    comps = {h: _vs(t, w, h * f)[0] for h, _ in HARMONIC_WEIGHTS}
    hmax = max(comps, key=lambda h: abs(comps[h]) * HARMONIC_PREF[h])
    base = (np.angle(comps[hmax]) % (2 * np.pi)) / (2 * np.pi) * beat_ms / hmax
    cands = [base + j * beat_ms / hmax for j in range(hmax)]
    lower = [h for h in comps if h < hmax and hmax % h == 0] or [1]
    wv = w * (0.2 + low) ** 2 if low is not None else w
    vote_comps = {h: _vs(t, wv, h * f)[0] for h in lower}

    def votes(phi):
        return sum(np.real(vote_comps[h] * np.exp(-2j * np.pi * h * phi / beat_ms)) for h in lower)

    phase = max(cands, key=votes) % beat_ms
    strength = max(abs(c) for c in comps.values())
    return float(phase), float(strength)


def fit_grid(times_ms, w, bpm0, lo_ms=-np.inf, hi_ms=np.inf, span=0.01, steps=1001, low=None) -> GridFit:
    sel = (times_ms >= lo_ms) & (times_ms < hi_ms)
    t = times_ms[sel] / 1000.0
    ww = w[sel]
    low_sel = low[sel] if low is not None else None
    if t.size < 4:
        return GridFit(bpm0, 0.0, 0.0)
    bpms = np.linspace(bpm0 * (1 - span), bpm0 * (1 + span), steps)
    score = beat_score(t, ww, bpms)
    i = int(np.argmax(score))
    bpm = float(bpms[i])
    if 0 < i < steps - 1:
        a, b, c = score[i - 1], score[i], score[i + 1]
        d = a - 2 * b + c
        if abs(d) > 1e-12:
            bpm += float(np.clip(0.5 * (a - c) / d, -1, 1)) * (bpms[1] - bpms[0])
    best = float(beat_score(t, ww, [bpm])[0])
    # prefer a "clean" BPM (integer or .5) if it explains the onsets as well
    for clean in sorted({float(round(bpm)), round(bpm * 2) / 2}, key=lambda c: abs(c - bpm)):
        if abs(clean - bpm) < 0.2:
            if float(beat_score(t, ww, [clean])[0]) >= 0.985 * best:
                bpm = clean
                break
    offset, strength = grid_phase(t * 1000.0, ww, bpm, low_sel)
    return GridFit(float(bpm), float(offset), float(strength))


def global_candidates(times_ms, w, n=4) -> List[Tuple[float, float]]:
    t = times_ms / 1000.0
    bpms = BPM_MIN * (1.0025 ** np.arange(int(np.log(BPM_MAX / BPM_MIN) / np.log(1.0025)) + 1))
    raw = beat_score(t, w, bpms)
    score = raw * (0.35 + 0.65 * prior(bpms))
    peaks = [i for i in range(1, len(score) - 1) if score[i] >= score[i - 1] and score[i] >= score[i + 1]]
    peaks.sort(key=lambda i: -score[i])
    out: List[Tuple[float, float]] = []
    for i in peaks:
        b = float(bpms[i])
        if all(abs(np.log2(b / o)) > 0.02 for o, _ in out):
            out.append((b, float(score[i])))
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------- tempo changes

def _window_scores(times_ms, w, g_bpm, start, end, win=12000.0, hop=3000.0):
    """Per window: centre, bpm grid, beat scores (only windows with enough onsets)."""
    bpms = g_bpm * (1.003 ** np.arange(int(np.log(0.62) / np.log(1.003)), int(np.log(1.62) / np.log(1.003)) + 1))
    out = []
    t = start
    while t < end:
        sel = (times_ms >= t) & (times_ms < t + win)
        if sel.sum() >= 10:
            s = beat_score(times_ms[sel] / 1000.0, w[sel], bpms)
            out.append((t + win / 2, s))
        t += hop
    return bpms, out


def _score_at(bpms, s, bpm):
    """Best score of a tempo or its octave relatives in the window."""
    best = 0.0
    for m in (0.5, 1.0, 2.0):
        b = bpm * m
        if bpms[0] <= b <= bpms[-1]:
            i = int(np.argmin(np.abs(bpms - b)))
            best = max(best, float(s[max(0, i - 1):i + 2].max()))
    return best


_GLOBAL_OCTAVES: List[float] = []
OSU_BPM_LOW, OSU_BPM_HIGH = 95.0, 240.0


def osu_octave(b: float) -> float:
    """Move a tempo into the octave osu! maps are usually timed in. A half-time
    grid would leave no room for 1/8 notes (the grid only offers 1/4 and 1/3)."""
    while b < OSU_BPM_LOW and b * 2 <= OSU_BPM_HIGH:
        b *= 2
    while b > OSU_BPM_HIGH:
        b /= 2
    return b


def _fold(b: float) -> float:
    """Express a local tempo in the octave the whole-song analysis preferred."""
    for c in _GLOBAL_OCTAVES:
        for k in (-1, 1):
            if abs(np.log2(b / c) - k) < 0.02:
                return osu_octave(b / (2.0 ** k))
    return osu_octave(b)


def _local_best(bpms, s) -> float:
    return _fold(float(bpms[int(np.argmax(s * (0.35 + 0.65 * prior(bpms))))]))


def _initial_tempo(bpms, windows, g_bpm) -> float:
    """Tempo of the opening windows, expressed in the global tempo's octave if equivalent."""
    if len(windows) < 3:
        return g_bpm
    first = [_local_best(bpms, s) for _, s in windows[:3]]
    b = float(np.median(first))
    # if the global tempo explains the opening as well, keep it
    s0 = windows[0][1] + windows[1][1] + windows[2][1]
    if _score_at(bpms, s0, g_bpm) >= 0.8 * _score_at(bpms, s0, b):
        return g_bpm
    return b


def _change_points(bpms, windows, start_bpm, run=3, gain=1.3) -> List[Tuple[float, float]]:
    """Returns [(time, new_bpm)] where a different tempo clearly wins for `run` windows."""
    changes = []
    cur = start_bpm
    i = 0
    while i < len(windows):
        devs = []
        for j in range(i, min(len(windows), i + run)):
            _, s = windows[j]
            k = int(np.argmax(s * (0.35 + 0.65 * prior(bpms))))
            b = _fold(float(bpms[k]))
            if abs(np.log2(b / cur)) > 0.022 and min(abs(np.log2(b / cur) - o) for o in (-1, 1)) > 0.022 \
                    and s[k] > gain * _score_at(bpms, s, cur):
                devs.append(b)
            else:
                break
        if len(devs) == run and np.ptp(np.log2(devs)) < 0.02:
            new = float(np.median(devs))
            changes.append((windows[i][0], new))
            cur = new
            i += run
        else:
            i += 1
    return changes


def _refine_boundary(times_ms, w, a: GridFit, b: GridFit, est_ms, radius=8000.0) -> float:
    sel = (times_ms >= est_ms - radius) & (times_ms < est_ms + radius)
    t = times_ms[sel]
    ww = w[sel]
    beat_b = 60000.0 / b.bpm
    k0 = np.ceil((est_ms - radius - b.offset_ms) / beat_b)
    cands = b.offset_ms + beat_b * np.arange(k0, k0 + int(2 * radius / beat_b) + 1)

    def align(fit):
        # beats and half-beats only: finer harmonics alias between the two grids
        ph = 2 * np.pi * (t - fit.offset_ms) / (60000.0 / fit.bpm)
        return (np.cos(ph) + 0.5 * np.cos(2 * ph)) * ww

    ca, cb = align(a), align(b)
    best, best_c = -np.inf, est_ms
    for c in cands:
        s = ca[t < c].sum() + cb[t >= c].sum()
        if s > best:
            best, best_c = s, float(c)
    return best_c


def _residual_ms(times_ms, w, fit: GridFit, lo, hi, win=8000.0) -> float:
    """Worst windowed phase error of onsets against the grid (ms)."""
    worst = 0.0
    beat = 60000.0 / fit.bpm
    t = lo
    while t < hi:
        sel = (times_ms >= t) & (times_ms < min(hi, t + win))
        if sel.sum() >= 8:
            best = None
            for h, _ in HARMONIC_WEIGHTS:
                c = (w[sel] * np.exp(2j * np.pi * h * (times_ms[sel] - fit.offset_ms) / beat)).sum() / w[sel].sum()
                if best is None or abs(c) > abs(best[1]):
                    best = (h, c)
            h, c = best
            if abs(c) > 0.35:
                worst = max(worst, abs(np.angle(c) / (2 * np.pi) * beat / h))
        t += win
    return worst


def _fit_segment(times_ms, w, low, bpm0, lo, hi, depth=0) -> List[Tuple[float, float, GridFit]]:
    fit = fit_grid(times_ms, w, bpm0, lo, hi, low=low)
    res = _residual_ms(times_ms, w, fit, lo, hi)
    if depth < 3 and res > 15.0 and hi - lo > 40000:
        mid = (lo + hi) / 2
        left = _fit_segment(times_ms, w, low, fit.bpm, lo, mid, depth + 1)
        right = _fit_segment(times_ms, w, low, fit.bpm, mid, hi, depth + 1)
        worst_child = max(_residual_ms(times_ms, w, f, a, b) for a, b, f in left + right)
        if worst_child < res * 0.6:
            log.info("Split drifting segment %.0f-%.0f (residual %.1f ms -> %.1f ms)", lo, hi, res, worst_child)
            return left + right
    return [(lo, hi, fit)]


def _downbeat_phase(times_ms, w, low, fit: GridFit, lo, hi, meter=4) -> int:
    beat = 60000.0 / fit.bpm
    k0 = int(np.ceil((lo - fit.offset_ms) / beat))
    k1 = int(np.floor((hi - fit.offset_ms) / beat))
    if k1 - k0 < meter * 2:
        return k0 % meter
    beats = fit.offset_ms + beat * np.arange(k0, k1 + 1)
    idx = np.searchsorted(times_ms, beats)
    acc = np.zeros(meter)
    tol = min(45.0, beat * 0.12)
    for j, (bt, i) in enumerate(zip(beats, idx)):
        s = 0.0
        for ii in (i - 1, i):
            if 0 <= ii < len(times_ms) and abs(times_ms[ii] - bt) < tol:
                s = max(s, w[ii] * (0.4 + 1.6 * low[ii]))
        acc[(k0 + j) % meter] += s
    # first beat of the segment wins near-ties (music usually starts on a downbeat)
    acc[k0 % meter] *= 1.08
    return int(np.argmax(acc))


def detect_timing(times_ms: np.ndarray, weight: np.ndarray, low: np.ndarray,
                  music_start: float, music_end: float, duration_ms: float):
    """Returns (timing sections, global confidence, candidates, warnings).

    weight: per-onset fitting weight (OnsetPeaks.timing_weight).
    """
    warnings: List[str] = []
    order = np.argsort(times_ms)
    times_ms, w, low = times_ms[order], weight[order], low[order]
    inside = (times_ms >= music_start - 50) & (times_ms <= music_end + 50)
    t_in, w_in, low_in = times_ms[inside], w[inside], low[inside]
    if t_in.size < 8:
        raise ValueError("Too few rhythmic onsets were detected to establish a beat grid.")

    cands = global_candidates(t_in, w_in)
    g_bpm = osu_octave(cands[0][0])
    _GLOBAL_OCTAVES[:] = [osu_octave(b) for b, s in cands if s > 0.6 * cands[0][1]]

    bpms, windows = _window_scores(t_in, w_in, g_bpm, music_start, music_end)
    start_bpm = _initial_tempo(bpms, windows, g_bpm)
    changes = _change_points(bpms, windows, start_bpm)
    bounds = [music_start] + [c for c, _ in changes] + [music_end]
    seg_bpms = [start_bpm] + [b for _, b in changes]
    segs: List[Tuple[float, float, GridFit]] = []
    for (a, b), bpm0 in zip(zip(bounds[:-1], bounds[1:]), seg_bpms):
        segs.extend(_fit_segment(t_in, w_in, low_in, bpm0, a, b))

    # merge neighbouring segments whose tempo is effectively identical
    merged = [segs[0]]
    for lo, hi, fit in segs[1:]:
        plo, phi, pfit = merged[-1]
        if abs(fit.bpm / pfit.bpm - 1) < 0.004:
            joint = fit_grid(t_in, w_in, pfit.bpm, plo, hi, span=0.004, low=low_in)
            if _residual_ms(t_in, w_in, joint, plo, hi) < 15.0:
                merged[-1] = (plo, hi, joint)
                continue
        merged.append((lo, hi, fit))

    if len(cands) > 1 and len(merged) == 1:
        b2, s2 = cands[1]
        octave_related = min(abs(np.log2(b2 / g_bpm) - k) for k in (-1, 0, 1)) < 0.03 or \
            min(abs(np.log2(b2 / g_bpm) - np.log2(r)) for r in (1.5, 2 / 3)) < 0.03
        if s2 > 0.85 * cands[0][1] and not octave_related:
            warnings.append(f"Tempo is ambiguous: {g_bpm:.1f} vs {b2:.1f} BPM scored similarly; "
                            f"using {merged[0][2].bpm:.2f} BPM.")

    # align segment boundaries to the incoming grid and pick downbeats
    sections: List[TimingSection] = []
    starts = [merged[0][0]]
    for i in range(1, len(merged)):
        # refit the incoming grid away from the transition, then refine the switch point
        lo, hi, fit = merged[i]
        starts.append(_refine_boundary(t_in, w_in, merged[i - 1][2], fit, lo))
    for i, (lo, hi, fit) in enumerate(merged):
        beat = 60000.0 / fit.bpm
        seg_lo = starts[i]
        seg_hi = starts[i + 1] if i + 1 < len(merged) else music_end
        phase = _downbeat_phase(t_in, w_in, low_in, fit, seg_lo, seg_hi)
        if i == 0:
            # the downbeat at or before the first musical event
            # (music_start can read slightly early because loudness is smoothed)
            kb = int(np.floor((music_start - fit.offset_ms) / beat + 0.5))
            while kb % 4 != phase:
                kb -= 1
            offset = fit.offset_ms + beat * kb
            start = min(0.0, offset)
            db_phase = 0
        else:
            # the incoming grid's beat at the refined boundary; the bar phase is
            # kept separately so the switch happens exactly where the tempo changes
            kb = int(np.round((seg_lo - fit.offset_ms) / beat))
            offset = fit.offset_ms + beat * kb
            prev = sections[-1]
            if offset <= prev.offset_ms + prev.beat_ms:
                n = np.ceil((prev.offset_ms + prev.beat_ms - offset) / beat + 1e-9)
                offset += beat * n
                kb += int(n)
            db_phase = (phase - kb) % 4
            start = offset
        # osu! stores timing point offsets as whole milliseconds; build the grid from that value
        offset = float(round(offset))
        start = float(min(0.0, offset)) if i == 0 else offset
        sections.append(TimingSection(offset_ms=float(offset), beat_ms=beat, start_ms=float(start),
                                      end_ms=duration_ms, confidence=float(fit.strength),
                                      downbeat_phase=int(db_phase)))
    for a, b in zip(sections[:-1], sections[1:]):
        a.end_ms = b.start_ms
    sections[-1].end_ms = duration_ms

    weights = np.array([max(1.0, s.end_ms - max(s.start_ms, music_start)) for s in sections])
    conf = float(np.average([s.confidence for s in sections], weights=weights))
    if conf < 0.3:
        warnings.append(f"Low beat-grid confidence ({conf:.2f}); rhythm may be loosely timed "
                        "(live recording, rubato or very sparse percussion).")
    if len(sections) > 1:
        parts = []
        for prev, s in zip([None] + sections[:-1], sections):
            if prev is not None and abs(s.bpm - prev.bpm) < 0.05:
                parts.append(f"re-sync at {s.offset_ms / 1000:.1f}s (same {s.bpm:g} BPM, the beat drifts)")
            else:
                parts.append(f"{s.bpm:g} BPM from {max(0.0, s.offset_ms) / 1000:.1f}s")
        warnings.append("Multiple timing points: " + ", ".join(parts))
    log.info("Timing: %s (conf %.2f), candidates %s",
             [(round(s.bpm, 3), round(s.offset_ms, 1)) for s in sections], conf,
             [(round(b, 1), round(s, 3)) for b, s in cands])
    return sections, conf, cands, warnings
