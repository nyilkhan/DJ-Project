from pydub import AudioSegment
from pydub.utils import which
import numpy as np

_FFMPEG = which("ffmpeg")

def _ensure_ffmpeg():
    if _FFMPEG is None:
        raise RuntimeError(
            "FFmpeg not found. Install it and ensure 'ffmpeg' is on your PATH.\n"
            "macOS: brew install ffmpeg\n"
            "Ubuntu: sudo apt-get install ffmpeg\n"
            "Windows: download from ffmpeg.org and add the /bin folder to PATH."
        )

def load_audio_to_pcm(path: str, target_sr: int = 48000):
    """Load an audio file (e.g., *.mp3) via FFmpeg/pydub and return float32 PCM (N, 2), sr.
    
    - Any format that FFmpeg can decode is supported (mp3, wav, m4a/aac, webm/opus, flac, ...).
    - Resamples to `target_sr` and ensures stereo. Values are normalized to [-1, 1].
    """
    _ensure_ffmpeg()
    seg = AudioSegment.from_file(path)
    if seg.frame_rate != target_sr:
        seg = seg.set_frame_rate(target_sr)
    if seg.channels == 1:
        seg = seg.set_channels(2)
    elif seg.channels > 2:
        # Take first two channels if multichannel
        chans = seg.split_to_mono()
        seg = AudioSegment.from_mono_audiosegments(chans[0], chans[1])
    # Convert to numpy float32
    samples = np.array(seg.get_array_of_samples()).astype(np.float32)
    samples /= float(1 << (8 * seg.sample_width - 1))
    samples = samples.reshape(-1, seg.channels)
    return samples, seg.frame_rate
