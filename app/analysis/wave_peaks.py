# app/analysis/wave_peaks.py
import numpy as np
from PyQt6.QtGui import QImage

def compute_peaks_image(pcm: np.ndarray, columns: int = 2000) -> QImage:
    """
    Returns 1px-high QImage (RGBA8888) width=columns.
    R=min, G=max (encoded 0..255) using mapping from -1..1 => 0..255
    """
    mono = pcm.mean(axis=1).astype(np.float32)
    n = len(mono)
    if n == 0:
        img = QImage(1, 1, QImage.Format.Format_RGBA8888)
        img.fill(0)
        return img

    # chunk size so we produce exactly `columns` samples
    step = max(1, n // columns)
    mins = []
    maxs = []
    for i in range(0, n, step):
        block = mono[i:i+step]
        mins.append(float(np.min(block)))
        maxs.append(float(np.max(block)))

    mins = np.array(mins, dtype=np.float32)
    maxs = np.array(maxs, dtype=np.float32)

    # normalize to 0..255
    def enc(x):
        x = np.clip(x, -1.0, 1.0)
        return ((x * 0.5 + 0.5) * 255.0).astype(np.uint8)

    r = enc(mins)
    g = enc(maxs)
    b = np.zeros_like(r, dtype=np.uint8)
    a = np.full_like(r, 255, dtype=np.uint8)

    rgba = np.stack([r, g, b, a], axis=1)  # (W,4)
    w = rgba.shape[0]

    img = QImage(rgba.data, w, 1, 4*w, QImage.Format.Format_RGBA8888)
    # important: copy so numpy buffer can be freed
    return img.copy()
