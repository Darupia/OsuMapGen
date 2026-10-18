"""Section, break and music-extent detection."""


def test_full_song_sections_follow_the_arrangement(analysed):
    sa, truth = analysed("full")
    starts = [s.start_ms for s in sa.sections]
    for t0, _, kind, _ in truth.segments_ms[1:]:
        assert min(abs(t0 - s) for s in starts) < 60000 / 140 * 4 + 1, f"no section boundary near {t0}"
    chorus = [s for s in sa.sections if s.start_ms >= 42000 and s.end_ms <= 70000]
    intro = sa.sections[0]
    assert chorus and chorus[0].intensity > intro.intensity + 0.4
    assert any(s.kiai for s in sa.sections)


def test_long_break_is_a_break(analysed):
    sa, truth = analysed("long_break")
    silence = next(s for s in truth.segments_ms if s[2] == "silence")
    brk = [s for s in sa.sections if s.is_break]
    assert brk, "silent stretch not detected as a break"
    assert brk[0].start_ms <= silence[0] + 500 and brk[0].end_ms >= silence[1] - 500


def test_quiet_intro_is_less_intense(analysed):
    sa, _ = analysed("quiet_intro")
    assert sa.sections[0].intensity < sa.sections[-1].intensity - 0.3


def test_trailing_silence_is_excluded(analysed):
    sa, truth = analysed("trailing_silence")
    music_end = truth.segments_ms[-1][1]
    assert abs(sa.music_end_ms - music_end) < 1500
    assert sa.audio.duration_ms - sa.music_end_ms > 10000


def test_whole_file_is_analysed(analysed):
    sa, truth = analysed("full")
    assert sa.analysed_ms >= sa.audio.duration_ms - 100
    assert sa.ticks[-1].time_ms >= sa.music_end_ms - 1000
