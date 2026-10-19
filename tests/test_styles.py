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
    assert prof["slider"]["slider_ratio"] > 2 * prof["jump"]["slider_ratio"]
    assert prof["slider"]["slider_ratio"] > prof["stream"]["slider_ratio"]
    assert prof["stream"]["stream_notes"] > 3 * max(1, prof["jump"]["stream_notes"])
    assert prof["stream"]["stream_notes"] > prof["simple"]["stream_notes"]
    assert prof["jump"]["avg_dist"] > 1.5 * prof["stream"]["avg_dist"]
    assert prof["jump"]["avg_dist"] > prof["simple"]["avg_dist"]
