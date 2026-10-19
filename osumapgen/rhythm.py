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
                # onsets are normalised locally, so in calm sections a soft hi-hat scores as "strong":
                # there only weight (low end) or a higher level earns the off-beats
                strong = on >= 0.6 and s.intensity >= 0.3
                take = L >= 1.0 or (L >= 0.6 and strong) or (L >= 0.3 and on >= 0.9 and g.low > 0.3)
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


def _cap_bursts(sa: SongAnalysis, idx: List[int], P: SectionParams, rng_for, ends=None) -> List[int]:
    """Split 1/4 runs longer than the allowed burst length for their section. Stream presets cut runs on beat
    boundaries (5, 9, 13... notes, one beat apart) and report where each run ends in `ends`."""
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
        elif p.stream_fill:
            cap = p.max_burst              # stream presets keep every run the audio supports, whatever the level
        elif L < 3.2:
            cap = 5
        else:
            cap = int(round(5 + (p.max_burst - 5) * np.clip((L - 3.2) / 0.8, 0, 1)))
        cap = max(2, min(cap, p.max_burst))
        base_cap, rng = cap, rng_for(10_000 + s.index)
        if p.stream_fill and len(run) >= 5:
            _aligned_chunks(run, ticks, cap, L, rng, out, ends)
            return
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
_STREAM_LENGTHS = (5, 9, 13, 17, 21, 25, 29, 33, 41)      # whole beats of 1/4 notes plus the starting note


def _aligned_chunks(run: List[int], ticks, cap: int, L: float, rng, out: List[int], ends) -> None:
    """Cut one run of adjacent ticks into streams that start and end on a beat, with a one-beat gap between them."""
    n, k = len(run), 0
    while k < n:
        target = _vary_cap(cap, 10 ** 6, n - k, L, rng, _STREAM_LENGTHS)
        snap = ticks[run[k]].snap
        cand = [e for e in range(k + 2, min(n, k + target + snap)) if ticks[run[e]].sub == 0]
        e = min(cand, key=lambda x: abs((x - k + 1) - target)) if cand else n - 1
        out.extend(run[k:e + 1])
        if ends is not None and e - k + 1 >= 4:
            ends.add(run[e])
        k = e + snap


def _vary_cap(cap: int, max_burst: int, run_len: int, L: float, rng, lengths=_BURST_LENGTHS) -> int:
    """Pick this run's length from a spread of lengths up to the section's limit, so streams
    are not all the same size. Short runs and low levels are left alone."""
    if L < 2.0 or cap < 6 or run_len <= 3:
        return cap
    choices = [n for n in lengths if 3 <= n <= cap]
    if not choices:
        return cap
    w = np.array([1.0 + 0.35 * i for i in range(len(choices))])    # favour the longer end a little
    pick = choices[int(rng.choice(len(choices), p=w / w.sum()))]
    # do not leave a 1-2 note stub behind the split
    rest = run_len - pick
    return run_len if 0 < rest <= 2 and run_len <= cap else pick


def _beat_ms(sa: SongAnalysis, g: GridTick) -> float:
    return sa.timing[g.timing_index].beat_ms


def _dotted(sa: SongAnalysis, idx: List[int], P: SectionParams, rng_for) -> List[int]:
    """Technical presets: stretch some half-beat gaps to a dotted 3/4 beat, only where the audio has an onset
    on the later tick (so the note still lands on a real sound)."""
    ticks = sa.ticks
    out = list(idx)
    chosen = set(out)
    rng, rng_section = None, None
    for j in range(len(out) - 1):
        a, b = out[j], out[j + 1]
        ga, gb = ticks[a], ticks[b]
        s = sa.sections[ga.section_index]
        p = P.of(s.index)
        if not p.dotted_rate or s.is_break or b - a != 2 or ga.snap != 4 or gb.timing_index != ga.timing_index:
            continue
        if s.index != rng_section:
            rng, rng_section = rng_for(30_000 + s.index), s.index
        cand = a + 3
        nxt = out[j + 2] if j + 2 < len(out) else 10 ** 9
        if cand >= nxt or cand in chosen or cand >= len(ticks) or ticks[cand].timing_index != ga.timing_index:
            continue
        if ticks[cand].onset < max(0.2, 0.7 * gb.onset) or rng.random() >= p.dotted_rate:
            continue
        chosen.discard(b)
        chosen.add(cand)
        out[j + 1] = cand
    return out


def plan_rhythm(sa: SongAnalysis, P: SectionParams, sm: float, rng_for) -> List[RhythmEvent]:
    """rng_for(section_index) -> np.random.Generator (deterministic per section)."""
    ticks = sa.ticks
    ends: set = set()
    idx = _cap_bursts(sa, _dotted(sa, select_ticks(sa, P), P, rng_for), P, rng_for, ends)
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

    _end_sliders(sa, events, P, rng_for, ends)
    events = enforce_pacing(sa, events, P, sm, rng_for)
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
    kick_ticks = int(round(best_len * g.snap)) // 2
    if p.kick_chance and kick_ticks >= 1 and rng.random() < p.kick_chance:
        kick_ticks = min(kick_ticks, max(1, g.snap // 2))          # each slide at most half a beat
        best_len = kick_ticks / g.snap
        repeats = 2
    elif best_len >= 1.0 and L < 2.8 and rng.random() < p.slider_repeat:
        half = ticks[min(len(ticks) - 1, ev.tick_index + int(round(best_len / 2 * g.snap)))]
        if half.onset > 0.3:
            best_len /= 2
            repeats = 2
    ev.kind = "slider"
    ev.repeats = repeats
    ev.end_tick_index = ev.tick_index + int(round(best_len * g.snap))


def _end_sliders(sa: SongAnalysis, events: List[RhythmEvent], P: SectionParams, rng_for, ends: set) -> None:
    """Human stream maps usually finish a run with one small slider (a kick, a 3-slide or a short plain slider)
    that lands where the next group begins. Turn the last note of some runs into one."""
    ticks = sa.ticks
    rng, rng_section = None, None
    for i, ev in enumerate(events):
        if ev.tick_index not in ends or ev.kind != "circle":
            continue
        g = ticks[ev.tick_index]
        s = sa.sections[g.section_index]
        p = P.of(s.index)
        if not p.run_slider_end:
            continue
        if s.index != rng_section:
            rng, rng_section = rng_for(40_000 + s.index), s.index
        if rng.random() >= p.run_slider_end:
            continue
        nxt = events[i + 1] if i + 1 < len(events) else None
        room = 8
        if nxt is not None:
            if ticks[nxt.tick_index].timing_index != g.timing_index:
                continue
            room = nxt.tick_index - ev.tick_index
        # (ticks per slide, slides): kick, 3-slide, short plain; each must leave one tick of air before the next note
        variants = [v for v in ((1, 2), (1, 3), (2, 1)) if v[0] * v[1] + 1 <= room]
        if not variants:
            continue
        seg, repeats = variants[int(rng.choice(len(variants), p=np.array([0.2, 0.3, 0.5][:len(variants)]) /
                                                 sum([0.2, 0.3, 0.5][:len(variants)])))]
        last = ev.tick_index + seg * repeats
        if last >= len(ticks) or ticks[last].timing_index != g.timing_index or ticks[last].time_ms > sa.music_end_ms:
            continue
        ev.kind = "slider"
        ev.end_tick_index = ev.tick_index + seg
        ev.repeats = repeats
        ev.stream = False


def _event_end_ms(sa: SongAnalysis, ev: RhythmEvent) -> float:
    """Time the player is released: slider end including every slide."""
    ticks = sa.ticks
    if ev.kind == "slider":
        t0 = ticks[ev.tick_index].time_ms
        return t0 + (ticks[ev.end_tick_index].time_ms - t0) * ev.repeats
    if ev.kind == "spinner":
        return ticks[ev.end_tick_index].time_ms
    return ev.time_ms


def _make_breather(sa: SongAnalysis, ev: RhythmEvent, p: MapParams, sm: float, rng, after_fast: bool = False) -> bool:
    """Turn `ev` into a held slider (long, with slides) or a buzz slider (1/4-beat slides repeated).
    Returns False when the timing/grid does not allow it."""
    ticks = sa.ticks
    g = ticks[ev.tick_index]
    beat = _beat_ms(sa, g)
    snap = g.snap
    # beats of rest for the hands; after stream-speed tapping they get a longer one (about a second or more)
    target = float(rng.choice([3.0, 4.0, 4.0, 6.0] if after_fast else [1.5, 2.0, 2.0, 3.0]))
    if rng.random() < p.buzz_chance:
        seg, repeats = 1, int(np.clip(round(target * snap * 0.75), 4, 16))      # 1 tick per slide
    else:
        seg_beats = min(MAX_SLIDER_PX / (sm * 100.0), 1.0)
        seg = max(1, int(seg_beats * snap + 1e-6))
        repeats = max(1, int(round(target * snap / seg)))
    end = ev.tick_index + seg
    last = ev.tick_index + seg * repeats
    if last >= len(ticks) or ticks[last].timing_index != g.timing_index:
        return False
    if ticks[last].time_ms > sa.music_end_ms:
        return False
    ev.kind = "slider"
    ev.end_tick_index = end
    ev.repeats = repeats
    ev.stream = False
    return True


def enforce_pacing(sa: SongAnalysis, events: List[RhythmEvent], P: SectionParams, sm: float,
                   rng_for) -> List[RhythmEvent]:
    """Cap continuous tapping. A rest is a gap of a beat and a half or more, or a held slider of a full beat or more.
    When a stretch runs past its limit the next good spot (a bar start, if one is near) becomes a long
    or buzz slider and the notes it covers are dropped, so the player gets to breathe."""
    ticks = sa.ticks
    out: List[RhythmEvent] = []
    start = prev_end = None
    prev_hold = False
    limit = 12000.0
    recent: List[float] = []          # press times in the last second, for stream-speed tapping
    fast_start, fast_limit = None, 10000.0
    rng, rng_section = None, None
    pending: List[RhythmEvent] = list(events)
    i = 0
    while i < len(pending):
        ev = pending[i]
        i += 1
        g = ticks[ev.tick_index]
        s = sa.sections[g.section_index]
        p = P.of(s.index)
        if s.index != rng_section:
            rng, rng_section = rng_for(20_000 + s.index), s.index
        beat = _beat_ms(sa, g)
        t = ev.time_ms
        if ev.kind == "spinner":
            out.append(ev)
            start, prev_end, prev_hold = None, _event_end_ms(sa, ev), False
            continue
        if start is None or prev_hold or t - prev_end >= 1.5 * beat:
            start = t
            limit = p.max_tap_s * 1000.0 * float(rng.uniform(0.7, 1.0))
        recent.append(t)
        while recent and recent[0] <= t - 1000.0:
            recent.pop(0)
        if len(recent) >= 8:
            if fast_start is None:
                fast_start = t
                fast_limit = p.max_fast_tap_s * 1000.0 * float(rng.uniform(0.7, 1.0))
        else:
            fast_start = None
        # how far into its allowance the current stretch is (1.0 = at the limit), for either kind of tapping
        used = max((t - start) / limit, ((t - fast_start) / fast_limit) if fast_start is not None else 0.0)
        elapsed = used * limit
        nice = g.sub == 0 and g.beat_index % 4 == 0 and not ev.stream          # start of a bar, outside a stream
        ok = g.sub == 0 and not ev.stream
        convertible = ev.kind == "circle" or (ev.kind == "slider" and _event_end_ms(sa, ev) - t < 0.97 * beat)
        if convertible and not s.is_break and (
                (elapsed > 0.8 * limit and nice) or (elapsed > limit and ok) or elapsed > 1.3 * limit):
            if _make_breather(sa, ev, p, sm, rng, after_fast=fast_start is not None):
                end_ms = _event_end_ms(sa, ev)
                rest_until = end_ms + beat / g.snap                  # a quarter tick of air after the release
                while i < len(pending) and pending[i].time_ms < rest_until:
                    i += 1
                out.append(ev)
                start, prev_end, prev_hold = None, end_ms, True
                recent.clear()
                fast_start = None
                continue
        out.append(ev)
        prev_end = _event_end_ms(sa, ev)
        prev_hold = ev.kind == "slider" and (prev_end - t) >= 0.97 * beat
        if prev_hold:
            start = None
    return out


def _final_spinner(sa: SongAnalysis, events: List[RhythmEvent], p: MapParams):
    if not events or p.knob > 0.75:
        return
    last = events[-1]
    ticks = sa.ticks
    last_end = _event_end_ms(sa, last)
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
        prev_end = _event_end_ms(sa, ev) if ev.end_tick_index >= 0 else g.time_ms
        # hitsounds: finish on section/kiai starts, clap on accented backbeats, whistle on held notes
        hs = 0
        if new and (s.kiai or s.label == "chorus") and g.sub == 0 and g.beat_index % 4 == 0:
            hs |= 4
        elif g.sub == 0 and g.beat_index % 4 in (1, 3) and g.onset > 0.3 and g.high > 0.35 and s.intensity > 0.45:
            hs |= 8
        elif ev.kind == "slider" and g.sustain > 0.6 and g.sub == 0 and g.beat_index % 4 == 0:
            hs |= 2
        ev.hitsound = hs
