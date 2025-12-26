import numpy as np
import librosa

def _normalize_half_double(bpm: float, lo: float = 80.0, hi: float = 170.0) -> float:
    """Fold BPM into a DJ-friendly range by doubling/halving."""
    if bpm <= 0 or not np.isfinite(bpm):
        return 0.0
    while bpm < lo:
        bpm *= 2.0
    while bpm > hi:
        bpm /= 2.0
    return float(bpm)

def estimate_bpm_dj(
    pcm: np.ndarray,
    sr: int,
    analyze_seconds: float = 75.0,
    start_offset_seconds: float = 15.0,
    target_sr: int = 22050,
    bpm_min: float = 60.0,
    bpm_max: float = 200.0,
) -> tuple[float, float, list[tuple[float, float]]]:
    """
    Returns:
      bpm_final, confidence(0..1-ish), candidates[(bpm, weight), ...] sorted best-first

    Strategy:
      - mono + resample
      - HPSS -> percussive component
      - onset strength -> tempogram
      - estimate tempo per segment -> aggregate with a weighted histogram
    """
    if pcm is None or pcm.size == 0:
        return 0.0, 0.0, []

    # mono
    y = pcm.mean(axis=1).astype(np.float32)

    # pick window: skip intro, analyze a chunk
    start = int(max(0.0, start_offset_seconds) * sr)
    end = int(min(len(y), start + analyze_seconds * sr))
    if end - start < int(5 * sr):
        start, end = 0, len(y)
    y = y[start:end]

    # resample for speed / stability
    if sr != target_sr:
        y = librosa.resample(y=y, orig_sr=sr, target_sr=target_sr)
        sr = target_sr

    # HPSS to emphasize drums
    y_harm, y_perc = librosa.effects.hpss(y)

    # onset envelope from percussive part
    hop_length = 512
    onset_env = librosa.onset.onset_strength(y=y_perc, sr=sr, hop_length=hop_length)

    # tempogram
    tg = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr, hop_length=hop_length)
    tempos = librosa.tempo_frequencies(tg.shape[0], sr=sr, hop_length=hop_length)

    # restrict tempo range
    mask = (tempos >= bpm_min) & (tempos <= bpm_max)
    if not np.any(mask):
        return 0.0, 0.0, []

    tg = tg[mask, :]
    tempos = tempos[mask]

    # segment-wise tempo votes
    # (using ~6s segments; adjust if you want)
    frames_per_seg = int((6.0 * sr) / hop_length)
    frames_per_seg = max(frames_per_seg, 8)

    hist = np.zeros_like(tempos, dtype=np.float64)

    n_frames = tg.shape[1]
    for s in range(0, n_frames, frames_per_seg):
        seg = tg[:, s:min(n_frames, s + frames_per_seg)]
        if seg.size == 0:
            continue
        # average tempogram energy in this segment
        seg_energy = np.mean(seg, axis=1)
        k = int(np.argmax(seg_energy))
        # weight by peak prominence vs mean (helps ignore weak/confused segments)
        peak = float(seg_energy[k])
        mean = float(np.mean(seg_energy)) + 1e-9
        weight = max(0.0, (peak / mean) - 1.0)
        hist[k] += weight

    if np.all(hist == 0):
        # fallback: use global mean tempogram
        global_energy = np.mean(tg, axis=1)
        k = int(np.argmax(global_energy))
        bpm = float(tempos[k])
        bpm = _normalize_half_double(bpm)
        return bpm, 0.2, [(bpm, 1.0)]

    # pick top candidates from histogram
    top_idx = np.argsort(hist)[::-1][:5]
    candidates = [(float(tempos[i]), float(hist[i])) for i in top_idx if hist[i] > 0]
    if not candidates:
        return 0.0, 0.0, []

    # normalize candidates into DJ range
    candidates_norm = [(_normalize_half_double(b), w) for (b, w) in candidates]

    # merge near-duplicates (e.g., 127.9 and 128.2)
    merged: dict[int, float] = {}
    for b, w in candidates_norm:
        key = int(round(b))  # 1 BPM bins
        merged[key] = merged.get(key, 0.0) + w

    merged_list = sorted(((float(k), float(v)) for k, v in merged.items()), key=lambda x: x[1], reverse=True)

    bpm_final, best_w = merged_list[0]
    total_w = sum(w for _, w in merged_list) + 1e-9
    confidence = float(best_w / total_w)

    return float(bpm_final), confidence, merged_list
