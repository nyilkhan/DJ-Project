import sys
from typing import Optional
from PyQt6 import QtWidgets, QtCore
import numpy as np
import os

from app.audio.engine import AudioEngine, SR
from app.io.decode import load_audio_to_pcm

ALLOWED_EXTS = {'.mp3', '.wav', '.m4a', '.aac', '.webm', '.flac', '.ogg'}

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ App Skeleton — Deck A")
        self.engine = AudioEngine(sr=SR)

        # Enable drag & drop
        self.setAcceptDrops(True)

        # Widgets
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)

        self.load_btn = QtWidgets.QPushButton("Load Track (.mp3, .wav, ...)")
        self.play_btn = QtWidgets.QPushButton("Play/Pause")
        self.rate_label = QtWidgets.QLabel("Rate: 1.00x")

        self.rate_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        self.rate_slider.setMinimum(80)  # 0.8x
        self.rate_slider.setMaximum(120) # 1.2x
        self.rate_slider.setValue(100)

        self.rate_group = QtWidgets.QGroupBox("Rate")
        rg = QtWidgets.QVBoxLayout(self.rate_group)
        rg.addWidget(self.rate_slider, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        rg.addWidget(self.rate_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)


        self.seek_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.seek_slider.setMinimum(0)
        self.seek_slider.setMaximum(0)
        self.seek_slider.setEnabled(False)

        # Code for EQ
        self.eq_group = QtWidgets.QGroupBox("EQ (dB)")


        def make_slider(label_text):
            label = QtWidgets.QLabel(f"{label_text}: 0 dB")
            slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
            slider.setMinimum(-80)   # kill to +6 dB
            slider.setMaximum(10)
            slider.setValue(0)
            slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksRight)
            return label, slider
        
        self.low_label,  self.low_slider  = make_slider("Low")
        self.mid_label,  self.mid_slider  = make_slider("Mid")
        self.high_label, self.high_slider = make_slider("High")

        eq_layout = QtWidgets.QHBoxLayout()
        for label, slider in [
            (self.low_label,  self.low_slider),
            (self.mid_label,  self.mid_slider),
            (self.high_label, self.high_slider),
        ]:
            col = QtWidgets.QVBoxLayout()
            col.addWidget(slider, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(label,  alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
            eq_layout.addLayout(col)
        self.eq_group.setLayout(eq_layout)
        

        # Hot cues 1..4
        self.cue_set_btns = []
        self.cue_go_btns = []

        cues_layout = QtWidgets.QGridLayout()
        for i in range(1, 5):
            set_btn = QtWidgets.QPushButton(f"Set CUE {i}")
            go_btn = QtWidgets.QPushButton(f"Go CUE {i}")
            set_btn.clicked.connect(lambda _, n=i: self.engine.set_hotcue(n))
            go_btn.clicked.connect(lambda _, n=i: self.engine.goto_hotcue(n))
            self.cue_set_btns.append(set_btn)
            self.cue_go_btns.append(go_btn)
            cues_layout.addWidget(set_btn, 0, i-1)
            cues_layout.addWidget(go_btn, 1, i-1)

        layout = QtWidgets.QVBoxLayout(central)
        layout.addWidget(self.load_btn)
        layout.addWidget(self.play_btn)

        # layout.addWidget(self.rate_label)
        # layout.addWidget(self.rate_slider)
        
        mix_layout = QtWidgets.QHBoxLayout()
        mix_layout.addWidget(self.rate_group)
        mix_layout.addWidget(self.eq_group)
        
        layout.addLayout(mix_layout)
        layout.addWidget(QtWidgets.QLabel("Seek:"))
        layout.addWidget(self.seek_slider)
        layout.addLayout(cues_layout)
        layout.addWidget(self.eq_group)

        # wire up signals
        for s in (self.low_slider, self.mid_slider, self.high_slider):
            s.valueChanged.connect(self.on_eq_change)

        # initialize EQ once
        self.on_eq_change()


        # Connections
        self.load_btn.clicked.connect(self.on_load_dialog)
        self.play_btn.clicked.connect(self.engine.toggle_play)
        self.rate_slider.valueChanged.connect(self.on_rate_change)
        self.seek_slider.sliderPressed.connect(self.on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self.on_seek_released)

        # Update timer
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(50)  # 20 fps

        self.seeking = False

    # ----- Loading helpers -----
    def on_load_dialog(self):
        dlg = QtWidgets.QFileDialog(self, "Select audio file")
        dlg.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
        dlg.setNameFilters([
            "Audio files (*.mp3 *.wav *.m4a *.aac *.webm *.flac *.ogg)",
            "All files (*)"
        ])
        if dlg.exec():
            path = dlg.selectedFiles()[0]
            self.load_path(path)

    def load_path(self, path: str):
        try:
            pcm, sr = load_audio_to_pcm(path, target_sr=SR)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load error", str(e))
            return
        try:
            self.engine.load_pcm(pcm, sr)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Engine error", str(e))
            return
        self.seek_slider.setEnabled(True)
        self.seek_slider.setMinimum(0)
        self.seek_slider.setMaximum(len(pcm)-1)
        self.seek_slider.setValue(0)
        self.statusBar().showMessage(f"Loaded: {os.path.basename(path)}", 5000)

    # ----- Drag & drop -----
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for u in event.mimeData().urls():
                if u.isLocalFile():
                    ext = os.path.splitext(u.toLocalFile())[1].lower()
                    if ext in ALLOWED_EXTS:
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dropEvent(self, event):
        for u in event.mimeData().urls():
            if u.isLocalFile():
                path = u.toLocalFile()
                ext = os.path.splitext(path)[1].lower()
                if ext in ALLOWED_EXTS:
                    self.load_path(path)
                    break

    # ----- Transport & UI updates -----
    def on_rate_change(self, val: int):
        rate = val / 100.0
        self.engine.set_rate(rate)
        self.rate_label.setText(f"Rate: {rate:.2f}x")

    def on_seek_pressed(self):
        self.seeking = True

    def on_seek_released(self):
        self.seeking = False
        frame = self.seek_slider.value()
        self.engine.seek_frames(frame)

    def on_tick(self):
        # UI position update
        if not self.seeking and self.seek_slider.isEnabled():
            pos = self.engine.get_position()
            self.seek_slider.setValue(pos)

    def closeEvent(self, event):
        self.engine.close()
        return super().closeEvent(event)

    def on_eq_change(self):
        low = int(self.low_slider.value())
        mid = int(self.mid_slider.value())
        high = int(self.high_slider.value())
        self.low_label.setText(f"Low: {low} dB")
        self.mid_label.setText(f"Mid: {mid} dB")
        self.high_label.setText(f"High: {high} dB")
        # <-- This is the call you asked about:
        self.engine.set_eq(low, mid, high)



def run_app():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.resize(700, 320)
    w.show()
    sys.exit(app.exec())
