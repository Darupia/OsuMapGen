"""Low-level signal features computed over the complete song.

Mel spectrogram is computed in chunks so memory stays bounded for long songs.
Frame i is centred at i * HOP samples.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage, signal

HOP = 256
N_FFT = 1024
N_MELS = 64
CHUNK_FRAMES = 4096

# Empirical latency of the flux peak relative to the true transient, measured
# on synthetic clicks (tests/test_timing_accuracy.py). Subtracted from onset times.
ONSET_LATENCY_MS = -11.0   # clicks alone measure -15 ms; drum hits (slower attack) about -10 ms


@dataclass
class Features:
    sr: int
    hop: int
    n_frames: int
    times_ms: np.ndarray        # frame centre times
    logmel: np.ndarray          # (N_MELS, n_frames) dB
    rms_db: np.ndarray          # loudness per frame relative to the song's p95 (dB)
    env: np.ndarray             # broadband spectral flux
    env_low: np.ndarray         # < ~200 Hz flux (kick / bass)
    env_mid: np.ndarray         # 200..3000 Hz flux
    env_high: np.ndarray        # > ~3000 Hz flux (snare / hats)
    mid_energy_db: np.ndarray   # mid-band energy for sustain detection
    local_ref: np.ndarray       # local loudness reference of env
    mfcc: np.ndarray            # (13, n_frames)

    @property
    def frame_ms(self) -> float:
        return self.hop / self.sr * 1000.0

    def frame_of(self, t_ms: float) -> int:
        return int(np.clip(round(t_ms / self.frame_ms), 0, self.n_frames - 1))


def mel_spectrogram(y: np.ndarray, sr: int, progress=None) -> np.ndarray:
    import librosa
    pad = N_FFT // 2
    ypad = np.concatenate([np.zeros(pad, np.float32), y.astype(np.float32), np.zeros(pad + N_FFT, np.float32)])
    n_frames = 1 + len(y) // HOP
    mel_fb = librosa.filters.mel(sr=sr, n_fft=N_FFT, n_mels=N_MELS, fmin=20.0, fmax=sr / 2)
    window = signal.get_window("hann", N_FFT).astype(np.float32)
    out = np.empty((N_MELS, n_frames), dtype=np.float32)
    for a in range(0, n_frames, CHUNK_FRAMES):
        b = min(n_frames, a + CHUNK_FRAMES)
        idx = (np.arange(a, b) * HOP)[:, None] + np.arange(N_FFT)[None, :]
        frames = ypad[idx] * window
        spec = np.abs(np.fft.rfft(frames, axis=1)) ** 2
        out[:, a:b] = (mel_fb @ spec.T).astype(np.float32)
        if progress:
            progress(b / n_frames)
    return out


def _flux(logmel: np.ndarray) -> np.ndarray:
    d = np.diff(logmel, axis=1, prepend=logmel[:, :1])
    return np.maximum(d, 0.0).mean(axis=0)


def compute(y: np.ndarray, sr: int, progress=None) -> Features:
    import librosa
    mel = mel_spectrogram(y, sr, progress)
    logmel = librosa.power_to_db(mel, ref=np.max(mel), top_db=90.0).astype(np.float32)
    n = logmel.shape[1]
    freqs = librosa.mel_frequencies(n_mels=N_MELS + 2, fmin=20.0, fmax=sr / 2)[1:-1]
    low = freqs < 200
    high = freqs > 3000
    mid = ~low & ~high

    env = _flux(logmel)
    env_low = _flux(logmel[low])
    env_mid = _flux(logmel[mid])
    env_high = _flux(logmel[high])

    power = mel.sum(axis=0) + 1e-12
    db = 10 * np.log10(power)
    db = ndimage.uniform_filter1d(db, size=5)
    ref_db = np.percentile(db, 95)
    rms_db = (db - ref_db).astype(np.float32)

    mid_power = mel[mid].sum(axis=0) + 1e-12
    mid_db = ndimage.uniform_filter1d(10 * np.log10(mid_power), size=3).astype(np.float32)

    frame_ms = HOP / sr * 1000.0
    win = max(5, int(round(4000 / frame_ms)))
    # local loudness reference for the onset envelope: high percentile over ~4 s
    dec = 8
    coarse = ndimage.maximum_filter1d(env, size=dec)[::dec]
    ref = ndimage.percentile_filter(coarse, percentile=95, size=max(3, win // dec))
    ref = np.repeat(ref, dec)[:n]
    floor = np.percentile(env, 95) * 0.15 + 1e-6      # do not amplify near-silence
    local_ref = np.maximum(ref, floor).astype(np.float32)

    mfcc = librosa.feature.mfcc(S=logmel, n_mfcc=13).astype(np.float32)
    times = np.arange(n) * frame_ms
    return Features(sr, HOP, n, times, logmel, rms_db, env, env_low, env_mid, env_high,
                    mid_db, local_ref, mfcc)


@dataclass
class OnsetPeaks:
    times_ms: np.ndarray
    strength: np.ndarray        # 0..1 relative to local loudness
    raw: np.ndarray             # raw flux height
    low: np.ndarray
    high: np.ndarray
    accent: np.ndarray          # unclipped strength relative to local loudness (keeps accents)
    glob: np.ndarray            # 0..1 strength relative to the whole song (quiet parts stay weak)

    @property
    def timing_weight(self) -> np.ndarray:
        """Accent-weighted, kick-favouring weights for beat-grid fitting."""
        return np.minimum(self.accent, 2.0) ** 2 * (0.6 + 0.8 * self.low)


def detect_onsets(f: Features) -> OnsetPeaks:
    norm = f.env / f.local_ref
    frame_ms = f.frame_ms
    w = max(1, int(round(30 / frame_ms)))
    avg = ndimage.uniform_filter1d(norm, size=max(3, int(round(120 / frame_ms))))
    is_max = norm == ndimage.maximum_filter1d(norm, size=2 * w + 1)
    cand = np.where(is_max & (norm > avg + 0.06) & (norm > 0.12) & (f.rms_db > -55))[0]
    # global accent: flux height against a song-wide reference rather than the local one
    global_ref = np.percentile(f.env[f.rms_db > -40], 90) if np.any(f.rms_db > -40) else 1.0
    # enforce minimum spacing of ~35 ms keeping the stronger peak
    keep = []
    min_gap = int(round(35 / frame_ms))
    for i in cand:
        if keep and i - keep[-1] < min_gap:
            if norm[i] > norm[keep[-1]]:
                keep[-1] = i
            continue
        keep.append(i)
    idx = np.array(keep, dtype=int)
    if idx.size == 0:
        return OnsetPeaks(*(np.zeros(0) for _ in range(7)))
    # parabolic interpolation for sub-frame precision
    left = f.env[np.maximum(idx - 1, 0)]
    mid = f.env[idx]
    right = f.env[np.minimum(idx + 1, f.n_frames - 1)]
    denom = left - 2 * mid + right
    delta = np.where(np.abs(denom) > 1e-9, 0.5 * (left - right) / denom, 0.0)
    delta = np.clip(delta, -0.5, 0.5)
    times = (idx + delta) * frame_ms - ONSET_LATENCY_MS
    total = f.env_low[idx] + f.env_mid[idx] + f.env_high[idx] + 1e-9
    return OnsetPeaks(
        times_ms=times,
        strength=np.clip(norm[idx], 0, 1.0),
        raw=f.env[idx],
        low=f.env_low[idx] / total,
        high=f.env_high[idx] / total,
        accent=norm[idx] * 0.5 + 0.5 * f.env[idx] / (global_ref + 1e-9),
        glob=np.clip(f.env[idx] / (global_ref + 1e-9), 0, 1),
    )
