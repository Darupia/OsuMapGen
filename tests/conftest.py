import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from synth import ensure_fixture  # noqa: E402

_analysis_cache = {}


@pytest.fixture(scope="session")
def fixture_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("fixtures")


@pytest.fixture(scope="session")
def song(fixture_dir):
    """song(name) -> (mp3 path, Rendered ground truth)."""
    def get(name):
        return ensure_fixture(name, fixture_dir)
    return get


@pytest.fixture(scope="session")
def analysed(song):
    """analysed(name) -> (SongAnalysis, Rendered); cached per session."""
    from osumapgen import analysis
    from osumapgen.infra import Progress

    def get(name):
        if name not in _analysis_cache:
            p, r = song(name)
            _analysis_cache[name] = (analysis.analyse(str(p), Progress()), r)
        return _analysis_cache[name]
    return get


@pytest.fixture
def out_dir(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d
