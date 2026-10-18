"""Invalid inputs and missing dependencies produce clear, handled errors."""

import builtins

import numpy as np
import pytest

from osumapgen import audio_io, deps, star_rating
from osumapgen.audio_io import InvalidAudioError
from osumapgen.infra import UserFacingError
from osumapgen.pipeline import GenerationRequest, run


def test_random_bytes_are_rejected(tmp_path):
    p = tmp_path / "noise.mp3"
    p.write_bytes(np.random.default_rng(0).integers(0, 256, 50000, dtype=np.uint8).tobytes())
    with pytest.raises(InvalidAudioError):
        run(GenerationRequest(mp3_path=str(p), stars=4.0, output_dir=str(tmp_path)))


def test_text_file_renamed_to_mp3(tmp_path):
    p = tmp_path / "notes.mp3"
    p.write_text("this is not audio\n" * 200)
    with pytest.raises(InvalidAudioError):
        audio_io.probe(str(p))


def test_empty_and_missing_files(tmp_path):
    p = tmp_path / "empty.mp3"
    p.write_bytes(b"")
    with pytest.raises(InvalidAudioError):
        audio_io.probe(str(p))
    with pytest.raises(InvalidAudioError):
        audio_io.probe(str(tmp_path / "missing.mp3"))


def test_wrong_extension(tmp_path):
    p = tmp_path / "song.wav"
    p.write_bytes(b"RIFF" + b"\0" * 4000)
    with pytest.raises(InvalidAudioError, match="Unsupported"):
        audio_io.probe(str(p))


def test_silent_mp3_is_rejected(tmp_path):
    from synth import write_mp3
    p = write_mp3(np.zeros(44100 * 5, dtype=np.float32), tmp_path / "silence.mp3")
    with pytest.raises(UserFacingError):
        run(GenerationRequest(mp3_path=str(p), stars=4.0, output_dir=str(tmp_path)))


def test_invalid_star_value(song, tmp_path):
    p, _ = song("short")
    with pytest.raises(UserFacingError):
        run(GenerationRequest(mp3_path=str(p), stars=50, output_dir=str(tmp_path)))


def test_decoding_without_ffmpeg_falls_back(song, monkeypatch):
    p, _ = song("short")
    info = audio_io.probe(str(p))
    y_ff, _ = audio_io.decode(info)
    monkeypatch.setattr(audio_io, "find_ffmpeg", lambda tool="ffmpeg": None)
    info2 = audio_io.probe(str(p))
    y_sf, _ = audio_io.decode(info2)
    assert info2.decoder == "soundfile"
    assert abs(len(y_sf) - len(y_ff)) / 22050 < 0.1


def test_missing_python_package_is_reported(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("rosu_pp_py"):
            raise ImportError("simulated")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    import importlib
    monkeypatch.setattr(importlib, "import_module",
                        lambda n, *a: (_ for _ in ()).throw(ImportError("simulated")) if n == "rosu_pp_py"
                        else real_import(n))
    rep = deps.check_dependencies()
    assert "rosu-pp-py" in rep.missing_modules and not rep.ok
    assert "Setup or Repair" in rep.describe()
    with pytest.raises(UserFacingError, match="Setup or Repair"):
        star_rating.calculate("osu file format v14")
