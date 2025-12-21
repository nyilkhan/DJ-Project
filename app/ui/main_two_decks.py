import sys
from typing import Dict
from PyQt6 import QtWidgets, QtCore
import numpy as np
from pathlib import Path

from app.audio.engine import AudioEngine, SR
from app.io.decode import load_audio_to_pcm

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ App — Two Decks + Crossfader")
        self.engine = AudioEngine(sr=SR)

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
        rate_slider.setMinimum(50); rate_slider.setMaximum(150); rate_slider.setValue(100)
        rate_label = QtWidgets.QLabel("1.00x")
        rate_slider.valueChanged.connect(lambda v: self.on_rate_change(deck, v))
        rgl.addWidget(rate_slider, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        rgl.addWidget(rate_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

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

        # Put rate + EQ side by side
        top_row = QtWidgets.QHBoxLayout()
        top_row.addWidget(rate_group)
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

        # Store widgets for this deck
        self.deck_widgets[deck] = {
            "rate_slider": rate_slider, "rate_label": rate_label,
            "low_slider": low_slider, "low_label": low_label,
            "mid_slider": mid_slider, "mid_label": mid_label,
            "high_slider": high_slider, "high_label": high_label,
            "seek_slider": seek_slider,
            "track_label": track_label,
        }
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

    def on_rate_change(self, deck: str, val: int):
        rate = val / 100.0
        self.engine.set_rate(deck, rate)
        self.deck_widgets[deck]["rate_label"].setText(f"{rate:.2f}x")

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
            if w["seek_slider"].isEnabled() and not self.seeking[deck]:
                pos = self.engine.get_position(deck)
                w["seek_slider"].setValue(pos)

    def closeEvent(self, event):
        self.engine.close()
        return super().closeEvent(event)

def run_app():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.resize(1000, 600)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_app()
