# DJ App Skeleton (Python MVP)

Minimal one-deck DJ player skeleton to get you started. It plays audio, supports play/pause, seek,
and hot cue management. DSP (EQ/FX/time-stretch) is stubbed for later.

## Quickstart

1) Create and activate a virtual environment (recommended).
2) `pip install -r requirements.txt`
   - You also need FFmpeg on your system for `pydub` to read MP3/MP4/WEBM:
     - macOS: `brew install ffmpeg`
     - Ubuntu: `sudo apt-get install ffmpeg`
     - Windows: install from ffmpeg.org and add to PATH.
3) Run the app:
   ```bash
   python -m app.app
   ```

## Project layout

- `app/app.py` — entry point
- `app/audio/engine.py` — low-latency callback mixer engine (1 deck for now)
- `app/io/decode.py` — file decoding (via pydub/ffmpeg) to float32 PCM
- `app/ui/main.py` — PyQt6 GUI (Load, Play/Pause, Seek slider, Hot Cue 1..4)
- `app/analysis/beatgrid.py` — placeholder for BPM/beat detection
- `app/audio/filters.py` — placeholder for EQ/FX biquads

## Next steps
- Add waveform rendering (pre-render peak cache and draw in UI)
- Implement 3-band EQ in `filters.py` and call from `engine.py`
- Add a second deck and a crossfader
- Add Rubber Band or SoundTouch for time-stretch/key-lock
- Add MIDI/HID mapping via `python-rtmidi`
