import sys
import os
from typing import Dict
from PyQt6 import QtWidgets, QtCore
import numpy as np
from pathlib import Path
import pyqtgraph as pg
from app.ui.qml import resources_rc


from app.audio.engine import AudioEngine, SR
from app.io.decode import load_audio_to_pcm
from app.analysis.beatgrid import estimate_bpm_dj
# from app.analysis.wave import waveform_peaks

from PyQt6.QtQml import QQmlEngine
from app.ui.waveform_provider import WaveImageProvider
from app.analysis.wave_peaks import compute_peaks_image
from app.ui.qml_waveform_widget import QmlWaveformWidget
import time



class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ App — Two Decks + Crossfader")
        self.engine = AudioEngine(sr=SR)

        # Waveform work
        self.beats_on_screen = 8  # how many beats visible in the scrolling window
        self.qml_engine = QQmlEngine()
        self.wave_provider = WaveImageProvider()
        self.qml_engine.addImageProvider("wave", self.wave_provider)
        self._wave_cache_bust = {"A": 0, "B": 0}

        # Track seeking flags per deck
        self.seeking = {'A': False, 'B': False}

        # Root layout
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        # Top: two decks side-by-side
        decks_layout = QtWidgets.QHBoxLayout()
        self.deck_widgets: Dict[str, Dict[str, QtWidgets.QWidget]] = {}
        decks_layout.addLayout(self._build_deck_ui('A'))
        decks_layout.addSpacing(20)
        decks_layout.addLayout(self._build_deck_ui('B'))
        root.addLayout(decks_layout)

        # Bottom: crossfader
        xf_group = QtWidgets.QGroupBox("Crossfader")
        xf_layout = QtWidgets.QVBoxLayout(xf_group)
        self.xf_label = QtWidgets.QLabel("A ◀──── 50% ────▶ B")
        self.xf_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.xf_slider.setMinimum(0)
        self.xf_slider.setMaximum(100)
        self.xf_slider.setValue(50)
        self.xf_slider.valueChanged.connect(self.on_crossfader_change)
        xf_layout.addWidget(self.xf_slider)
        xf_layout.addWidget(self.xf_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(xf_group)

        # Timer to update seek positions
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(50)  # 20 fps

        # Set base BPM levels
        self.base_bpm = {"A": 0.0, "B": 0.0}



    # ----- Deck UI builders -----
    def _build_deck_ui(self, deck: str) -> QtWidgets.QLayout:
        col = QtWidgets.QVBoxLayout()

        title = QtWidgets.QLabel(f"Deck {deck}")
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        col.addWidget(title, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        # Track label (shows the loaded file's name)
        track_label = QtWidgets.QLabel("No track loaded")
        track_label.setObjectName(f"trackLabel_{deck}")
        track_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        track_label.setStyleSheet("color: #666;")
        track_label.setWordWrap(True)
        col.addWidget(track_label)

        # BPMs
        bpm_base_label = QtWidgets.QLabel("Base BPM: --")
        bpm_cur_label  = QtWidgets.QLabel("BPM @ Rate: --")
        for lbl in (bpm_base_label, bpm_cur_label):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        col.addWidget(bpm_base_label)
        col.addWidget(bpm_cur_label)


        # Load & Play
        btn_row = QtWidgets.QHBoxLayout()
        load_btn = QtWidgets.QPushButton("Load")
        play_btn = QtWidgets.QPushButton("Play/Pause")
        load_btn.clicked.connect(lambda: self.on_load(deck))
        play_btn.clicked.connect(lambda: self.engine.toggle_play(deck))
        btn_row.addWidget(load_btn); btn_row.addWidget(play_btn)
        col.addLayout(btn_row)

        # Rate (vertical)
        rate_group = QtWidgets.QGroupBox("Rate")
        rgl = QtWidgets.QVBoxLayout(rate_group)
        rate_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        rate_slider.setMinimum(90); rate_slider.setMaximum(110); rate_slider.setValue(100)
        rate_label = QtWidgets.QLabel("1.00x")
        rate_slider.valueChanged.connect(lambda v: self.on_rate_change(deck, v))
        rgl.addWidget(rate_slider, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        rgl.addWidget(rate_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        # Volume (vertical)
        vol_group = QtWidgets.QGroupBox("Volume")
        vgl = QtWidgets.QVBoxLayout(vol_group)
        vol_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        vol_slider.setMinimum(0)
        vol_slider.setMaximum(100)
        vol_slider.setValue(100)  # start at full volume
        vol_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksRight)
        vol_label = QtWidgets.QLabel("100%")
        vol_slider.valueChanged.connect(lambda v: self.on_volume_change(deck, v))
        vgl.addWidget(vol_slider, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        vgl.addWidget(vol_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)


        # EQ (vertical sliders)
        eq_group = QtWidgets.QGroupBox("EQ (dB)")
        eql = QtWidgets.QHBoxLayout(eq_group)
        low_label, low_slider  = self._make_vslider("Low", -80, 10, 0, lambda: self.on_eq_change(deck))
        mid_label, mid_slider  = self._make_vslider("Mid", -80, 10, 0, lambda: self.on_eq_change(deck))
        high_label, high_slider = self._make_vslider("High", -80, 10, 0, lambda: self.on_eq_change(deck))
        for label, slider in [(low_label, low_slider), (mid_label, mid_slider), (high_label, high_slider)]:
            v = QtWidgets.QVBoxLayout()
            v.addWidget(slider, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
            v.addWidget(label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
            eql.addLayout(v)

        # Put rate + volume + EQ side by side
        top_row = QtWidgets.QHBoxLayout()
        top_row.addWidget(rate_group)
        top_row.addWidget(vol_group) 
        top_row.addWidget(eq_group)
        col.addLayout(top_row)

        # Seek slider
        seek_label = QtWidgets.QLabel("Seek")
        seek_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        seek_slider.setMinimum(0); seek_slider.setMaximum(0); seek_slider.setEnabled(False)
        seek_slider.sliderPressed.connect(lambda: self._on_seek_pressed(deck))
        seek_slider.sliderReleased.connect(lambda: self._on_seek_released(deck))
        col.addWidget(seek_label)
        col.addWidget(seek_slider)

        # Hot cues 1..4
        cues = QtWidgets.QGridLayout()
        for i in range(1, 5):
            set_btn = QtWidgets.QPushButton(f"Set CUE {i}")
            go_btn = QtWidgets.QPushButton(f"Go CUE {i}")
            set_btn.clicked.connect(lambda _, n=i: self.engine.set_hotcue(deck, n))
            go_btn.clicked.connect(lambda _, n=i: self.engine.goto_hotcue(deck, n))
            cues.addWidget(set_btn, 0, i-1)
        # row 2
        for i in range(1, 5):
            go_btn = QtWidgets.QPushButton(f"Go CUE {i}")
            go_btn.clicked.connect(lambda _, n=i: self.engine.goto_hotcue(deck, n))
            cues.addWidget(go_btn, 1, i-1)
        col.addLayout(cues)

        wave = QmlWaveformWidget(self.qml_engine)
        qml_path = os.path.abspath("app/ui/qml/WaveformView.qml")
        wave.set_source(qml_path)
        # FORCE a visible height
        wave.setMinimumHeight(120)
        wave.setMaximumHeight(180)

        # Optional but helpful during debugging
        wave.setStyleSheet("background-color: #222;")

        col.addWidget(wave)

        # wave_plot = pg.PlotWidget(
        #     background="#111",
        #     enableMenu=False,
        # )
        # wave_plot.setMouseEnabled(x=False, y=False)
        # wave_plot.hideAxis('left')   # no left axis
        # wave_plot.hideAxis('bottom') # no bottom axis
        # col.addWidget(wave_plot)

        # # Playhead line
        # playhead = pg.InfiniteLine(
        #     pos=0,
        #     angle=90,
        #     pen=pg.mkPen('y', width=2)
        # )
        # wave_plot.addItem(playhead)
       


        # Store widgets for this deck
        self.deck_widgets[deck] = {
            "rate_slider": rate_slider, "rate_label": rate_label,
            "vol_slider": vol_slider,   "vol_label": vol_label,
            "low_slider": low_slider, "low_label": low_label,
            "mid_slider": mid_slider, "mid_label": mid_label,
            "high_slider": high_slider, "high_label": high_label,
            "seek_slider": seek_slider,
            "track_label": track_label,
            "bpm_base_label": bpm_base_label, "bpm_cur_label": bpm_cur_label,
            "beat_lines":[],
            "wave_peaks":None,
            "wave_widget":wave,
        }
        self.engine.set_channel_gain(deck, 1.0)


        return col

    def _make_vslider(self, text, min_v, max_v, init_v, on_change_cb):
        label = QtWidgets.QLabel(f"{text}: {init_v} dB" if text != "Rate" else f"{init_v}")
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        slider.setMinimum(min_v); slider.setMaximum(max_v); slider.setValue(init_v)
        slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksRight)
        slider.valueChanged.connect(on_change_cb)
        return label, slider

    # ----- Event handlers -----
    def on_load(self, deck: str):
        dlg = QtWidgets.QFileDialog(self, f"Select audio file for Deck {deck}")
        dlg.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
        if dlg.exec():
            path = dlg.selectedFiles()[0]
            try:
                pcm, sr = load_audio_to_pcm(path, target_sr=SR)
                self.engine.load_pcm(deck, pcm, sr)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Load error", str(e))
                return
            w = self.deck_widgets[deck]
            w["seek_slider"].setEnabled(True)
            w["seek_slider"].setMinimum(0)
            w["seek_slider"].setMaximum(len(pcm)-1)
            w["seek_slider"].setValue(0)
            name = Path(path).name
            w["track_label"].setText(name)
            w["track_label"].setToolTip(path)
           

            bpm, conf, cands = estimate_bpm_dj(pcm, sr)
            if bpm > 0:
                self.base_bpm[deck] = float(bpm)
                w["bpm_base_label"].setText(f"Base BPM: {bpm:.1f}")
            else:
                w["bpm_label"].setText("BPM: --")
            self._update_bpm_display(deck)

            img = compute_peaks_image(pcm, columns=2500)
            self.wave_provider.set_image(f"deck{deck}", img)
            print("wave img", deck, img.width(), img.height(), img.isNull())


            # cache-bust to force QML Image reload
            self._wave_cache_bust[deck] += 1
            src = f"image://wave/deck{deck}?cache={self._wave_cache_bust[deck]}"

            root = self.deck_widgets[deck]["wave_widget"].root()
            # print("QML root:", root, "has waveTexSource?", root.property("waveTexSource"))
            root.setProperty("waveTexSource", src)
            print("setting waveTexSource to:", src)
            print("waveTexSource after:", root.property("waveTexSource"))

            root.setProperty("playhead", 0.0)

        
            # ----->>>>>  OLD WAY OF DOING THE WAVEFORM   <<<<<<<<<<<<--------------------------------
            # peaks = waveform_peaks(pcm, samples_per_pixel=512)
            # w["wave_peaks"] = peaks
            # x = np.arange(len(peaks))
            # transparent_pen = pg.mkPen((0, 0, 0, 0))


            # # Waveform drawing 
            # plot_item = w["wave_plot"].getPlotItem()
            # plot_item.clear()
            # x = np.arange(len(peaks))
            # mins = peaks[:, 0]
            # maxs = peaks[:, 1]
            # # Plot max and fill to mins (one "combined" waveform)
            # curve_max = plot_item.plot(x, maxs, pen=transparent_pen)
            # curve_min = plot_item.plot(x, mins, pen=transparent_pen)
            # fill = pg.FillBetweenItem(curve_max, curve_min,brush=pg.mkBrush(80, 160, 255, 120))
            # plot_item.addItem(fill)
            # # ensure the view is sane
            # plot_item.setYRange(-1.0, 1.0, padding=0.0)
            # plot_item.setXRange(0, len(peaks), padding=0.0)

            # --- playhead (create once, reuse thereafter) ---
            # if "playhead_line" not in w or w["playhead_line"] is None:
            #     w["playhead_line"] = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen('y', width=2))
            #     w["wave_plot"].addItem(w["playhead_line"])
            # else:
            #     w["playhead_line"].setValue(0)


            # for line in w["beat_lines"]:
            #     w["wave_plot"].removeItem(line)
            # w["beat_lines"].clear()

            # draw beat grid STIL NEED TO FIGURE OUT
            # total_frames = len(pcm)
            # for beat_frame in beat_frames:  # however you store them
            #     idx = int((beat_frame / total_frames) * len(w["wave_peaks"]))
            #     line = pg.InfiniteLine(
            #         pos=idx,
            #         angle=90,
            #         pen=pg.mkPen('#ffaa00', width=1)
            #     )
            #     w["wave_plot"].addItem(line)
            #     w["beat_lines"].append(line)


    def on_rate_change(self, deck: str, val: int):
        rate = val / 100.0
        self.engine.set_rate(deck, rate)
        self.deck_widgets[deck]["rate_label"].setText(f"{rate:.2f}x")
        self._update_bpm_display(deck)

    def on_eq_change(self, deck: str):
        w = self.deck_widgets[deck]
        low = int(w["low_slider"].value())
        mid = int(w["mid_slider"].value())
        high = int(w["high_slider"].value())
        w["low_label"].setText(f"Low: {low} dB")
        w["mid_label"].setText(f"Mid: {mid} dB")
        w["high_label"].setText(f"High: {high} dB")
        self.engine.set_eq(deck, low, mid, high)

    def _on_seek_pressed(self, deck: str):
        self.seeking[deck] = True

    def _on_seek_released(self, deck: str):
        self.seeking[deck] = False
        frame = self.deck_widgets[deck]["seek_slider"].value()
        self.engine.seek_frames(deck, frame)

    def on_crossfader_change(self, val: int):
        xf = val / 100.0
        self.engine.set_crossfader(xf)
        self.xf_label.setText(f"A ◀──── {int(xf*100)}% ────▶ B")

    def on_tick(self):
        # Update seek sliders for both decks unless the user is dragging
        for deck in ('A', 'B'):
            w = self.deck_widgets[deck]
            if w["seek_slider"].isEnabled():
                self._update_waveform_view(deck)
                # pos = self.engine.get_position(deck)
                # dur = self.engine.get_duration(deck)
                # if dur > 0:
                #     p = max(0.0, min(1.0, pos / float(dur)))
                #     root = w["wave_widget"].root()
                #     if root is not None:
                #         root.setProperty("playhead", p)

            # if w["seek_slider"].isEnabled() and not self.seeking[deck]:
            #     pos = self.engine.get_position(deck)
            #     w["seek_slider"].setValue(pos)
                
            #     pos_frames = self.engine.get_position(deck)
            #     total_frames = self.engine.get_duration(deck)
            #     peaks = w.get("wave_peaks")
            #     if total_frames > 0 and peaks is not None:
            #         x = int((pos_frames / total_frames) * len(peaks))
            #         w["playhead_line"].setValue(x)
        


    def closeEvent(self, event):
        self.engine.close()
        return super().closeEvent(event)
    
    def on_volume_change(self, deck: str, val: int):
        gain = val / 100.0
        self.engine.set_channel_gain(deck, gain)
        self.deck_widgets[deck]["vol_label"].setText(f"{val}%")


    def _update_bpm_display(self, deck: str):
        base = float(self.base_bpm.get(deck, 0.0))
        rate = float(self.deck_widgets[deck]["rate_slider"].value()) / 100.0

        if base > 0:
            cur = base * rate
            self.deck_widgets[deck]["bpm_cur_label"].setText(f"BPM @ Rate: {cur:.1f}")
        else:
            self.deck_widgets[deck]["bpm_cur_label"].setText("BPM @ Rate: --")

    def _get_current_bpm(self, deck: str) -> float:
        base = float(self.base_bpm.get(deck, 0.0))
        rate = float(self.deck_widgets[deck]["rate_slider"].value()) / 100.0
        return base * rate if base > 0 else 0.0

    def _update_waveform_view(self, deck: str):
        w = self.deck_widgets[deck]
        root = w["wave_widget"].root()
        if root is None:
            return

        # Need duration + position
        dur_frames = self.engine.get_duration(deck)
        if dur_frames <= 0:
            return

        sr = getattr(self.engine, "sr", 48000)  # adjust if your engine exposes SR differently
        dur_seconds = dur_frames / float(sr)

        pos_frames = self.engine.get_position(deck)
        pos_seconds = pos_frames / float(sr)

        bpm = self._get_current_bpm(deck)
        if bpm <= 0:
            # no bpm -> just show whole track
            root.setProperty("playhead", 0.5)
            root.setProperty("zoomStart", 0.0)
            root.setProperty("zoomWidth", 1.0)
            root.setProperty("beatLines", [])
            return

        seconds_per_beat = 60.0 / bpm
        window_seconds = self.beats_on_screen * seconds_per_beat

        # map window size into normalized [0..1] fraction of track
        zoomWidth = window_seconds / dur_seconds
        zoomWidth = max(0.02, min(1.0, zoomWidth))

        # center window on play position
        play_norm = pos_seconds / dur_seconds
        zoomStart = play_norm - zoomWidth * 0.5
        zoomStart = max(0.0, min(1.0 - zoomWidth, zoomStart))

        # beat lines within visible window
        t0 = zoomStart * dur_seconds
        t1 = (zoomStart + zoomWidth) * dur_seconds

        beat = seconds_per_beat
        # align first beat line to the beat grid (simple global grid)
        first = (t0 // beat) * beat
        if first < t0:
            first += beat

        xs = []
        t = first
        span = (t1 - t0) if (t1 > t0) else 1e-9
        while t <= t1:
            xs.append(float((t - t0) / span))  # viewport coords 0..1
            t += beat

        # push into QML
        root.setProperty("playhead", 0.5)        # centered playhead (scrolling view)
        root.setProperty("zoomStart", float(zoomStart))
        root.setProperty("zoomWidth", float(zoomWidth))
        root.setProperty("beatLines", xs)


def run_app():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.resize(1000, 600)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_app()
