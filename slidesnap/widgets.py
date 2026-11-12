from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget


class ImageView(QWidget):
    regionChanged = Signal(list, list)

    def __init__(self, editable=False):
        super().__init__()
        self.setMinimumSize(320, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.pix = QPixmap()
        self.roi = [0, 0, 1, 1]
        self.masks = []
        self.mode = "view"
        self.editable = editable
        self.start = self.end = None
        self.zoom = 1.0
        self.setMouseTracking(True)

    def set_image(self, source):
        self.pix = source if isinstance(source, QPixmap) else QPixmap(str(source))
        self.update()

    def image_rect(self):
        if self.pix.isNull():
            return QRectF()
        available = self.rect().adjusted(12, 12, -12, -12)
        size = self.pix.size().scaled(available.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2, (self.height()-size.height())/2, size.width(), size.height())

    def normalized(self, point):
        r = self.image_rect()
        return (max(0, min(1, (point.x()-r.x())/max(r.width(), 1))),
                max(0, min(1, (point.y()-r.y())/max(r.height(), 1))))

    def screen_rect(self, norm):
        r = self.image_rect()
        x, y, w, h = norm
        return QRectF(r.x()+x*r.width(), r.y()+y*r.height(), w*r.width(), h*r.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#080d17"))
        if self.pix.isNull():
            painter.setPen(QColor("#8191a9"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Your video preview appears here")
            return
        r = self.image_rect()
        painter.drawPixmap(r, self.pix, QRectF(self.pix.rect()))
        if self.editable:
            painter.setPen(QPen(QColor("#69e3c3"), 2))
            painter.drawRect(self.screen_rect(self.roi))
            for mask in self.masks:
                painter.fillRect(self.screen_rect(mask), QColor(245, 128, 112, 75))
                painter.setPen(QPen(QColor("#f58070"), 2))
                painter.drawRect(self.screen_rect(mask))
            if self.start is not None and self.end is not None:
                painter.setPen(QPen(QColor("#69e3c3" if self.mode == "roi" else "#f58070"), 2, Qt.PenStyle.DashLine))
                painter.drawRect(QRect(self.start, self.end).normalized())

    def mousePressEvent(self, event):
        if self.editable and self.mode != "view" and self.image_rect().contains(event.position()):
            self.start = event.position().toPoint()
            self.end = self.start

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None:
            return
        a = self.normalized(self.start)
        b = self.normalized(event.position())
        norm = [min(a[0], b[0]), min(a[1], b[1]), abs(a[0]-b[0]), abs(a[1]-b[1])]
        if norm[2] > .025 and norm[3] > .025:
            if self.mode == "roi":
                self.roi = norm
            else:
                self.masks.append(norm)
            self.regionChanged.emit(self.roi, self.masks)
        self.start = self.end = None
        self.update()


class ZoomView(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWidget(self.label)
        self.pix = QPixmap()
        self.factor = 1.0
        self.fitting = True
        self.setStyleSheet("QScrollArea { background: #080d17; border: 0; border-radius: 12px; }")

    def set_image(self, path):
        self.pix = QPixmap(str(path)) if path else QPixmap()
        self.apply_zoom()

    def apply_zoom(self):
        if self.pix.isNull():
            self.label.clear()
            return
        if self.fitting:
            area = self.viewport().size()
            self.factor = min(max(1, area.width()-24)/self.pix.width(), max(1, area.height()-24)/self.pix.height())
        size = self.pix.size() * self.factor
        self.label.setPixmap(self.pix.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.label.resize(size)

    def zoom_by(self, factor):
        self.fitting = False
        self.factor = max(.1, min(5, self.factor * factor))
        self.apply_zoom()

    def fit(self):
        self.fitting = True
        self.apply_zoom()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fitting:
            self.apply_zoom()


class DropCard(QWidget):
    fileDropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropCard")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.fileDropped.emit(url.toLocalFile())
                break
