# app/ui/qml_waveform_widget.py
from PyQt6.QtQuickWidgets import QQuickWidget
from PyQt6.QtQml import QQmlContext
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QWidget, QVBoxLayout

# ensures qrc shader is registered
from app.ui.qml import resources_rc  # noqa

class QmlWaveformWidget(QWidget):
    def __init__(self, qml_engine, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.quick = QQuickWidget(qml_engine,self)
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)

        layout.addWidget(self.quick)

    def set_source(self, qml_path: str):
        self.quick.setSource(QUrl.fromLocalFile(qml_path))

    def root(self):
        return self.quick.rootObject()
