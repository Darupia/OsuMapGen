"""Star-rating targeting."""

import pytest

from osumapgen import generator, serializer, star_rating
from osumapgen.pipeline import GenerationRequest, run


def stars_for(sa, target, knob):
    m = generator.generate(sa, target, "balanced", knob, 1)
    return star_rating.calculate(serializer.serialize(sa, m, serializer.Metadata("t", "a"), "audio.mp3")).stars


def test_knob_increases_difficulty(analysed):
    sa, _ = analysed("full")
    lo, mid, hi = (stars_for(sa, 4.0, k) for k in (0.0, 0.5, 1.0))
    assert lo < mid < hi


@pytest.mark.parametrize("target", [2.0, 3.0, 5.0])
def test_reachable_targets_hit_tolerance(song, out_dir, target):
    p, _ = song("full")
    res = run(GenerationRequest(mp3_path=str(p), stars=target, output_dir=str(out_dir)))
    assert res.ok, res.errors
    assert abs(res.estimated_stars - target) <= 0.5, res.warnings


def test_unreachable_high_target_is_reported_not_faked(song, out_dir):
    p, _ = song("short")
    res = run(GenerationRequest(mp3_path=str(p), stars=11.0, output_dir=str(out_dir)))
    assert res.ok                       # a valid, playable map is still exported
    assert not res.within_tolerance
    assert res.estimated_stars < 11.0
    assert any("musically reasonable" in w for w in res.warnings)
    text = open(res.osu_path, encoding="utf-8").read()
    assert "11" not in text.split("[Difficulty]")[1].split("[")[0]   # nothing fake written as a rating


def test_unreachable_low_target_is_reported(song, out_dir):
    p, _ = song("short")
    res = run(GenerationRequest(mp3_path=str(p), stars=0.5, output_dir=str(out_dir)))
    assert res.ok
    if not res.within_tolerance:
        assert any("simplest version" in w for w in res.warnings)
