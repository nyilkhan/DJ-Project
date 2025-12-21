# Placeholder for beat/BPM analysis using aubio/librosa/essentia later.
# Keep the API minimal so you can call it from the UI/import pipeline.

from dataclasses import dataclass
from typing import List

@dataclass
class BeatGrid:
    bpm: float
    beats: List[int]  # sample indices of beat onsets at the chosen sample rate

def analyze_beats(pcm, sr: int) -> BeatGrid:
    # TODO: implement using aubio or librosa
    return BeatGrid(bpm=120.0, beats=[])
