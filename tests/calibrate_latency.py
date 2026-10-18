"""Measure onset-detector latency on synthetic clicks (MP3 round trip).

Run:  python tests/calibrate_latency.py
Prints mean/median error between detected onset times and true click times.
The value is used as features.ONSET_LATENCY_MS.
"""

import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from synth import clicks, write_mp3  # noqa: E402
from osumapgen import audio_io, features  # noqa: E402


def measure() -> np.ndarray:
    rng = np.random.default_rng(3)
    times = np.cumsum(rng.uniform(0.18, 0.6, 120)) + 0.5
    audio = clicks(times, times[-1] + 1.0)
    with tempfile.TemporaryDirectory() as d:
        p = write_mp3(audio, Path(d) / "clicks.mp3")
        info = audio_io.probe(str(p))
        y, sr = audio_io.decode(info)
    f = features.compute(y, sr)
    on = features.detect_onsets(f)
    errs = []
    for t in times * 1000:
        i = np.argmin(np.abs(on.times_ms - t))
        errs.append(on.times_ms[i] - t)
    return np.array(errs)


if __name__ == "__main__":
    e = measure()
    print(f"n={len(e)} mean={e.mean():.2f}ms median={np.median(e):.2f}ms std={e.std():.2f}ms "
          f"max|e|={np.abs(e).max():.2f}ms (current ONSET_LATENCY_MS={features.ONSET_LATENCY_MS})")
