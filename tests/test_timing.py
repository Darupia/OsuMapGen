"""Beat-grid accuracy against the exact beat times used to synthesise each fixture."""

import numpy as np
import pytest

from calibrate_latency import measure


def grid_error_ms(sa, beats_ms):
    """Distance of each true beat to the nearest grid beat or half-beat (allows octave choices)."""
    errs = []
    for b in beats_ms:
        ts = sa.timing_at(b)
        x = (b - ts.offset_ms) / ts.beat_ms
        errs.append(min(abs(x - round(x * d) / d) for d in (1, 2)) * ts.beat_ms)
    return np.array(errs)


@pytest.mark.parametrize("name", ["short", "full", "long", "long_break", "trailing_silence", "quiet_intro"])
def test_constant_tempo_grid_is_accurate(analysed, name):
    sa, truth = analysed(name)
    true_bpm = truth.segments_ms[0][3]
    assert len(sa.timing) == 1, f"unexpected tempo changes: {[t.bpm for t in sa.timing]}"
    assert sa.timing[0].bpm == pytest.approx(true_bpm, abs=0.05)
    err = grid_error_ms(sa, truth.beats_ms)
    assert np.max(err) < 6.0, f"max beat error {np.max(err):.1f} ms"


def test_tempo_change_detected_at_the_right_place(analysed):
    sa, truth = analysed("tempo_change")
    bpms = [round(t.bpm, 1) for t in sa.timing]
    assert bpms == [120.0, 150.0]
    change_true = truth.segments_ms[1][0]
    assert abs(sa.timing[1].offset_ms - change_true) <= 60000 / 150 * 0.5 + 5
    assert np.max(grid_error_ms(sa, truth.beats_ms)) < 6.0


def test_ambiguous_tempo_is_octave_consistent(analysed):
    sa, truth = analysed("ambiguous")
    ratio = sa.timing[0].bpm / 96.0
    assert min(abs(ratio - r) for r in (0.5, 1.0, 2.0)) < 0.002
    assert np.max(grid_error_ms(sa, truth.beats_ms)) < 6.0


def test_triplet_feel_lands_on_grid(analysed):
    sa, truth = analysed("triplet")
    # 110 BPM with triplet hats can legitimately be timed as 110 (1/3) or 165 (1/2)
    assert min(abs(sa.timing[0].bpm - b) for b in (110.0, 165.0, 220.0)) < 0.05
    ticks = np.array([g.time_ms for g in sa.ticks])
    hats = [b + k * (60000 / 110) / 3 for b in truth.beats_ms for k in range(3)]
    d = np.array([np.min(np.abs(ticks - h)) for h in hats])
    assert np.max(d) < 6.0


def test_onset_latency_calibration():
    e = measure()
    assert abs(np.median(e)) < 6.0
