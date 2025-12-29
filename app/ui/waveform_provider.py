from PyQt6.QtQuick import QQuickImageProvider
from PyQt6.QtGui import QImage
from PyQt6.QtCore import QSize

class WaveImageProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._images: dict[str, QImage] = {}

    def set_image(self, key: str, img: QImage):
        self._images[key] = img

    # IMPORTANT: requestedSize is optional to match how PyQt6 may call this
    def requestImage(self, id: str, size: QSize, requestedSize: QSize = None):
        print("WaveImageProvider.requestImage:", id)
        key = id.split("?")[0]
        img = self._images.get(key)

        if img is None or img.isNull():
            img = QImage(1, 1, QImage.Format.Format_RGBA8888)
            img.fill(0)

        if size is not None:
            size.setWidth(img.width())
            size.setHeight(img.height())

        return img, img.size()
