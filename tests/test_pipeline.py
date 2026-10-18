"""End-to-end generation on complete synthetic songs."""

import zipfile
from pathlib import Path

import pytest

from osumapgen import validator
from osumapgen.pipeline import GenerationRequest, run


def generate(song, name, stars, out_dir, style="Auto", **kw):
    p, truth = song(name)
    res = run(GenerationRequest(mp3_path=str(p), stars=stars, style=style, output_dir=str(out_dir), **kw))
    return res, truth


def parsed(res):
    text = Path(res.osu_path).read_bytes().decode("utf-8")
    rep = validator.ValidationReport()
    secs = validator.split_sections(text)
    objs = validator.parse_objects(secs["HitObjects"], rep)
    timing = validator.parse_timing(secs["TimingPoints"], rep)
    return text, secs, objs, timing


def test_full_length_song_end_to_end(song, analysed, out_dir):
    res, truth = generate(song, "full", 4.0, out_dir)
    assert res.ok, res.errors
    assert res.within_tolerance and abs(res.estimated_stars - 4.0) <= 0.5
    assert res.coverage_pct >= 97
    text, secs, objs, timing = parsed(res)
    sa, _ = analysed("full")
    beat = 60000 / 140
    # starts with the music and runs to its end
    assert objs[0].time <= truth.segments_ms[0][0] + 4 * beat
    last_end = max(max(o.end_time, o.time) for o in objs)
    assert last_end >= truth.segments_ms[-1][1] - 4 * beat
    # every non-break section has objects
    for s in sa.sections:
        if not s.is_break:
            assert any(s.start_ms <= o.time < s.end_ms for o in objs), f"empty section {s.label}"
    # intense sections are denser than calm ones
    def density(lo, hi):
        return sum(lo <= o.time < hi for o in objs) / (hi - lo)
    chorus = density(42343, 69771)
    intro = density(1200, 14914)
    assert chorus > intro * 1.5
    # one red line, standard structure, files present
    assert sum(1 for t in timing if t[4] == 1) == 1
    with zipfile.ZipFile(res.osz_path) as z:
        names = z.namelist()
    assert Path(res.osu_path).name in names and "audio.mp3" in names
    assert "AudioFilename: audio.mp3" in text
    assert Path(res.report_path).is_file()


def test_six_minute_song_is_mapped_to_the_end(song, out_dir):
    res, truth = generate(song, "long", 5.5, out_dir)
    assert res.ok, res.errors
    assert truth.segments_ms[-1][1] > 345000          # ~5:50 of music
    assert res.coverage_pct >= 97
    _, _, objs, _ = parsed(res)
    beat = 60000 / 174
    assert max(max(o.end_time, o.time) for o in objs) >= truth.segments_ms[-1][1] - 4 * beat
    assert abs(res.estimated_stars - 5.5) <= 0.5


def test_short_song(song, out_dir):
    res, _ = generate(song, "short", 3.0, out_dir)
    assert res.ok, res.errors
    assert abs(res.estimated_stars - 3.0) <= 0.5


def test_long_break_has_no_objects_and_a_break_period(song, out_dir):
    res, truth = generate(song, "long_break", 4.0, out_dir)
    assert res.ok, res.errors
    text, secs, objs, _ = parsed(res)
    s0, s1 = next((a, b) for a, b, k, _ in truth.segments_ms if k == "silence")
    assert not any(s0 + 200 < o.time < s1 - 200 for o in objs)
    assert any(line.startswith("2,") for line in secs["Events"])


def test_trailing_silence_not_mapped(song, out_dir):
    res, truth = generate(song, "trailing_silence", 4.0, out_dir)
    assert res.ok, res.errors
    _, _, objs, _ = parsed(res)
    music_end = truth.segments_ms[-1][1]
    assert max(max(o.end_time, o.time) for o in objs) <= music_end + 400
    assert max(o.time for o in objs) >= music_end - 3000


def test_tempo_change_map_has_two_red_lines(song, out_dir):
    res, _ = generate(song, "tempo_change", 4.5, out_dir)
    assert res.ok, res.errors
    _, _, objs, timing = parsed(res)
    reds = [t for t in timing if t[4] == 1]
    assert [round(60000 / t[1]) for t in reds] == [120, 150]
    assert any(o.time > reds[1][0] for o in objs) and any(o.time < reds[1][0] for o in objs)


def test_quiet_intro_is_mapped_lighter(song, out_dir):
    res, truth = generate(song, "quiet_intro", 4.5, out_dir)
    assert res.ok, res.errors
    _, _, objs, _ = parsed(res)
    split = truth.segments_ms[1][0]
    intro = sum(o.time < split for o in objs) / (split - truth.segments_ms[0][0])
    loud = sum(o.time >= split for o in objs) / (truth.segments_ms[1][1] - split)
    assert intro > 0 and loud > intro * 1.3


@pytest.mark.parametrize("style", ["Simple and readable", "Stream-focused", "Jump-focused", "Technical",
                                   "Slider-focused", "Balanced mix (all styles)"])
def test_styles_produce_valid_maps(song, out_dir, style):
    res, _ = generate(song, "short", 4.0, out_dir, style=style)
    assert res.ok, res.errors


def test_balanced_mix_varies_style_with_the_music(song, analysed, out_dir):
    from osumapgen.params import mix_styles
    sa, _ = analysed("full")
    styles = mix_styles(sa, 5.0)
    assert len(set(styles.values())) >= 3, styles
    for s in sa.sections:
        st = styles.get(s.index)
        if s.intensity < 0.4:
            assert st in ("slider", "simple"), (s.label, st)
        if s.intensity >= 0.75:
            assert st in ("stream", "jump", "tech", "balanced"), (s.label, st)
    res, _ = generate(song, "full", 5.0, out_dir, style="Balanced mix (all styles)")
    assert res.ok, res.errors
    assert res.style_used == "Mixed" and res.style_breakdown.startswith("Styles by section")
    assert abs(res.estimated_stars - 5.0) <= 0.5
    assert "style: " in Path(res.report_path).read_text(encoding="utf-8")


def test_generation_is_deterministic(song, out_dir):
    a, _ = generate(song, "short", 3.5, out_dir / "a")
    b, _ = generate(song, "short", 3.5, out_dir / "b")
    assert Path(a.osu_path).read_bytes() == Path(b.osu_path).read_bytes()


def test_unique_output_folders(song, out_dir):
    a, _ = generate(song, "short", 2.5, out_dir)
    b, _ = generate(song, "short", 2.5, out_dir)
    assert a.output_folder != b.output_folder
    assert Path(a.osz_path).is_file() and Path(b.osz_path).is_file()


def test_username_validation(song, out_dir):
    from osumapgen.infra import UserFacingError, check_username
    assert check_username("Peppy") == "" and check_username("") == ""
    assert check_username("ab") and check_username("this name is too long") and check_username("a@b!c")
    assert check_username(" Lead") and check_username("two  spaces")
    p, _ = song("short")
    with pytest.raises(UserFacingError, match="username"):
        run(GenerationRequest(mp3_path=str(p), stars=3.0, output_dir=str(out_dir), creator="no@good"))


def test_user_metadata_is_used(song, out_dir):
    res, _ = generate(song, "short", 3.0, out_dir, title="Test Song ★", artist="Synth Band")
    text = Path(res.osu_path).read_text(encoding="utf-8")
    assert "Title:Test Song" in text and "TitleUnicode:Test Song ★" in text
    assert "Artist:Synth Band" in text
