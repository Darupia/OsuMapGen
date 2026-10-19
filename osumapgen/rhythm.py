"""Rhythm planning: decide WHEN objects happen and what kind they are.

Works on the whole-song tick grid. Each tick has an onset strength (from the
audio) and a metrical weight. The section's intensity and the difficulty knob
give a "level":

  level < 1   : downbeats and half-bar beats (+ strong beats)
  level 1..2  : every beat, strong 1/2 off-beats
  level 2..3  : 1/2 rhythm following the music, 1/4 triples/bursts on strong onsets
  level 3..4+ : 1/4 bursts and streams where the music has continuous 1/4 onsets

Long gaps become sliders, preferably ending on a sound that was not given its
own circle, or on held (sustained) audio.
"""

from __future__ import annotations

from typing import List

import numpy as np

from .model import GridTick, RhythmEvent, Section, SongAnalysis
from .params import MapParams, SectionParams

MAX_SLIDER_PX = 290.0


def _tick_class(g: GridTick) -> str:
    if g.sub == 0:
        return "beat"
    if g.snap == 4:
        return "half" if g.sub == 2 else "quarter"
    return "trip"


def _phrase_pos(g: GridTick) -> int:
    """Bar index within a 4-bar phrase (0..3)."""
    return (g.beat_index // 4) % 4


def select_ticks(sa: SongAnalysis, P: SectionParams) -> List[int]:
    chosen: List[int] = []
    secs = sa.sections
    for i, g in enumerate(sa.ticks):
        s = secs[g.section_index]
        if s.is_break or g.time_ms < sa.music_start_ms - 30 or g.time_ms > sa.music_end_ms:
            continue
        L = P.of(s.index).level(s.intensity)
        c = _tick_class(g)
        bib = g.beat_index % 4
        on = g.onset
        phrase = _phrase_pos(g)
        take = False
        if c == "beat":
            if bib == 0:
                take = on > 0.05 or L >= 0.4 or g.sustain > 0.3
            elif bib == 2:
                take = L >= 0.45 or on >= 0.5
            else:
                take = L >= 1.0 or (L >= 0.6 and on >= 0.6) or (L >= 0.3 and on >= 0.9 and g.low > 0.3)
            if take and on < 0.05 and L < 1.3 and g.sustain < 0.2 and bib != 0:
                take = False
        elif c == "half":
            thr = float(np.clip(1.0 - 0.5 * (L - 1.0), 0.12, 2.0))
            take = on >= thr
        else:  # quarter / triplet
            qb = P.of(s.index).quarter_bias
            if L >= 2.2 - max(0.0, qb):
                thr = 1.2 - 0.5 * (L - 2.0) - (0.08 if c == "trip" else 0.0) - qb
                thr += {0: 0.2, 1: 0.1, 2: 0.0, 3: -0.12}[phrase]   # build density toward phrase ends
                take = on >= max(0.15, thr)
        if take:
            chosen.append(i)
    return _fill_streams(sa, chosen, P)


def _fill_streams(sa: SongAnalysis, chosen: List[int], P: SectionParams) -> List[int]:
    """Stream presets: bridge 1-2 missing 1/4 ticks next to an existing run so the music's
    continuous 1/4 passages become real streams instead of broken 3-5 note bursts."""
    ticks = sa.ticks
    have = set(chosen)
    out = set(chosen)
    for a, b in zip(chosen[:-1], chosen[1:]):
        if b - a not in (2, 3):
            continue
        ga, gb = ticks[a], ticks[b]
        s = sa.sections[ga.section_index]
        p = P.of(s.index)
        if not p.stream_fill or s.is_break or ga.timing_index != gb.timing_index or ga.snap != 4 or gb.snap != 4:
            continue
        if p.level(s.intensity) < 2.0:
            continue
        in_run = (a - 1) in have or (b + 1) in have
        if in_run:
            out.update(range(a + 1, b))
    return sorted(out)


def _cap_bursts(sa: SongAnalysis, idx: List[int], P: SectionParams, rng_for) -> List[int]:
    """Split 1/4 runs longer than the allowed burst length for their section."""
    if not idx:
        return idx
    ticks = sa.ticks
    out: List[int] = []
    run: List[int] = [idx[0]]

    def flush(run):
        if len(run) <= 2:
            out.extend(run)
            return
        s = sa.sections[ticks[run[0]].section_index]
        p = P.of(s.index)
        L = p.level(s.intensity)
        if L < (2.0 if p.stream_fill else 2.6):
            cap = 3
        elif L < 3.2 and not p.stream_fill:
            cap = 5
        elif L < 3.2:
            cap = int(round(5 + (p.max_burst - 5) * np.clip((L - 2.6) / 0.6, 0.0, 1.0) * 0.6)) if L >= 2.6 else 6
        elif p.stream_fill:
            cap = p.max_burst
        else:
            cap = int(round(5 + (p.max_burst - 5) * np.clip((L - 3.2) / 0.8, 0, 1)))
        cap = max(2, min(cap, p.max_burst))
        base_cap, rng = cap, rng_for(10_000 + s.index)
        cap = _vary_cap(base_cap, p.max_burst, len(run), L, rng)
        k = 0
        count = 0
        while k < len(run):
            out.append(run[k])
            count += 1
            if count >= cap and k + 1 < len(run):
                # drop the next off-beat tick to leave a 1/2 gap, then continue
                j = k + 1
                while j < len(run) and ticks[run[j]].sub == 0:
                    out.append(run[j])
                    j += 1
                k = j + 1
                count = 0
                cap = _vary_cap(base_cap, p.max_burst, len(run) - k, L, rng)
                continue
            k += 1

    for a, b in zip(idx[:-1], idx[1:]):
        adjacent = b == a + 1 and ticks[b].timing_index == ticks[a].timing_index
        if adjacent:
            run.append(b)
        else:
            flush(run)
            run = [b]
    flush(run)
    return sorted(set(out))


_BURST_LENGTHS = (3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32)


def _vary_cap(cap: int, max_burst: int, run_len: int, L: float, rng) -> int:
    """Pick this run's length from a spread of lengths up to the section's limit, so streams
    are not all the same size. Short runs and low levels are left alone."""
    if L < 2.0 or cap < 6 or run_len <= 3:
        return cap
    choices = [n for n in _BURST_LENGTHS if 3 <= n <= cap]
    if not choices:
        return cap
    w = np.array([1.0 + 0.35 * i for i in range(len(choices))])    # favour the longer end a little
    pick = choices[int(rng.choice(len(choices), p=w / w.sum()))]
    # do not leave a 1-2 note stub behind the split
    rest = run_len - pick
    return run_len if 0 < rest <= 2 and run_len <= cap else pick


def _beat_ms(sa: SongAnalysis, g: GridTick) -> float:
    return sa.timing[g.timing_index].beat_ms


def plan_rhythm(sa: SongAnalysis, P: SectionParams, sm: float, rng_for) -> List[RhythmEvent]:
    """rng_for(section_index) -> np.random.Generator (deterministic per section)."""
    ticks = sa.ticks
    idx = _cap_bursts(sa, select_ticks(sa, P), P, rng_for)
    if not idx:
        return []
    events: List[RhythmEvent] = []
    tick_times = np.array([g.time_ms for g in ticks])

    # stream membership: runs of >= 3 adjacent grid ticks
    stream = set()
    run = [idx[0]]
    for a, b in zip(idx[:-1], idx[1:]):
        if b == a + 1 and ticks[b].timing_index == ticks[a].timing_index:
            run.append(b)
        else:
            if len(run) >= 3:
                stream.update(run)
            run = [b]
    if len(run) >= 3:
        stream.update(run)

    rng, rng_section = None, None
    for n, i in enumerate(idx):
        g = ticks[i]
        s = sa.sections[g.section_index]
        if s.index != rng_section:
            rng, rng_section = rng_for(s.index), s.index
        p = P.of(s.index)
        L = p.level(s.intensity)
        emphasis = float(np.clip(g.onset * (0.5 + g.metric), 0, 1.5) / 1.5)
        ev = RhythmEvent(time_ms=g.time_ms, tick_index=i, kind="circle", stream=i in stream, emphasis=emphasis)
        nxt = idx[n + 1] if n + 1 < len(idx) else None
        if not ev.stream and nxt is not None:
            _maybe_slider(sa, ev, g, nxt, L, p, sm, rng, tick_times)
        events.append(ev)

    _final_spinner(sa, events, P.base)
    _combos_and_hitsounds(sa, events, P)
    return events


def _maybe_slider(sa, ev: RhythmEvent, g: GridTick, nxt: int, L: float, p: MapParams, sm: float,
                  rng, tick_times):
    ticks = sa.ticks
    beat = _beat_ms(sa, g)
    gn = ticks[nxt]
    if gn.timing_index != g.timing_index:
        return
    gap_beats = (gn.time_ms - g.time_ms) / beat
    if gap_beats < p.slider_min_gap:
        return
    rest = 0.5 if L < 1.5 else (1.0 / g.snap)
    max_len = min(gap_beats - rest, MAX_SLIDER_PX / (sm * 100.0), 2.0 if L < 1.5 else 1.5)
    if max_len < 0.24:
        return
    if (gn.time_ms - g.time_ms) > 0 and g.time_ms + max_len * beat > sa.music_end_ms:
        max_len = (sa.music_end_ms - g.time_ms) / beat - 0.05
        if max_len < 0.24:
            return
    step = 1.0 / g.snap
    lengths = [round(k * step, 6) for k in range(1, int(max_len / step + 1e-6) + 1)]
    # musically motivated end: an un-mapped onset, or the end of a held sound
    best_len, best_score = None, -1.0
    for d in lengths:
        if d < 0.49 and L < 2.5 and p.slider_min_gap >= 0.9:
            continue
        j = ev.tick_index + int(round(d * g.snap))
        if j >= len(ticks) or ticks[j].timing_index != g.timing_index:
            break
        end = ticks[j]
        score = 0.0
        if end.onset > 0.35:
            score += 0.6 + 0.4 * end.onset
        score += 0.35 * g.sustain
        score += 0.05 * d                 # gently prefer filling the gap
        if score > best_score:
            best_len, best_score = d, score
    if best_len is None:
        return
    chance = p.slider_rate * (0.35 + 0.65 * min(1.0, best_score))
    if L < 1.2 and gap_beats >= 2:
        chance = max(chance, 0.55)       # easy maps use sliders to fill long gaps
    chance = max(chance, p.slider_force)
    if rng.random() >= chance:
        return
    repeats = 1
    if best_len >= 1.0 and L < 2.8 and rng.random() < p.slider_repeat:
        half = ticks[min(len(ticks) - 1, ev.tick_index + int(round(best_len / 2 * g.snap)))]
        if half.onset > 0.3:
            best_len /= 2
            repeats = 2
    ev.kind = "slider"
    ev.repeats = repeats
    ev.end_tick_index = ev.tick_index + int(round(best_len * g.snap))


def _final_spinner(sa: SongAnalysis, events: List[RhythmEvent], p: MapParams):
    if not events or p.knob > 0.75:
        return
    last = events[-1]
    ticks = sa.ticks
    last_end = ticks[last.end_tick_index].time_ms if last.kind == "slider" else last.time_ms
    beat = _beat_ms(sa, ticks[last.tick_index])
    start = last_end + beat
    end = sa.music_end_ms - beat * 0.5
    if end - start < max(1500.0, 3 * beat):
        return
    # only if the tail holds sound (a sustained ending) rather than silence
    tail = [g for g in ticks if start <= g.time_ms <= end]
    if not tail or np.mean([g.sustain for g in tail]) < 0.35:
        return
    si = min(range(len(ticks)), key=lambda i: abs(ticks[i].time_ms - start))
    ei = min(range(len(ticks)), key=lambda i: abs(ticks[i].time_ms - end))
    if ei <= si:
        return
    events.append(RhythmEvent(time_ms=ticks[si].time_ms, tick_index=si, kind="spinner", end_tick_index=ei,
                              new_combo=True))


def _combos_and_hitsounds(sa: SongAnalysis, events: List[RhythmEvent], P: SectionParams):
    ticks = sa.ticks
    count = 0
    last_bar = None
    prev_section = None
    prev_end = -1e9
    for n, ev in enumerate(events):
        g = ticks[ev.tick_index]
        s = sa.sections[g.section_index]
        L = P.of(s.index).level(s.intensity)
        bar = (g.timing_index, g.beat_index // 4)
        bar_period = 2 if L < 1.0 else 1
        new = False
        if n == 0 or ev.kind == "spinner" or s.index != prev_section:
            new = True
        elif g.time_ms - prev_end > 4 * _beat_ms(sa, g):
            new = True                                      # after a long gap
        elif ev.stream and n > 0 and not events[n - 1].stream and count >= 3:
            new = True
        elif last_bar is not None and bar != last_bar and (bar[1] % bar_period == 0) and count >= 4 \
                and not (ev.stream and events[n - 1].stream and count < 16):
            new = True
        elif count >= 14 and g.sub == 0:
            new = True
        if new:
            count = 0
        ev.new_combo = new
        count += 1
        last_bar = bar
        prev_section = s.index
        prev_end = ticks[ev.end_tick_index].time_ms if ev.end_tick_index >= 0 else g.time_ms
        # hitsounds: finish on section/kiai starts, clap on accented backbeats, whistle on held notes
        hs = 0
        if new and (s.kiai or s.label == "chorus") and g.sub == 0 and g.beat_index % 4 == 0:
            hs |= 4
        elif g.sub == 0 and g.beat_index % 4 in (1, 3) and g.onset > 0.3 and g.high > 0.35 and s.intensity > 0.45:
            hs |= 8
        elif ev.kind == "slider" and g.sustain > 0.6 and g.sub == 0 and g.beat_index % 4 == 0:
            hs |= 2
        ev.hitsound = hs
