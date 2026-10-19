"""Click-track timing preview and album-art background."""

import shutil
import struct
import zipfile
import zlib
from pathlib import Path

import numpy as np
import pytest

from osumapgen import audio_io, preview, validator
from osumapgen.pipeline import GenerationRequest, run

SR = preview.PREVIEW_SR


def _png(w=4, h=4) -> bytes:
    """A real (tiny, solid pink) PNG built without any imaging library."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xe8\x64\x9a" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _with_art(src: Path, dest: Path, data: bytes, mime: str) -> Path:
    from mutagen.id3 import APIC, ID3, ID3NoHeaderError
    shutil.copyfile(src, dest)
    try:
        tags = ID3(str(dest))
    except ID3NoHeaderError:
        tags = ID3()
    tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
    tags.save(str(dest))
    return dest


def _load(path: Path) -> np.ndarray:
    if path.suffix == ".mp3":
        y, _ = audio_io.decode(audio_io.probe(str(path)), sr=SR)
        return y
    import soundfile as sf
    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    assert sr == SR
    return y.mean(axis=1)


def _rms(y, t_ms, lo_ms, hi_ms):
    a, b = int((t_ms + lo_ms) / 1000 * SR), int((t_ms + hi_ms) / 1000 * SR)
    seg = y[max(0, a):max(0, b)]
    return float(np.sqrt(np.mean(seg.astype(np.float64) ** 2))) if seg.size else 0.0


@pytest.fixture(scope="module")
def short_result(song, tmp_path_factory):
    p, _ = song("short")
    out = tmp_path_factory.mktemp("extras")
    return p, run(GenerationRequest(mp3_path=str(p), stars=3.5, output_dir=str(out)))


def test_preview_written_with_song_length_and_clicks(short_result):
    mp3, res = short_result
    assert res.ok, res.errors
    pv = Path(res.preview_path)
    assert pv.is_file() and pv.parent == Path(res.output_folder)
    assert pv.stem == "preview with clicks" and pv.suffix in (".mp3", ".wav")
    with zipfile.ZipFile(res.osz_path) as z:
        assert not any("preview" in n for n in z.namelist())

    y = _load(pv)
    song_y = _load(Path(mp3))
    assert abs(len(y) - len(song_y)) / SR < 0.15                    # whole song, same length

    # clicks: compare the preview against the original song in the same windows, so the drums
    # (which also sit on the beat) cancel out of the comparison
    text = Path(res.osu_path).read_text(encoding="utf-8")
    rep = validator.ValidationReport()
    objs = validator.parse_objects(validator.split_sections(text)["HitObjects"], rep)
    times = sorted(o.time for o in objs)
    near, between = [], []
    for a, b in zip(times[:-1], times[1:]):
        if b - a >= 200:
            near.append(_rms(y, a, -5, 30) / max(1e-6, _rms(song_y, a, -5, 30)))
            mid = (a + b) / 2
            between.append(_rms(y, mid, -15, 15) / max(1e-6, _rms(song_y, mid, -15, 15)))
    assert len(near) >= 5
    assert np.median(near) > 1.6 * np.median(between), (np.median(near), np.median(between))


def test_click_events_cover_slider_ends_and_combos():
    from osumapgen.model import HitObject
    objs = [HitObject(1000, "circle", 0, 0, new_combo=True),
            HitObject(1500, "slider", 0, 0, slides=2, end_time_ms=2500),
            HitObject(3000, "spinner", 256, 192, end_time_ms=4000)]
    ev = preview.click_events(objs)
    assert ev == [(1000.0, "combo"), (1500.0, "head"), (2000.0, "tail"), (2500.0, "tail"),
                  (3000.0, "head"), (4000.0, "tail")]


def test_no_art_means_no_background(short_result):
    _, res = short_result
    folder = Path(res.output_folder)
    assert res.background_path is None
    assert not list(folder.glob("background.*"))
    text = Path(res.osu_path).read_text(encoding="utf-8")
    assert validator.background_of(text) is None
    with zipfile.ZipFile(res.osz_path) as z:
        assert sorted(z.namelist()) == sorted([Path(res.osu_path).name, "audio.mp3"])


def test_cover_art_becomes_packaged_background(song, tmp_path):
    p, _ = song("short")
    art = _png()
    mp3 = _with_art(p, tmp_path / "with art.mp3", art, "image/png")
    assert audio_io.cover_art(str(mp3)) == (art, ".png")
    res = run(GenerationRequest(mp3_path=str(mp3), stars=3.0, output_dir=str(tmp_path / "out")))
    assert res.ok, res.errors
    folder = Path(res.output_folder)
    bg = folder / "background.png"
    assert res.background_path == str(bg) and bg.read_bytes() == art
    text = Path(res.osu_path).read_text(encoding="utf-8")
    assert '0,0,"background.png",0,0' in text
    with zipfile.ZipFile(res.osz_path) as z:
        assert z.read("background.png") == art
    assert "background.png" in Path(res.report_path).read_text(encoding="utf-8")

    # the validators notice a referenced background that is missing
    assert validator.validate_text(text, audio_dir=folder).ok
    bg.unlink()
    assert "background.missing" in [i.code for i in validator.validate_text(text, audio_dir=folder).errors]
    stripped = tmp_path / "no_bg.osz"
    with zipfile.ZipFile(res.osz_path) as src, zipfile.ZipFile(stripped, "w") as dst:
        for n in src.namelist():
            if n != "background.png":
                dst.writestr(n, src.read(n))
    osu_name = Path(res.osu_path).name
    orep = validator.validate_osz(stripped, osu_name, Path(res.osu_path).read_bytes(), "audio.mp3")
    assert "osz.background_missing" in [i.code for i in orep.errors]


def test_jpeg_cover_art_detected(song, tmp_path):
    p, _ = song("short")
    jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 200 + b"\xff\xd9"
    mp3 = _with_art(p, tmp_path / "jpg art.mp3", jpg, "image/jpeg")
    assert audio_io.cover_art(str(mp3)) == (jpg, ".jpg")
    assert audio_io.cover_art(str(p)) is None


def test_mapset_shares_background_and_writes_preview(song, tmp_path):
    p, _ = song("short")
    art = _png()
    mp3 = _with_art(p, tmp_path / "mapset art.mp3", art, "image/png")
    res = run(GenerationRequest(mp3_path=str(mp3), stars=4.4, output_dir=str(tmp_path / "out"), mapset=True))
    assert res.ok, res.errors
    assert Path(res.preview_path).is_file()
    with zipfile.ZipFile(res.osz_path) as z:
        names = z.namelist()
        assert z.read("background.png") == art
        osus = [n for n in names if n.endswith(".osu")]
        assert len(osus) >= 2
        assert all(validator.background_of(z.read(n).decode("utf-8")) == "background.png" for n in osus)
        assert not any("preview" in n for n in names)
