import threading
import math
from typing import Optional, Dict
import numpy as np
import sounddevice as sd
from .filters import EQIsolator

# Audio engine constants
SR = 48000
BLOCKSIZE = 256
CHANNELS = 2

class DeckState:
    def __init__(self):
        self.buffer: Optional[np.ndarray] = None  # (N, 2) float32
        self.frames: int = 0
        self.playhead: float = 0.0  # in frames
        self.rate: float = 1.0
        self.playing: bool = False
        self.eq = EQIsolator(sr=SR)
        self.hotcues: Dict[int, int] = {}  # hotcue index -> frame index

class AudioEngine:
    """Two-deck audio engine with equal-power crossfader."""
    def __init__(self, sr: int = SR):
        self.sr = sr
        self.deckA = DeckState()
        self.deckB = DeckState()
        self.lock = threading.RLock()
        self.stream: Optional[sd.OutputStream] = None

        # Mixer controls
        self.crossfader: float = 0.5  # 0.0 = full A, 1.0 = full B
        self.chanA: float = 1.0       # channel A fader (0..1), reserved for later UI
        self.chanB: float = 1.0       # channel B fader (0..1)

    # -------- public API: deck helpers --------
    def _deck(self, deck: str) -> DeckState:
        if deck.upper() == 'A':
            return self.deckA
        elif deck.upper() == 'B':
            return self.deckB
        else:
            raise ValueError("deck must be 'A' or 'B'")

    def load_pcm(self, deck: str, pcm: np.ndarray, sr: int):
        if sr != self.sr:
            raise ValueError(f"Sample rate {sr} != engine SR {self.sr}. Resample before load.")
        if pcm.ndim != 2 or pcm.shape[1] != CHANNELS:
            raise ValueError("PCM must be shape (N, 2)")
        with self.lock:
            d = self._deck(deck)
            d.buffer = pcm.astype(np.float32, copy=False)
            d.frames = pcm.shape[0]
            d.playhead = 0.0
            d.playing = False
            d.rate = 1.0
            d.hotcues.clear()
            d.eq.set_sample_rate(self.sr)

    def play(self, deck: str):
        with self.lock:
            self._deck(deck).playing = True
        self._ensure_stream()

    def pause(self, deck: str):
        with self.lock:
            self._deck(deck).playing = False

    def toggle_play(self, deck: str):
        with self.lock:
            d = self._deck(deck)
            d.playing = not d.playing
        self._ensure_stream()

    def seek_frames(self, deck: str, frame_index: int):
        with self.lock:
            d = self._deck(deck)
            if d.buffer is None:
                return
            d.playhead = float(np.clip(frame_index, 0, d.frames - 1))

    def set_rate(self, deck: str, rate: float):
        with self.lock:
            self._deck(deck).rate = float(rate)

    def get_position(self, deck: str) -> int:
        with self.lock:
            return int(self._deck(deck).playhead)

    def get_duration(self, deck: str) -> int:
        with self.lock:
            return int(self._deck(deck).frames)

    # Hot cues
    def set_hotcue(self, deck: str, idx: int):
        with self.lock:
            d = self._deck(deck)
            d.hotcues[idx] = int(d.playhead)

    def goto_hotcue(self, deck: str, idx: int):
        with self.lock:
            d = self._deck(deck)
            if idx in d.hotcues:
                d.playhead = float(d.hotcues[idx])

    # EQ (per deck)
    def set_eq(self, deck: str, low_db: float, mid_db: float, high_db: float):
        with self.lock:
            self._deck(deck).eq.set_gains_db(low_db, mid_db, high_db)

    # Mixer
    def set_crossfader(self, xf: float):
        """Set crossfader position in [0,1]. 0=A, 1=B."""
        xf = min(max(xf, 0.0), 1.0)
        with self.lock:
            self.crossfader = xf

    def set_channel_gain(self, deck: str, gain: float):
        gain = min(max(gain, 0.0), 1.0)
        with self.lock:
            if deck.upper() == 'A':
                self.chanA = gain
            elif deck.upper() == 'B':
                self.chanB = gain

    # -------- internal --------
    def _ensure_stream(self):
        if self.stream is None or not self.stream.active:
            self.stream = sd.OutputStream(
                channels=CHANNELS,
                samplerate=self.sr,
                blocksize=BLOCKSIZE,
                dtype='float32',
                callback=self._callback,
            )
            self.stream.start()

    def _render_deck(self, d: DeckState, frames: int) -> np.ndarray:
        out = np.zeros((frames, CHANNELS), dtype=np.float32)
        if d.buffer is not None and d.playing:
            start = int(d.playhead)
            end = min(start + frames, d.frames)
            if end > start:
                out[:(end-start), :] = d.buffer[start:end, :]
            # advance playhead
            d.playhead += frames * d.rate
            if d.playhead >= d.frames:
                d.playhead = d.frames - 1
                d.playing = False  # stop at end for now
            # Per-deck EQ
            out = d.eq.process(out)
        return out

    def _callback(self, outdata, frames, time, status):
        if status:
            print(status)
        with self.lock:
            a = self._render_deck(self.deckA, frames) * self.chanA
            b = self._render_deck(self.deckB, frames) * self.chanB

            # equal-power crossfader
            theta = self.crossfader * (math.pi / 2.0)
            gA = math.cos(theta)
            gB = math.sin(theta)
            mix = gA * a + gB * b

        outdata[:] = np.clip(mix, -1.0, 1.0)

    def close(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None
