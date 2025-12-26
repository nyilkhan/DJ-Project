import numpy as np

def waveform_peaks(pcm: np.ndarray, samples_per_pixel: int = 512):
    """
    Return peaks array shape (N, 2): (min, max) for each block.
    """
    if pcm.ndim == 2:
        mono = pcm.mean(axis=1)
    else:
        mono = pcm

    # pad end so length is multiple of block
    length = len(mono)
    n_blocks = int(np.ceil(length / samples_per_pixel))
    padded = np.zeros(n_blocks * samples_per_pixel, dtype=mono.dtype)
    padded[:length] = mono

    peaks = padded.reshape(n_blocks, samples_per_pixel)
    return np.column_stack((peaks.min(axis=1), peaks.max(axis=1)))
