"""Map length option: choosing the part of the song, cutting the audio, and detail passes."""

import hashlib
import zipfile
from pathlib import Path

import numpy as np
import pytest

from osumapgen import audio_io, detail, length
from osumapgen.infra import UserFacingError
from osumapgen.model import HitObject
from osumapgen.pipeline import GenerationRequest, run


@pytest.mark.parametrize("text,secs", [("Full song", None), ("", None), (None, None), ("1:30 (TV size)", 90),
                                       ("2:00", 120), ("90", 90), ("1.5 min", 90), ("2 minutes", 120)])
def test_parse_length(text, secs):
    assert length.parse_length(text) == secs


@pytest.mark.parametrize("text", ["abc", "0:10", "5"])
def test_parse_length_rejects_bad_values(text):
    with pytest.raises(UserFacingError):
        length.parse_length(text)


def test_shorter_maps_get_more_detail():
    levels = [length.detail_level(s) for s in (60, 90, 120, 180, 240, 300)]
    assert levels == sorted(levels, reverse=True)
    assert levels[0] == 6 and levels[-1] == 1


def test_window_follows_sections_and_keeps_the_chorus(analysed):
    sa, truth = analysed("full")
    plan = length.choose_window(sa, 60)
    assert plan is not None
    assert 36 <= plan.length_s <= 84
    starts = {round(s.start_ms) for s in sa.sections} | {round(sa.music_start_ms)}
    ends = {round(s.end_ms) for s in sa.sections} | {round(sa.music_end_ms)}
    assert min(abs(plan.start_ms - x) for x in starts) <= 1
    assert min(abs(plan.end_ms - x) for x in ends) <= 1
    peak = max(s.intensity for s in sa.sections)
    assert any(s.intensity >= peak - 0.08 and s.end_ms > plan.start_ms and s.start_ms < plan.end_ms
               for s in sa.sections)


def test_no_cut_when_song_is_already_short(analysed):
    sa, _ = analysed("short")
    assert length.choose_window(sa, 90) is None


def test_cut_audio_is_aligned_and_fades(song, analysed, tmp_path):
    p, _ = song("full")
    sa, _ = analysed("full")
    plan = length.choose_window(sa, 60)
    cut = length.cut_audio(str(p), plan, tmp_path / "cut.mp3")
    y, sr = audio_io.decode(audio_io.probe(str(cut)))
    y0, _ = audio_io.decode(audio_io.probe(str(p)))
    assert abs(len(y) / sr * 1000 - (plan.cut_end_ms - plan.cut_start_ms)) < 150
    a = int(plan.cut_start_ms / 1000 * sr)
    ref, got = y0[a + sr: a + 3 * sr], y[sr: 3 * sr]            # same 2 s, one second into the cut
    lag = np.argmax(np.correlate(got, ref[: sr], mode="valid"))
    assert lag < 0.005 * sr                                      # within 5 ms of the original
    rms = lambda s: float(np.sqrt(np.mean(s ** 2)))
    assert rms(y[-int(0.3 * sr):]) < 0.3 * rms(y[len(y) // 2: len(y) // 2 + sr])


def test_section_quality_prefers_spread_notes():
    def notes(points):
        out = []
        for i, (x, y) in enumerate(points):
            o = HitObject(time_ms=1000 + 150 * i, kind="circle", x=x, y=y, pattern=f"p{i % 3}")
            o.end_x, o.end_y = x, y
            out.append(o)
        return out
    spread = notes([(100 + 60 * (i % 6), 100 + 40 * (i // 6) + (i % 2) * 30) for i in range(12)])
    clumped = notes([(250 + (i % 2) * 20, 190 + (i % 3) * 10) for i in range(12)])
    q = lambda objs: detail.section_quality(objs, 0, 10000, 4.0, 9.0)
    assert q(spread) > q(clumped)


def test_one_minute_map_end_to_end(song, out_dir):
    p, truth = song("full")
    before = hashlib.sha1(Path(p).read_bytes()).hexdigest()
    res = run(GenerationRequest(mp3_path=str(p), stars=4.0, output_dir=str(out_dir), length="1:00"))
    assert res.ok, res.errors
    assert abs(res.estimated_stars - 4.0) <= 0.5
    assert res.detail_level >= 5 and res.length_note.startswith("Mapped ")
    assert hashlib.sha1(Path(p).read_bytes()).hexdigest() == before          # source untouched
    with zipfile.ZipFile(res.osz_path) as z:
        z.extract("audio.mp3", out_dir / "x")
    dur = audio_io.probe(str(out_dir / "x" / "audio.mp3")).duration_ms
    assert 38000 <= dur <= 90000                                             # the cut, not the 2:47 song
    report = Path(res.report_path).read_text(encoding="utf-8")
    assert "Length:" in report and "versions of every section" in report


def test_length_longer_than_song_maps_whole_song(song, out_dir):
    p, _ = song("short")
    res = run(GenerationRequest(mp3_path=str(p), stars=3.0, output_dir=str(out_dir), length="1:30"))
    assert res.ok, res.errors
    assert res.length_note.startswith("Full song mapped")


def test_length_works_with_mapset(song, out_dir):
    p, _ = song("full")
    res = run(GenerationRequest(mp3_path=str(p), stars=4.0, output_dir=str(out_dir), length="1:00", mapset=True))
    assert res.ok, res.errors
    assert len(res.difficulties) >= 2 and res.length_note.startswith("Mapped ")
