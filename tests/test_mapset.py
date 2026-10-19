"""Full mapset: several difficulties from one analysis in one .osz."""

import json
import zipfile
from pathlib import Path

from osumapgen import analysis, pipeline, validator
from osumapgen.pipeline import GenerationRequest, mapset_targets, run, unique_versions, version_name


def test_spread_and_names():
    assert mapset_targets(5.6) == [2.0, 3.2, 4.4, 5.6]
    assert mapset_targets(7.0) == [2.0, 3.2, 4.4, 5.6, 7.0]
    assert mapset_targets(4.6) == [2.0, 3.2, 4.6]          # 4.4 is too close to the target
    assert mapset_targets(1.5) == [1.5]
    assert [version_name(x) for x in (1.8, 2.3, 3.3, 4.5, 5.8, 7.0)] == \
        ["Easy", "Normal", "Hard", "Insane", "Expert", "Expert+"]
    names = unique_versions([5.4, 6.1])
    assert len(set(names)) == 2 and all(n.startswith("Expert") for n in names)


def test_full_mapset_one_osz(song, out_dir, monkeypatch):
    calls = []
    real = analysis.analyse
    monkeypatch.setattr(analysis, "analyse", lambda *a, **k: calls.append(1) or real(*a, **k))
    p, _ = song("full")
    res = run(GenerationRequest(mp3_path=str(p), stars=5.6, output_dir=str(out_dir), mapset=True,
                                creator="Some_Player"))
    assert res.ok, res.errors
    assert len(calls) == 1                                   # analysed once for the whole set
    assert res.mapset and not res.skipped
    diffs = res.difficulties
    assert len(diffs) >= 4 and all(d.ok for d in diffs)
    est = [d.estimated_stars for d in diffs]
    assert est == sorted(est) and len(set(est)) == len(est), est
    assert len({d.version for d in diffs}) == len(diffs)

    with zipfile.ZipFile(res.osz_path) as z:
        names = z.namelist()
        osus = [n for n in names if n.endswith(".osu")]
        audio = [n for n in names if n.startswith("audio.")]
        texts = [z.read(n).decode("utf-8") for n in osus]
    assert len(osus) == len(diffs) >= 4
    assert audio == ["audio.mp3"]
    assert Path(res.osz_path).parent == Path(res.output_folder)
    versions = set()
    for t in texts:
        meta = validator.kv(validator.split_sections(t)["Metadata"])
        assert "BeatmapSetID:-1" in t and "AudioFilename: audio.mp3" in t
        assert meta["Creator"] == "Some_Player"
        versions.add(meta["Version"])
        rep = validator.validate_text(t, audio_dir=Path(res.output_folder))
        assert rep.ok, [str(i) for i in rep.errors]
    assert versions == {d.version for d in diffs}
    assert len({validator.kv(validator.split_sections(t)["Metadata"])["Title"] for t in texts}) == 1
    assert validator.validate_osz(Path(res.osz_path), {n: z_bytes for n, z_bytes in
                                  zip(osus, (t.encode("utf-8") for t in texts))}, None, "audio.mp3").ok

    report = Path(res.report_path).read_text(encoding="utf-8")
    for d in diffs:
        assert f"[{d.version}]" in report and d.version in report
    data = json.loads((Path(res.output_folder) / "report.json").read_text(encoding="utf-8"))
    assert data["mapset"] and len(data["difficulties"]) == len(diffs)
    assert all(d["valid"] and "requested_stars" in d and "estimated_lazer" in d for d in data["difficulties"])


def test_failed_difficulty_is_skipped_and_others_exported(song, out_dir, monkeypatch):
    real = validator.validate_text

    def flaky(text, *a, **k):
        rep = real(text, *a, **k)
        if "Version:Generated 2.0 Stars" in text:
            rep.error("test.forced", "forced failure for the easiest difficulty")
        return rep

    monkeypatch.setattr(pipeline.validator, "validate_text", flaky)
    p, _ = song("short")
    res = run(GenerationRequest(mp3_path=str(p), stars=4.4, output_dir=str(out_dir), mapset=True))
    assert res.ok, res.errors
    assert res.skipped and res.difficulties[0].version in res.skipped
    assert not res.difficulties[0].ok and all(d.ok for d in res.difficulties[1:])
    assert "SKIPPED" in res.message and res.skipped[0] in res.message
    with zipfile.ZipFile(res.osz_path) as z:
        osus = [n for n in z.namelist() if n.endswith(".osu")]
    assert len(osus) == len(res.difficulties) - len(res.skipped)
    assert any(f.name.startswith("INVALID DRAFT") for f in Path(res.output_folder).iterdir())
    assert "SKIPPED" in Path(res.report_path).read_text(encoding="utf-8")


def test_osz_validation_checks_every_osu(tmp_path):
    osz = tmp_path / "x.osz"
    with zipfile.ZipFile(osz, "w") as z:
        z.writestr("a.osu", b"osu file format v14\n[General]\nAudioFilename: audio.mp3\n[Metadata]\nVersion:Easy\n")
        z.writestr("b.osu", b"osu file format v14\n[General]\nAudioFilename: audio.mp3\n[Metadata]\nVersion:Easy\n")
        z.writestr("c.osu", b"garbage")
        z.writestr("audio.mp3", b"x" * 2048)
    rep = validator.validate_osz(osz, {"a.osu": z_read(osz, "a.osu")}, None, "audio.mp3")
    codes = {i.code for i in rep.errors}
    assert {"osz.version_duplicate", "osz.osu_unexpected", "osz.osu_header"} <= codes


def z_read(osz, name):
    with zipfile.ZipFile(osz) as z:
        return z.read(name)


def test_cli_mapset_flag(monkeypatch):
    from osumapgen import __main__ as cli
    seen = {}

    class Res:
        ok, message, style_breakdown, estimated_stars, warnings, errors = True, "ok", "", None, [], []
        difficulties, mapset, osz_path, report_path = [], True, None, None

    monkeypatch.setattr(pipeline, "run", lambda req, progress=None: seen.setdefault("req", req) and Res())
    assert cli.main(["song.mp3", "5", "--mapset"]) == 0
    assert seen["req"].mapset is True
