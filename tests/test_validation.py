"""Validator catches malformed maps; the generator's sanitizer prevents them."""

import pytest

from osumapgen import generator, serializer, validator
from osumapgen.model import HitObject

HEADER = """osu file format v14

[General]
AudioFilename: audio.mp3
Mode: 0

[Editor]
BeatDivisor: 4

[Metadata]
Title:T
TitleUnicode:T
Artist:A
ArtistUnicode:A
Creator:C
Version:V

[Difficulty]
HPDrainRate:5
CircleSize:4
OverallDifficulty:7
ApproachRate:8
SliderMultiplier:1.4
SliderTickRate:1

[Events]

[TimingPoints]
1000,500,4,2,0,60,1,0

[HitObjects]
"""


def codes(objects: str, duration=60000):
    rep = validator.validate_text(HEADER + objects, audio_duration_ms=duration)
    return {i.code for i in rep.errors}


def test_valid_minimal_map_passes():
    assert codes("100,100,1000,5,0,0:0:0:0:\n200,100,1500,1,0,0:0:0:0:\n") == set()


@pytest.mark.parametrize("objects,code", [
    ("100,100,1000,5,0\n100,100,1000,1,0\n", "object.order"),                        # duplicate time
    ("100,100,1500,5,0\n100,100,1000,1,0\n", "object.order"),                        # unsorted
    ("600,100,1000,5,0\n", "object.bounds"),                                         # off playfield
    ("100,100,1000,3,0\n", "object.type"),                                           # circle+slider bits
    ("100,100,abc,5,0\n", "object.syntax"),
    ("100,100,1000,6,0,P|150:150|200:100|250:150,1,140\n", "slider.points"),       # P needs 2 points
    ("100,100,1000,6,0,X|150:150,1,140\n", "slider.curve"),
    ("100,100,1000,6,0,L|200:100,1,-5\n", "slider.length"),
    ("100,100,1000,6,0,L|240:100,1,140\n200,100,1200,1,0\n", "object.overlap"),     # starts inside slider
    ("100,100,59900,6,0,L|240:100,1,140\n", "object.after_audio"),                  # ends after audio
    ("500,100,1000,6,0,L|700:100,1,200\n", "slider.bounds"),
    ("256,192,1000,12,0,900\n", "spinner.duration"),
])
def test_malformed_objects_are_rejected(objects, code):
    assert code in codes(objects)


def test_missing_section_and_bad_metadata():
    rep = validator.validate_text(HEADER.replace("[Editor]", "[Editr]") + "100,100,1000,5,0\n")
    assert "section.missing" in {i.code for i in rep.errors}
    rep = validator.validate_text(HEADER.replace("Title:T", "Title:日本") + "100,100,1000,5,0\n")
    assert "metadata.ascii" in {i.code for i in rep.errors}


def test_sanitizer_removes_structural_problems():
    objs = [
        HitObject(time_ms=1000, kind="slider", x=100, y=100, curve_type="L", curve_points=[(200, 100)],
                  length=100, end_time_ms=1400),
        HitObject(time_ms=1200, kind="circle", x=50, y=50),                 # inside the slider
        HitObject(time_ms=2000, kind="circle", x=900, y=-20),               # off playfield
        HitObject(time_ms=2000, kind="circle", x=10, y=10),                 # duplicate time
        HitObject(time_ms=9990, kind="slider", x=100, y=100, curve_type="L", curve_points=[(200, 100)],
                  length=100, end_time_ms=12000),                           # ends after the audio
    ]
    out = generator.sanitize(objs, duration_ms=10000)
    assert [o.time_ms for o in out] == [1000, 2000]
    assert 0 <= out[1].x <= 512 and 0 <= out[1].y <= 384
    assert out[0].new_combo


def test_generated_map_round_trips_through_validator(analysed):
    sa, _ = analysed("short")
    m = generator.generate(sa, 4.0, "balanced", 0.5, 7)
    text = serializer.serialize(sa, m, serializer.Metadata("t", "a"), "audio.mp3")
    rep = validator.validate_text(text, sa)
    assert rep.ok, [str(i) for i in rep.errors]
    assert rep.metrics["on_grid_pct"] == 100.0


def test_osz_validation_detects_missing_audio(tmp_path):
    import zipfile
    osz = tmp_path / "x.osz"
    with zipfile.ZipFile(osz, "w") as z:
        z.writestr("map.osu", b"data")
    rep = validator.validate_osz(osz, "map.osu", b"data", "audio.mp3")
    assert "osz.audio_missing" in {i.code for i in rep.errors}
