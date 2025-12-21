# app/audio/filters.py
# Basic 3-band EQ Isolator with Linkwitz–Riley 24 dB/oct crossovers.
# - Low  : < 250 Hz (two cascaded Butterworth low-pass biquads)
# - Mid  : 250 Hz – 2.5 kHz (24 dB/oct HP @250 -> 24 dB/oct LP @2500)
# - High : > 2.5 kHz (two cascaded Butterworth high-pass biquads)
#
# Gains are in dB. Use ~-INF (<= -80 dB) for a "kill".
#
# NOTE: This is written for small callback block sizes (e.g., 256 frames).
# Python per-sample loops are fine at that size; for heavier DSP, consider Cython/Rust/C++.

from __future__ import annotations
import math
from typing import Tuple
import numpy as np


def _db_to_lin(db: float) -> float:
    """Convert dB to linear gain. Treat <= -80 dB as kill (0.0)."""
    if db <= -80.0 or not np.isfinite(db):
        return 0.0
    return 10.0 ** (db / 20.0)


# ----- Biquad (RBJ cookbook), Transposed Direct Form II for numerical stability -----

class Biquad:
    def __init__(self, b: Tuple[float, float, float], a: Tuple[float, float, float]):
        # Normalize by a0
        b0, b1, b2 = b
        a0, a1, a2 = a
        if a0 == 0.0:
            raise ValueError("a0 must not be zero")
        self.b0 = b0 / a0
        self.b1 = b1 / a0
        self.b2 = b2 / a0
        self.a1 = a1 / a0
        self.a2 = a2 / a0
        # State per channel (stereo)
        self.z1L = 0.0
        self.z2L = 0.0
        self.z1R = 0.0
        self.z2R = 0.0

    def reset(self):
        self.z1L = self.z2L = self.z1R = self.z2R = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        """Process stereo buffer shape (N, 2). Returns a new array."""
        if x.ndim != 2 or x.shape[1] != 2:
            raise ValueError("Expected stereo samples shaped (N, 2)")
        y = np.empty_like(x)
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2

        z1L, z2L = self.z1L, self.z2L
        z1R, z2R = self.z1R, self.z2R

        # Per-sample loop; with small audio blocks this is fine in Python.
        for n in range(x.shape[0]):
            xL = x[n, 0]
            outL = xL * b0 + z1L
            z1L = xL * b1 + z2L - a1 * outL
            z2L = xL * b2 - a2 * outL

            xR = x[n, 1]
            outR = xR * b0 + z1R
            z1R = xR * b1 + z2R - a1 * outR
            z2R = xR * b2 - a2 * outR

            y[n, 0] = outL
            y[n, 1] = outR

        self.z1L, self.z2L = z1L, z2L
        self.z1R, self.z2R = z1R, z2R
        return y


# ----- RBJ coefficient designers for LP/HP Butterworth 12 dB/oct (Q = 1/sqrt(2)) -----

def _rbj_lowpass(fc: float, sr: int, Q: float = 1 / math.sqrt(2)) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    w0 = 2.0 * math.pi * (fc / sr)
    cosw0 = math.cos(w0)
    sinw0 = math.sin(w0)
    alpha = sinw0 / (2.0 * Q)
    b0 = (1.0 - cosw0) * 0.5
    b1 = 1.0 - cosw0
    b2 = (1.0 - cosw0) * 0.5
    a0 = 1.0 + alpha
    a1 = -2.0 * cosw0
    a2 = 1.0 - alpha
    return (b0, b1, b2), (a0, a1, a2)

def _rbj_highpass(fc: float, sr: int, Q: float = 1 / math.sqrt(2)) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    w0 = 2.0 * math.pi * (fc / sr)
    cosw0 = math.cos(w0)
    sinw0 = math.sin(w0)
    alpha = sinw0 / (2.0 * Q)
    b0 = (1.0 + cosw0) * 0.5
    b1 = -(1.0 + cosw0)
    b2 = (1.0 + cosw0) * 0.5
    a0 = 1.0 + alpha
    a1 = -2.0 * cosw0
    a2 = 1.0 - alpha
    return (b0, b1, b2), (a0, a1, a2)


# ----- Linkwitz–Riley 24 dB/oct via two cascaded Butterworth biquads -----

class LR4Lowpass:
    def __init__(self, fc: float, sr: int):
        b, a = _rbj_lowpass(fc, sr)
        self.s1 = Biquad(b, a)
        self.s2 = Biquad(b, a)

    def reset(self):
        self.s1.reset()
        self.s2.reset()

    def process(self, x: np.ndarray) -> np.ndarray:
        return self.s2.process(self.s1.process(x))

class LR4Highpass:
    def __init__(self, fc: float, sr: int):
        b, a = _rbj_highpass(fc, sr)
        self.s1 = Biquad(b, a)
        self.s2 = Biquad(b, a)

    def reset(self):
        self.s1.reset()
        self.s2.reset()

    def process(self, x: np.ndarray) -> np.ndarray:
        return self.s2.process(self.s1.process(x))


# ----- EQ Isolator combining low/mid/high bands -----

class EQIsolator:
    """
    3-band isolator:
      - Low  (< low_cut Hz)  : LR4 low-pass
      - Mid  (low_cut..high_cut Hz): LR4 high-pass @ low_cut then LR4 low-pass @ high_cut
      - High (> high_cut Hz) : LR4 high-pass

    Gains are in dB (low_gain, mid_gain, high_gain).
    """
    def __init__(self, sr: int = 48000, low_cut: float = 250.0, high_cut: float = 2500.0):
        if not (0 < low_cut < high_cut < sr * 0.45):
            raise ValueError("Choose sensible crossover frequencies (0 < low_cut < high_cut < Nyquist).")
        self.sr = int(sr)
        self.low_cut = float(low_cut)
        self.high_cut = float(high_cut)

        self.low_gain_db = 0.0
        self.mid_gain_db = 0.0
        self.high_gain_db = 0.0

        # Filters: separate state for each band (do NOT share instances)
        self._lp_low  = LR4Lowpass(self.low_cut, self.sr)
        self._hp_mid  = LR4Highpass(self.low_cut, self.sr)
        self._lp_mid  = LR4Lowpass(self.high_cut, self.sr)
        self._hp_high = LR4Highpass(self.high_cut, self.sr)

    # ---- Public API ----

    def set_gains_db(self, low: float, mid: float, high: float):
        """Set per-band gains in dB (e.g., -INF..+6)."""
        self.low_gain_db = float(low)
        self.mid_gain_db = float(mid)
        self.high_gain_db = float(high)

    def set_sample_rate(self, sr: int):
        """Redesign filters for a new sample rate."""
        self.sr = int(sr)
        self._lp_low  = LR4Lowpass(self.low_cut, self.sr)
        self._hp_mid  = LR4Highpass(self.low_cut, self.sr)
        self._lp_mid  = LR4Lowpass(self.high_cut, self.sr)
        self._hp_high = LR4Highpass(self.high_cut, self.sr)

    def set_crossovers(self, low_cut: float, high_cut: float):
        """Change crossover frequencies and redesign filters."""
        if not (0 < low_cut < high_cut < self.sr * 0.45):
            raise ValueError("Choose sensible crossover frequencies (0 < low_cut < high_cut < Nyquist).")
        self.low_cut = float(low_cut)
        self.high_cut = float(high_cut)
        self.set_sample_rate(self.sr)

    def reset(self):
        self._lp_low.reset()
        self._hp_mid.reset()
        self._lp_mid.reset()
        self._hp_high.reset()

    def process(self, x: np.ndarray) -> np.ndarray:
        """Apply EQ to a stereo block (N, 2)."""
        if x.size == 0:
            return x
        # Split into bands (separate filter instances maintain proper state)
        low  = self._lp_low.process(x)
        mid  = self._lp_mid.process(self._hp_mid.process(x))
        high = self._hp_high.process(x)

        # Apply per-band linear gains
        gl = _db_to_lin(self.low_gain_db)
        gm = _db_to_lin(self.mid_gain_db)
        gh = _db_to_lin(self.high_gain_db)

        y = gl * low + gm * mid + gh * high
        # Ensure we don't clip too hard; engine will clip to [-1, 1] anyway
        return y
