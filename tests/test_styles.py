"""Each mapping style must produce a measurably different map at the same settings."""

import math

from osumapgen import generator


def _profile(sa, style):
    m = generator.generate(sa, 5.0, style, 0.8, 1)
    objs = [o for o in m.objects if o.kind != "spinner"]
    dists = [math.dist((a.x, a.y), (b.x, b.y)) for a, b in zip(objs, objs[1:])]
    return {
        "slider_ratio": m.stats["sliders"] / max(1, m.stats["objects"]),
        "stream_notes": m.stats["stream_notes"],
        "avg_dist": sum(dists) / max(1, len(dists)),
    }


def test_styles_are_distinct(analysed):
    sa, _ = analysed("full")
    prof = {s: _profile(sa, s) for s in ("simple", "stream", "jump", "tech", "slider")}
    assert prof["slider"]["slider_ratio"] >= prof["jump"]["slider_ratio"]          # human jump maps are slider-rich too
    assert prof["slider"]["slider_ratio"] > prof["stream"]["slider_ratio"]
    assert prof["stream"]["stream_notes"] > 3 * max(1, prof["jump"]["stream_notes"])
    assert prof["stream"]["stream_notes"] > prof["simple"]["stream_notes"]
    assert prof["jump"]["avg_dist"] > 1.5 * prof["stream"]["avg_dist"]
    assert prof["jump"]["avg_dist"] > prof["simple"]["avg_dist"]


def _run_lengths(sa, style, knob):
    m = generator.generate(sa, 6.0, style, knob, 1)
    runs, cur = [], 1
    for a, b in zip(m.objects, m.objects[1:]):
        if b.time_ms - a.time_ms <= 0.3 * 60000 / 150:       # 1/4 notes at the fixture's tempo or faster
            cur += 1
        else:
            if cur >= 4:
                runs.append(cur)
            cur = 1
    return runs


def test_stream_runs_are_long_and_varied(analysed):
    sa, _ = analysed("full")
    runs = _run_lengths(sa, "stream", 1.0)
    assert runs, "stream preset produced no streams"
    assert max(runs) > 5, "streams are stuck at burst length"
    assert len(set(runs)) >= 3, f"stream lengths are not varied: {sorted(set(runs))}"


def _longest_tap_stretch_s(sa, m):
    """Longest run of tapping with no rest: a rest is a gap of 1.5+ beats or a slider held a full beat."""
    beat = sa.timing[0].beat_ms
    sm = m.difficulty.slider_multiplier
    start = last_end = None
    hold = False
    best = 0.0
    for o in m.objects:
        if o.kind == "spinner":
            start = None
            continue
        end = o.end_time_ms if o.kind == "slider" else o.time_ms
        if start is None or hold or o.time_ms - last_end >= 1.5 * beat:
            if start is not None:
                best = max(best, last_end - start)
            start = o.time_ms
        hold = o.kind == "slider" and end - o.time_ms >= 0.97 * beat
        last_end = end
        if hold:
            best = max(best, o.time_ms - start)
            start = None
    if start is not None:
        best = max(best, last_end - start)
    return best / 1000.0


def test_tapping_stretches_are_capped(analysed):
    sa, _ = analysed("full")
    for style in ("stream", "jump", "tech", "mix"):
        m = generator.generate(sa, 6.0, style, 1.0, 1)
        assert _longest_tap_stretch_s(sa, m) <= 15.0, style
