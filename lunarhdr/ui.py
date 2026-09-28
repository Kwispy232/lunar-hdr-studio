"""Desktop workspace for aligning and developing lunar exposure brackets."""
from __future__ import annotations

import errno
import math
import os
import traceback
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSettings, QStandardPaths, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QImage, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QScrollArea, QSizePolicy,
    QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from . import engine
from .finishing import finish_image
from .help_dialog import HelpDialog

IMAGE_FILTER = "Images and FITS (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp *.fit *.fits *.fts *.fit.gz *.fits.gz *.fts.gz *.fit.fz *.fits.fz *.fts.fz);;FITS (*.fit *.fits *.fts *.fit.gz *.fits.gz *.fts.gz *.fit.fz *.fits.fz *.fts.fz);;All files (*)"
EXPORT_FORMATS = (
    ("PNG (*.png)", ".png", (".png",)),
    ("JPEG (*.jpg)", ".jpg", (".jpg", ".jpeg")),
    ("16-bit TIFF (*.tif)", ".tif", (".tif", ".tiff")),
    ("Linear HDR radiance (unedited) (*.hdr)", ".hdr", (".hdr",)),
)


def default_export_directory() -> Path:
    """LaunchServices may start in '/'; save destinations must never depend on cwd."""
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    candidates = [Path(pictures)] if pictures else []
    candidates.append(Path.home())
    for candidate in candidates:
        if candidate.is_absolute() and candidate.is_dir() and os.access(candidate, os.W_OK):
            return candidate
    return Path.home()


def resolve_export_path(path: str, selected_filter: str) -> str:
    """Resolve native-dialog formats even when Qt returns an empty filter."""
    destination = Path(path)
    selected = next((item for item in EXPORT_FORMATS if item[0] == selected_filter), None)
    if selected is None and selected_filter:
        # Native dialogs can return a shortened/localized label with only its pattern.
        pattern = selected_filter.lower()
        selected = next((item for item in EXPORT_FORMATS
                         if any("*" + suffix in pattern for suffix in item[2])), None)
    if selected is None:
        selected = next((item for item in EXPORT_FORMATS
                         if destination.suffix.lower() in item[2]), EXPORT_FORMATS[0])
    _, default_suffix, accepted_suffixes = selected
    if destination.suffix.lower() not in accepted_suffixes:
        destination = destination.with_suffix(default_suffix)
    return str(destination)


DEFAULTS = dict(exposure=0.0, contrast=0, highlights=0, shadows=0,
                temperature=0, white_balance=0, saturation=100, mineral=0, clarity=0,
                sharpness=0, denoise=0)
PRESETS = {
    "Natural": dict(DEFAULTS, contrast=6, highlights=-24, shadows=8,
                    saturation=106, clarity=10, sharpness=12),
    "Mineral Moon": dict(DEFAULTS, white_balance=100, saturation=100, mineral=65,
                         clarity=30, sharpness=18, denoise=8),
    "Silver": dict(DEFAULTS, contrast=18, highlights=-20, shadows=8,
                   saturation=0, clarity=20, sharpness=16),
    "Earthshine": dict(DEFAULTS, exposure=0.35, contrast=5, highlights=-48,
                       shadows=55, saturation=115, clarity=8, denoise=22),
}

STYLE = """
QMainWindow, QDialog { background: #111517; color: #dbe3e5; }
QWidget { color: #dbe3e5; font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif; font-size: 12px; }
QFrame#header { background: #171c1f; border-bottom: 1px solid #2a3235; }
QFrame#rail { background: #171c1f; border: 1px solid #2c3539; border-radius: 10px; }
QFrame#card { background: #1d2428; border: 1px solid #343e43; border-radius: 9px; }
QFrame#canvasShell { background: #0b0e10; border: 1px solid #2b3438; border-radius: 10px; }
QFrame#footer { border-top: 1px solid #2a3337; }
QLabel#muted { color: #82939a; }
QLabel#eyebrow { color: #82979b; font-size: 10px; font-weight: 600; }
QLabel#section { font-size: 12px; font-weight: 600; color: #e7edee; }
QLabel#badge { color: #b7dcd7; background: #263936; border: 1px solid #3a524d; border-radius: 5px; padding: 5px 8px; font-size: 10px; }
QLabel#sourceBadge { color: #aab5b7; background: #20272b; border-radius: 4px; padding: 3px 6px; font-size: 10px; }
QPushButton, QToolButton { background: #252f34; color: #d9e3e6; border: 1px solid #3a474d; border-radius: 6px; padding: 8px 12px; font-weight: 500; }
QPushButton:hover, QToolButton:hover { background: #303d42; border-color: #587077; }
QPushButton:pressed, QToolButton:pressed { background: #35474b; }
QPushButton:disabled, QToolButton:disabled { background: #20272b; color: #58686f; border-color: #2d383d; }
QPushButton#primary { background: #97d3c6; color: #112620; border: 1px solid #b0e0d6; font-weight: 700; padding: 11px; }
QPushButton#primary:hover { background: #b5e5da; }
QPushButton#primary:disabled { background: #354b46; border-color: #354b46; color: #82998f; }
QPushButton#quiet { background: transparent; border-color: #303b40; padding: 6px 10px; color: #a2b6bd; }
QPushButton#preset { padding: 9px 6px; font-size: 11px; }
QPushButton#preset:checked { color: #c1e9df; border: 1px solid #80b9aa; background: #263d36; }
QToolButton:checked { color: #bfe4d9; background: #2c443b; border-color: #76a999; }
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit { background: #101719; color: #c9d7dd; border: 1px solid #3a484e; border-radius: 5px; padding: 6px; min-height: 15px; }
QComboBox QAbstractItemView { background: #1a2428; color: #deeaee; selection-background-color: #38564d; }
QMenuBar, QMenu { background: #171c1f; color: #dbe3e5; }
QMenuBar::item:selected, QMenu::item:selected { background: #38564d; }
QMenu::item { padding: 7px 20px; }
QComboBox::drop-down { border: 0; width: 23px; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #60766e; background: #14211c; border-radius: 3px; }
QCheckBox::indicator:checked { background: #8fc7b7; border-color: #b9e0d2; }
QSlider::groove:horizontal { height: 3px; background: #354348; border-radius: 1px; }
QSlider::sub-page:horizontal { background: #80b4a9; border-radius: 1px; }
QSlider::handle:horizontal { width: 11px; height: 11px; margin: -4px 0; border-radius: 6px; background: #b7d5cd; border: 1px solid #152721; }
QScrollArea { background: #171c1f; border: none; }
QWidget#developControls, QWidget#inputCards { background: #171c1f; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 1px; }
QScrollBar::handle:vertical { background: #43545b; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { background: #29363a; border: none; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: #97d3c6; border-radius: 2px; }
QToolTip { background: #233137; color: #e0ecef; border: 1px solid #5b747d; padding: 5px; }
"""


def label(text: str, role: str = "", parent=None) -> QLabel:
    item = QLabel(text, parent)
    if role:
        item.setObjectName(role)
    return item


def qimage(pixels: np.ndarray) -> QImage:
    values = np.ascontiguousarray(np.clip(pixels * 255.0 + 0.5, 0, 255).astype(np.uint8))
    height, width = values.shape[:2]
    return QImage(values.data, width, height, values.strides[0], QImage.Format.Format_RGB888).copy()


def preview_size(pixels: np.ndarray, maximum: int = 1500) -> np.ndarray:
    height, width = pixels.shape[:2]
    factor = min(1.0, maximum / max(height, width))
    if factor < 1:
        return cv2.resize(pixels, (round(width * factor), round(height * factor)), interpolation=cv2.INTER_AREA)
    return pixels.copy()


class Task(QThread):
    progressed = Signal(int, str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, function: Callable, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.result.emit(self.function(self.progressed.emit))
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")


class ExposureCard(QFrame):
    requested = Signal(int)
    dropped = Signal(int, str)
    evChanged = Signal()
    removed = Signal(int)

    def __init__(self, index: int, title: str, description: str, ev: float, parent=None):
        super().__init__(parent)
        self.index = index
        self.setObjectName("card")
        self.setAcceptDrops(True)
        self.setMinimumHeight(153)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(11, 10, 11, 10)
        outer.setSpacing(7)
        top = QHBoxLayout()
        top.addWidget(label(f"{index + 1:02d}", "eyebrow"))
        top.addWidget(label(title, "section"), 1)
        self.ev = QDoubleSpinBox()
        self.ev.setRange(-20, 20)
        self.ev.setDecimals(3)
        self.ev.setSingleStep(0.3)
        self.ev.setValue(ev)
        self.ev.setSuffix(" EV")
        self.ev.setFixedWidth(98)
        self.ev.setToolTip("Exposure relative to the selected reference. Used for radiometric HDR merging.")
        self.ev.valueChanged.connect(lambda _value: self.evChanged.emit())
        top.addWidget(self.ev)
        outer.addLayout(top)
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(56, 56)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setStyleSheet("background: #101517; border-radius: 6px; color:#506067; font-size:24px;")
        self.thumbnail.setText("＋")
        middle = QHBoxLayout()
        middle.addWidget(self.thumbnail)
        copy = QVBoxLayout()
        copy.setSpacing(4)
        self.filename = label("Add an image", "section")
        self.filename.setWordWrap(True)
        self.filename.setMaximumWidth(136)
        self.details = label(description, "muted")
        self.details.setWordWrap(True)
        self.details.setStyleSheet("font-size: 10px; color: #85989f;")
        copy.addWidget(self.filename)
        copy.addWidget(self.details)
        middle.addLayout(copy, 1)
        outer.addLayout(middle)
        self.browse = QPushButton("Choose file  ↗")
        self.browse.setObjectName("quiet")
        self.browse.clicked.connect(lambda: self.requested.emit(self.index))
        actions = QHBoxLayout()
        actions.addWidget(self.browse, 1)
        self.remove_button = QPushButton("×")
        self.remove_button.setObjectName("quiet")
        self.remove_button.setFixedWidth(29)
        self.remove_button.setToolTip("Remove this exposure")
        self.remove_button.clicked.connect(lambda: self.removed.emit(self.index))
        actions.addWidget(self.remove_button)
        outer.addLayout(actions)

    def clear_frame(self):
        self.thumbnail.setPixmap(QPixmap())
        self.thumbnail.setText("＋")
        self.filename.setText("Add an image")
        self.filename.setToolTip("")
        self.details.setText("No image loaded yet")
        self.browse.setText("Choose file  ↗")

    def set_frame(self, frame):
        source = qimage(preview_size(frame.pixels, 180))
        self.thumbnail.setPixmap(QPixmap.fromImage(source).scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                                                Qt.TransformationMode.SmoothTransformation))
        name = frame.name
        self.filename.setText(name if len(name) < 27 else name[:23] + "…")
        self.filename.setToolTip(frame.path)
        height, width = frame.pixels.shape[:2]
        metadata = getattr(frame, "metadata", {}) or {}
        source = "FITS" if metadata.get("source_format") == "fits" else Path(frame.path).suffix.lstrip(".").upper()
        mono = " · mono" if metadata.get("monochrome") else ""
        seconds = getattr(frame, "exposure_seconds", None)
        exposure = f" · {seconds:.5g} s" if seconds is not None else ""
        self.details.setText(f"{width:,} × {height:,} · {source}{mono}{exposure}".replace(",", " "))
        self.details.setToolTip("\n".join(getattr(frame, "warnings", [])) or f"{frame.bit_depth} bit")
        self.browse.setText("Replace image  ↗")

    def dragEnterEvent(self, event):
        if self.isEnabled() and event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.isEnabled() and event.mimeData().hasUrls():
            self.dropped.emit(self.index, event.mimeData().urls()[0].toLocalFile())
            event.acceptProposedAction()


class ImageCanvas(QWidget):
    zoomChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(380, 370)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.after: QImage | None = None
        self.before: QImage | None = None
        self.compare = False
        self.wipe = 0.5
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self._drag = None
        self._last = QPointF()

    def set_images(self, after: np.ndarray, before: np.ndarray | None = None):
        self.after = qimage(after)
        if before is not None:
            self.before = qimage(before)
        self.update()
        self._emit_zoom()

    def fit(self):
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self._emit_zoom()
        self.update()

    def zoom_by(self, factor):
        self.zoom = min(8.0, max(0.3, self.zoom * factor))
        self._emit_zoom()
        self.update()

    def _emit_zoom(self):
        self.zoomChanged.emit("Fit" if abs(self.zoom - 1) < 0.01 else f"{self.zoom:.1f}×")

    def image_rect(self):
        if self.after is None:
            return QRectF()
        scale = min((self.width() - 44) / self.after.width(), (self.height() - 58) / self.after.height()) * self.zoom
        width, height = self.after.width() * scale, self.after.height() * scale
        return QRectF((self.width() - width) / 2 + self.pan.x(),
                      (self.height() - height) / 2 + self.pan.y(), width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0b0e10"))
        if self.after is None:
            painter.setPen(QColor("#526870"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Multiple exposures. One Moon.\n\nAdd at least two photos or FITS images.")
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.image_rect()
        painter.drawImage(rect, self.after)
        if self.compare and self.before is not None:
            split = self.width() * self.wipe
            painter.save()
            painter.setClipRect(QRectF(0, 0, split, self.height()))
            painter.drawImage(rect, self.before)
            painter.restore()
            painter.setPen(QPen(QColor("#d9ece8"), 1))
            painter.drawLine(QPointF(split, 0), QPointF(split, self.height()))
            painter.setBrush(QColor("#d2e7e1"))
            painter.drawEllipse(QPointF(split, self.height() / 2), 15, 15)
            painter.setPen(QColor("#263a35"))
            painter.drawText(QRectF(split - 14, self.height()/2 - 12, 28, 24),
                             Qt.AlignmentFlag.AlignCenter, "‹ ›")
            self._tag(painter, QRectF(12, 12, 106, 25), "Reference")
            self._tag(painter, QRectF(self.width() - 88, 12, 76, 25), "Result")

    def _tag(self, painter, rect, text):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 26, 220))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor("#e0e9e8"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def wheelEvent(self, event):
        self.zoom_by(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._last = event.position()
            self._drag = "wipe" if self.compare and abs(event.position().x() - self.width() * self.wipe) < 24 else "pan"
            self.setCursor(Qt.CursorShape.SplitHCursor if self._drag == "wipe" else Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag == "wipe":
            self.wipe = min(0.98, max(0.02, event.position().x() / self.width()))
            self.update()
        elif self._drag == "pan":
            self.pan += event.position() - self._last
            self._last = event.position()
            self.update()
        else:
            self.setCursor(Qt.CursorShape.SplitHCursor if self.compare and
                           abs(event.position().x() - self.width()*self.wipe) < 24
                           else Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event):
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event):
        self.fit()


class CropCanvas(QWidget):
    changed = Signal(tuple)

    def __init__(self, pixels, crop_rect=(0, 0, 1, 1), parent=None):
        super().__init__(parent)
        self.picture = qimage(preview_size(pixels, 1100))
        self.crop_rect = tuple(crop_rect)
        self._anchor = None
        self._previous = self.crop_rect
        self.setMinimumSize(580, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def image_rect(self):
        scale = min((self.width()-24)/self.picture.width(), (self.height()-24)/self.picture.height())
        width, height = self.picture.width()*scale, self.picture.height()*scale
        return QRectF((self.width()-width)/2, (self.height()-height)/2, width, height)

    def normalized_point(self, point):
        rect = self.image_rect()
        return (min(1., max(0., (point.x()-rect.x())/rect.width())),
                min(1., max(0., (point.y()-rect.y())/rect.height())))

    def reset(self):
        self.crop_rect = (0., 0., 1., 1.)
        self.changed.emit(self.crop_rect)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0e10"))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        image = self.image_rect()
        painter.drawImage(image, self.picture)
        x, y, w, h = self.crop_rect
        crop = QRectF(image.x()+x*image.width(), image.y()+y*image.height(), w*image.width(), h*image.height())
        shade = QColor(0, 0, 0, 155)
        painter.fillRect(QRectF(image.left(), image.top(), image.width(), crop.top()-image.top()), shade)
        painter.fillRect(QRectF(image.left(), crop.bottom(), image.width(), image.bottom()-crop.bottom()), shade)
        painter.fillRect(QRectF(image.left(), crop.top(), crop.left()-image.left(), crop.height()), shade)
        painter.fillRect(QRectF(crop.right(), crop.top(), image.right()-crop.right(), crop.height()), shade)
        painter.setPen(QPen(QColor("#a4d7c9"), 1.5))
        painter.drawRect(crop)
        painter.setPen(QPen(QColor(210, 233, 227, 110), 1, Qt.PenStyle.DashLine))
        for part in (1/3, 2/3):
            painter.drawLine(QPointF(crop.left()+crop.width()*part, crop.top()), QPointF(crop.left()+crop.width()*part, crop.bottom()))
            painter.drawLine(QPointF(crop.left(), crop.top()+crop.height()*part), QPointF(crop.right(), crop.top()+crop.height()*part))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#c3e7dd"))
        for point in (crop.topLeft(), crop.topRight(), crop.bottomLeft(), crop.bottomRight()):
            painter.drawEllipse(point, 3, 3)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.image_rect().contains(event.position()):
            self._previous = self.crop_rect
            self._anchor = self.normalized_point(event.position())

    def mouseMoveEvent(self, event):
        if self._anchor is None:
            return
        x, y = self.normalized_point(event.position())
        start_x, start_y = self._anchor
        self.crop_rect = (min(x, start_x), min(y, start_y), abs(x-start_x), abs(y-start_y))
        self.changed.emit(self.crop_rect)
        self.update()

    def mouseReleaseEvent(self, event):
        if self._anchor is None:
            return
        self.mouseMoveEvent(event)
        self._anchor = None
        if self.crop_rect[2]*self.picture.width() < 3 or self.crop_rect[3]*self.picture.height() < 3:
            self.crop_rect = self._previous
        self.changed.emit(self.crop_rect)
        self.update()


class CropDialog(QDialog):
    def __init__(self, pixels, crop_rect=(0, 0, 1, 1), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crop composition")
        self.resize(820, 660)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(label("Drag to select a crop", "section"))
        note = label("The crop applies to the preview and PNG, JPEG and TIFF exports. Linear HDR exports keep the full image.", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.canvas = CropCanvas(pixels, crop_rect)
        layout.addWidget(self.canvas, 1)
        self.selection_info = label("", "muted")
        self.canvas.changed.connect(self._selection_changed)
        self._selection_changed(crop_rect)
        layout.addWidget(self.selection_info)
        buttons = QHBoxLayout()
        reset = QPushButton("Full image")
        reset.clicked.connect(self.canvas.reset)
        buttons.addWidget(reset)
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        apply = QPushButton("Apply crop")
        apply.setObjectName("primary")
        apply.clicked.connect(self.accept)
        buttons.addWidget(apply)
        layout.addLayout(buttons)

    def _selection_changed(self, rect):
        self.selection_info.setText(f"Width {rect[2]*100:.1f}% · height {rect[3]*100:.1f}% of the original image")

    def selected_rect(self):
        return self.canvas.crop_rect


class Adjustment(QWidget):
    changed = Signal()

    def __init__(self, title, minimum, maximum, value=0, factor=1, suffix="", parent=None):
        super().__init__(parent)
        self.factor, self.suffix = factor, suffix
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(4)
        row = QHBoxLayout()
        row.addWidget(label(title), 1)
        self.value_label = label("", "muted")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.value_label.setMinimumWidth(42)
        row.addWidget(self.value_label)
        self.layout_.addLayout(row)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(round(value * factor))
        self.slider.setFixedHeight(18)
        self.slider.valueChanged.connect(self._changed)
        self.layout_.addWidget(self.slider)
        self._update_text()

    def value(self):
        return self.slider.value() / self.factor

    def set_value(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(round(value * self.factor))
        self.slider.blockSignals(False)
        self._update_text()

    def _update_text(self):
        value = self.value()
        if self.factor != 1:
            self.value_label.setText(f"{value:+.2f}{self.suffix}")
        else:
            self.value_label.setText(f"{int(value)}{self.suffix}")

    def _changed(self):
        self._update_text()
        self.changed.emit()


class ManualAlignmentDialog(QDialog):
    """One reusable editor and a downsampled overlay for any source frame."""
    def __init__(self, corrections, reports, parent=None, alignment=None, frames=None):
        super().__init__(parent)
        self.setWindowTitle("Fine-tune alignment")
        self.setMinimumWidth(690)
        self._alignment = alignment
        self._frames = frames or []
        self._reports = reports
        count = len(self._frames) or len(reports)
        self.reference_index = alignment.reference_index if alignment is not None else 0
        self._corrections = [dict(corrections[i]) if i < len(corrections) else {} for i in range(count)]
        self._selected_index = None
        self._overlay_inputs = {}
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.setInterval(30)
        self._overlay_timer.timeout.connect(self.update_overlay)
        body = QVBoxLayout(self)
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(12)
        body.addWidget(label("Fine-tune the lunar disks", "section"))
        note = label("Select an image and adjust it against the fixed reference. Corrections are relative to the automatic alignment.", "muted")
        note.setWordWrap(True)
        body.addWidget(note)
        preview_row = QHBoxLayout()
        preview_row.addWidget(label("EXPOSURE TO ADJUST", "eyebrow"))
        self.overlay_selector = QComboBox()
        self.overlay_selector.setMinimumWidth(300)
        for index in range(count):
            if index != self.reference_index:
                name = self._frames[index].name if self._frames else f"Image {index+1}"
                self.overlay_selector.addItem(f"{index+1:02d} · {name}", index)
        preview_row.addWidget(self.overlay_selector, 1)
        body.addLayout(preview_row)
        self.overlay = QLabel()
        self.overlay.setFixedSize(650, 280)
        self.overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay.setStyleSheet("background:#080d10; border:1px solid #33464a; border-radius:6px;")
        body.addWidget(self.overlay, 0, Qt.AlignmentFlag.AlignHCenter)
        legend = label("Red = reference · cyan = selected exposure · neutral edges = alignment.\nBrightness is normalized; exposure differences or clipped detail can affect the color.", "muted")
        legend.setStyleSheet("font-size:10px; color:#92a7af;")
        legend.setWordWrap(True)
        body.addWidget(legend)
        self.controls = {}
        self.values = {}
        grid = QGridLayout()
        specs = [("dx", "X shift · px", -100000, 100000, 0.25, 2),
                 ("dy", "Y shift · px", -100000, 100000, 0.25, 2),
                 ("rotation", "Rotation · °", -180, 180, 0.05, 3),
                 ("scale", "Scale", 0.01, 100, 0.001, 4)]
        for col, (key, title, low, high, step, decimals) in enumerate(specs):
            grid.addWidget(label(title, "muted"), 0, col)
            control = QDoubleSpinBox()
            control.setRange(low, high)
            control.setDecimals(decimals)
            control.setSingleStep(step)
            control.valueChanged.connect(self._control_changed)
            grid.addWidget(control, 1, col)
            self.controls[key] = control
        body.addLayout(grid)
        self.diagnostic = label("", "muted")
        self.diagnostic.setWordWrap(True)
        self.diagnostic.setMinimumHeight(36)
        self.diagnostic.setMaximumHeight(64)
        self.diagnostic.setStyleSheet("font-size:10px; color:#92a7af;")
        body.addWidget(self.diagnostic)
        buttons = QHBoxLayout()
        reset = QPushButton("Reset selected")
        reset.clicked.connect(self.reset)
        buttons.addWidget(reset)
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        apply = QPushButton("Apply and rebuild HDR")
        apply.setObjectName("primary")
        apply.clicked.connect(self.accept)
        buttons.addWidget(apply)
        body.addLayout(buttons)
        self.overlay_selector.currentIndexChanged.connect(self._selection_changed)
        if self._alignment is not None and self._frames:
            self._prepare_reference()
        self._selection_changed()

    @staticmethod
    def _normalized_luminance(pixels):
        gray = pixels @ np.float32([0.2126, 0.7152, 0.0722])
        black, white = np.percentile(gray, [5, 99.5])
        return np.clip((gray-black)/max(float(white-black), 1e-5), 0, 1).astype(np.float32)

    def _prepare_reference(self):
        source = self._frames[self.reference_index].pixels
        ref_h, ref_w = source.shape[:2]
        self._overlay_ref_size = (ref_w, ref_h)
        factor = min(650/ref_w, 280/ref_h, 1.0)
        self._overlay_size = (max(1, round(ref_w*factor)), max(1, round(ref_h*factor)))
        rx, ry = self._overlay_size[0]/ref_w, self._overlay_size[1]/ref_h
        self._overlay_destination_scale = np.float64([[rx, 0, (rx-1)/2], [0, ry, (ry-1)/2], [0, 0, 1]])
        reference = cv2.resize(source, self._overlay_size, interpolation=cv2.INTER_AREA)
        self._overlay_reference = self._normalized_luminance(reference)

    def select_frame(self, index):
        position = self.overlay_selector.findData(index)
        if position >= 0:
            self.overlay_selector.setCurrentIndex(position)

    def _selection_changed(self, *args):
        self._store_selected()
        self._selected_index = self.overlay_selector.currentData()
        if self._selected_index is None:
            return
        index = self._selected_index
        correction = self._corrections[index]
        for key, control in self.controls.items():
            control.blockSignals(True)
            control.setValue(correction.get(key, 1 if key == "scale" else 0))
            control.blockSignals(False)
        self.values = {index: self.controls}
        report = self._reports[index] if index < len(self._reports) else {}
        text = f"{report.get('method', 'Alignment')} · confidence {float(report.get('confidence', 0)):.0%} · {report.get('inliers', 0)} points"
        if "residual_px" in report:
            text += f" · residual {report['residual_px']:.2f} px"
        if report.get("warning"):
            text += "\n" + report["warning"]
        self.diagnostic.setText(text)
        self.diagnostic.setToolTip(text)
        if self._alignment is not None and self._frames:
            source = self._frames[index].pixels
            source_h, source_w = source.shape[:2]
            small = preview_size(source, 700)
            small_h, small_w = small.shape[:2]
            ix, iy = source_w/small_w, source_h/small_h
            inverse = np.float64([[ix, 0, (ix-1)/2], [0, iy, (iy-1)/2], [0, 0, 1]])
            self._overlay_inputs = {index: (self._normalized_luminance(small), inverse)}
            self.update_overlay()

    def _store_selected(self):
        if self._selected_index is not None:
            self._corrections[self._selected_index] = {key: control.value() for key, control in self.controls.items()}

    def _control_changed(self, *args):
        self._store_selected()
        self._overlay_timer.start()

    def update_overlay(self, *args):
        index = self._selected_index
        if index not in self._overlay_inputs:
            return
        width, height = self._overlay_ref_size
        correction = cv2.getRotationMatrix2D(((width-1)/2, (height-1)/2),
                                             self.controls["rotation"].value(), self.controls["scale"].value())
        correction[:, 2] += [self.controls["dx"].value(), self.controls["dy"].value()]
        baseline = np.vstack((self._alignment.matrices[index], [0, 0, 1]))
        combined = np.vstack((correction @ baseline, [0, 0, 1]))
        gray, inverse_scale = self._overlay_inputs[index]
        preview_matrix = (self._overlay_destination_scale @ combined @ inverse_scale)[:2]
        transformed = cv2.warpAffine(gray, preview_matrix, self._overlay_size,
                                     flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        overlay = np.stack((self._overlay_reference, transformed, transformed), axis=2)
        self.overlay.setPixmap(QPixmap.fromImage(qimage(overlay)))

    def reset(self):
        for key, control in self.controls.items():
            control.setValue(1 if key == "scale" else 0)

    def corrections(self):
        self._store_selected()
        return [dict(correction) for correction in self._corrections]


class MainWindow(QMainWindow):
    def __init__(self, *, settings=None, show_onboarding=True):
        super().__init__()
        self._settings = settings if settings is not None else QSettings("LunarHDR", "LunarHDRStudio")
        self._show_onboarding = bool(show_onboarding)
        self._onboarding_started = False
        self._help_dialog = None
        self._onboarding_timer = QTimer(self)
        self._onboarding_timer.setSingleShot(True)
        self._onboarding_timer.setInterval(250)
        self._onboarding_timer.timeout.connect(self._show_first_run_help)
        self.setWindowTitle("Lunar HDR Studio")
        self.resize(1480, 960)
        self.setMinimumSize(1160, 780)
        self.setStyleSheet(STYLE)
        self.frames = []
        self.reference_index = 0
        self._ev_from_metadata = False
        self.automatic_alignment = None
        self.alignment = None
        self.composite = None
        self.corrections = []
        self._preview_base = None
        self._preview_before = None
        self._preview_after = None
        self._task = None
        self._busy = False
        self._synthetic = False
        self._merge_dirty = False
        self._export_directory = None
        self.crop_rect = (0.0, 0.0, 1.0, 1.0)
        self.crop_enabled = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(95)
        self._preview_timer.timeout.connect(self.update_preview)
        self._build()
        QTimer.singleShot(80, self.load_demo)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._onboarding_started:
            self._onboarding_started = True
            if self._show_onboarding and not self._settings.value("onboarding/seen_v1", False, type=bool):
                self._onboarding_timer.start()

    def _show_first_run_help(self):
        if self.isVisible() and not self._settings.value("onboarding/seen_v1", False, type=bool):
            self.show_help("quick-start")

    def show_help(self, topic="quick-start"):
        """Keep a single modeless guide available, including while processing."""
        self._onboarding_timer.stop()
        if self._help_dialog is None:
            self._help_dialog = HelpDialog(self, initial_topic=topic)
            self._help_dialog.finished.connect(self._help_closed)
        else:
            self._help_dialog.select_topic(topic)
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

    def _help_closed(self, _result):
        self._settings.setValue("onboarding/seen_v1", True)
        self._settings.sync()

    def _build(self):
        self.help_menu = self.menuBar().addMenu("&Help")
        self.help_action = QAction("Getting started", self)
        self.help_action.setShortcut(QKeySequence("F1"))
        self.help_action.triggered.connect(lambda checked=False: self.show_help("quick-start"))
        self.help_menu.addAction(self.help_action)
        self.user_guide_action = QAction("User guide", self)
        self.user_guide_action.triggered.connect(lambda checked=False: self.show_help("import"))
        self.help_menu.addAction(self.user_guide_action)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(80)
        head = QHBoxLayout(header)
        head.setContentsMargins(26, 12, 24, 12)
        moon = label("◒")
        moon.setStyleSheet("font-size: 37px; color: #acd3c7;")
        head.addWidget(moon)
        brand = QVBoxLayout()
        brand.setSpacing(1)
        title = label("L U N A R")
        title.setStyleSheet("font-size: 21px; font-weight: 600; color: #edf4f2;")
        brand.addWidget(title)
        brand.addWidget(label("HDR STUDIO  /  LUNAR IMAGING", "eyebrow"))
        head.addLayout(brand)
        head.addSpacing(22)
        divider = label("Multiple exposures. Every detail.", "muted")
        head.addWidget(divider)
        head.addStretch()
        self.demo_button = QPushButton("Open demo")
        self.demo_button.setObjectName("quiet")
        self.demo_button.clicked.connect(self.load_demo)
        head.addWidget(self.demo_button)
        self.load_button = QPushButton("＋  Add exposures")
        self.load_button.clicked.connect(self.pick_frames)
        head.addWidget(self.load_button)
        self.help_button = QToolButton()
        self.help_button.setText("?")
        self.help_button.setAccessibleName("Help and getting started")
        self.help_button.setToolTip("Help and getting started (F1)")
        self.help_button.setFixedSize(34, 34)
        self.help_button.clicked.connect(lambda checked=False: self.show_help("quick-start"))
        head.addWidget(self.help_button)
        outer.addWidget(header)
        workspace = QHBoxLayout()
        workspace.setContentsMargins(20, 20, 20, 16)
        workspace.setSpacing(16)
        workspace.addWidget(self._build_inputs())
        workspace.addWidget(self._build_canvas(), 1)
        workspace.addWidget(self._build_develop())
        outer.addLayout(workspace, 1)
        footer = QFrame()
        footer.setObjectName("footer")
        status_layout = QVBoxLayout(footer)
        status_layout.setContentsMargins(22, 9, 22, 9)
        status_layout.setSpacing(5)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        status_layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.status = label("Ready for your photos.", "muted")
        self.status.setWordWrap(True)
        row.addWidget(self.status, 1)
        self.memory_note = label("LOCAL PROCESSING  ·  NO CLOUD UPLOADS", "eyebrow")
        row.addWidget(self.memory_note)
        status_layout.addLayout(row)
        outer.addWidget(footer)
        self._refresh_actions()

    def _build_inputs(self):
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(270)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(12, 16, 12, 14)
        layout.setSpacing(11)
        row = QHBoxLayout()
        row.addWidget(label("01   SOURCE IMAGES", "eyebrow"), 1)
        self.source_count = label("0 images", "muted")
        row.addWidget(self.source_count)
        layout.addLayout(row)
        desc = label("Two or more exposures. Add as many as you need.", "muted")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        self.cards = []
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards_scroll.viewport().setStyleSheet("background:#171c1f;")
        card_content = QWidget()
        card_content.setObjectName("inputCards")
        card_content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.cards_layout = QVBoxLayout(card_content)
        self.cards_layout.setContentsMargins(0, 0, 5, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()
        self.cards_scroll.setWidget(card_content)
        layout.addWidget(self.cards_scroll, 1)
        self.add_button = QPushButton("＋  Add files…")
        self.add_button.setObjectName("quiet")
        self.add_button.clicked.connect(self.pick_frames)
        layout.addWidget(self.add_button)
        layout.addWidget(label("REFERENCE IMAGE", "eyebrow"))
        self.reference_selector = QComboBox()
        self.reference_selector.currentIndexChanged.connect(self._reference_changed)
        layout.addWidget(self.reference_selector)
        self.input_info = label("Add at least two images.", "muted")
        self.input_info.setWordWrap(True)
        self.input_info.setStyleSheet("font-size:10px; color:#95aaa7;")
        layout.addWidget(self.input_info)
        layout.addWidget(label("MERGE METHOD", "eyebrow"))
        self.mode = QComboBox()
        self.mode.addItem("HDR · exposure times / EV", "radiance")
        self.mode.addItem("Exposure fusion · uncalibrated", "fusion")
        self.mode.setToolTip("HDR uses EV values or FITS EXPTIME. Fusion combines displayed exposures and does not provide a linear HDR export.")
        self.mode.currentIndexChanged.connect(self._ev_changed)
        layout.addWidget(self.mode)
        self.merge_button = QPushButton("Align and build HDR  →")
        self.merge_button.setObjectName("primary")
        self.merge_button.clicked.connect(self.merge)
        layout.addWidget(self.merge_button)
        file_note = label("FITS / FITS.gz · PNG · JPEG · TIFF\nDrop a file onto a card to replace its image.", "muted")
        file_note.setStyleSheet("font-size:10px; color:#81959b;")
        file_note.setWordWrap(True)
        layout.addWidget(file_note)
        return rail

    def _build_canvas(self):
        center = QWidget()
        center.setMinimumWidth(370)
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(11)
        row = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(5)
        heading.addWidget(label("02   COMPOSITION", "eyebrow"))
        self.preview_title = label("Moon preview", "section")
        self.preview_title.setStyleSheet("font-size:18px; font-weight:500;")
        heading.addWidget(self.preview_title)
        row.addLayout(heading)
        row.addStretch()
        self.demo_badge = label("DEMO · SYNTHETIC EXPOSURES", "badge")
        self.demo_badge.setVisible(False)
        row.addWidget(self.demo_badge)
        layout.addLayout(row)
        shell = QFrame()
        shell.setObjectName("canvasShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(1, 1, 1, 1)
        shell_layout.setSpacing(0)
        self.canvas = ImageCanvas()
        shell_layout.addWidget(self.canvas, 1)
        tools = QWidget()
        toolbar = QHBoxLayout(tools)
        toolbar.setContentsMargins(12, 9, 12, 9)
        self.compare_button = QToolButton()
        self.compare_button.setText("◐  Before / after")
        self.compare_button.setCheckable(True)
        self.compare_button.setToolTip("Drag the divider: selected reference on the left, result on the right. Scroll to zoom; drag the image to pan.")
        self.compare_button.toggled.connect(self.set_compare)
        toolbar.addWidget(self.compare_button)
        toolbar.addStretch()
        zoom_out = QToolButton()
        zoom_out.setText("−")
        zoom_out.clicked.connect(lambda: self.canvas.zoom_by(1/1.2))
        toolbar.addWidget(zoom_out)
        self.fit_button = QToolButton()
        self.fit_button.setText("Fit")
        self.fit_button.clicked.connect(self.canvas.fit)
        self.canvas.zoomChanged.connect(self.fit_button.setText)
        toolbar.addWidget(self.fit_button)
        zoom_in = QToolButton()
        zoom_in.setText("＋")
        zoom_in.clicked.connect(lambda: self.canvas.zoom_by(1.2))
        toolbar.addWidget(zoom_in)
        shell_layout.addWidget(tools)
        layout.addWidget(shell, 1)
        details = QHBoxLayout()
        self.image_info = label("—", "muted")
        self.image_info.setStyleSheet("font-size: 10px; color: #81979f;")
        details.addWidget(self.image_info, 1)
        self.edit_state = label("LIVE PREVIEW", "eyebrow")
        details.addWidget(self.edit_state)
        layout.addLayout(details)
        alignment = QFrame()
        alignment.setObjectName("rail")
        align_layout = QVBoxLayout(alignment)
        align_layout.setContentsMargins(14, 12, 14, 12)
        align_layout.setSpacing(7)
        row = QHBoxLayout()
        row.addWidget(label("DISK ALIGNMENT", "eyebrow"), 1)
        self.manual_button = QPushButton("Fine-tune…")
        self.manual_button.setObjectName("quiet")
        self.manual_button.clicked.connect(self.manual_alignment)
        row.addWidget(self.manual_button)
        align_layout.addLayout(row)
        self.alignment_info = label("Disk detection → surface feature matching → subpixel alignment", "muted")
        self.alignment_info.setWordWrap(True)
        self.alignment_info.setMinimumHeight(30)
        self.alignment_info.setStyleSheet("font-size: 11px; color: #90a5ad;")
        align_layout.addWidget(self.alignment_info)
        layout.addWidget(alignment)
        return center

    def _build_develop(self):
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(260)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(12)
        row = QHBoxLayout()
        row.addWidget(label("03   DEVELOP", "eyebrow"), 1)
        reset = QPushButton("Reset")
        reset.setObjectName("quiet")
        reset.clicked.connect(self.reset_settings)
        row.addWidget(reset)
        layout.addLayout(row)
        preset_grid = QGridLayout()
        preset_grid.setSpacing(7)
        self.preset_buttons = {}
        for index, name in enumerate(PRESETS):
            button = QPushButton(name)
            button.setObjectName("preset")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, name=name: self.apply_preset(name))
            self.preset_buttons[name] = button
            preset_grid.addWidget(button, index//2, index%2)
        layout.addLayout(preset_grid)
        note = label("Mineral Moon brings out subtle surface color differences.", "muted")
        self.mineral_note = note
        note.setWordWrap(True)
        note.setStyleSheet("font-size:10px; color:#83989f;")
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background: #171c1f;")
        controls = QWidget()
        controls.setObjectName("developControls")
        controls.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sliders = QVBoxLayout(controls)
        sliders.setContentsMargins(0, 2, 6, 3)
        sliders.setSpacing(11)
        self.adjustments = {}
        specs = [("exposure", "Exposure", -300, 300, 0, 100, " EV"),
                 ("contrast", "Contrast", -100, 100, 0, 1, ""),
                 ("highlights", "Highlights", -100, 100, 0, 1, ""),
                 ("shadows", "Shadows", -100, 100, 0, 1, ""),
                 ("white_balance", "Color neutralization", 0, 100, 0, 1, "%"),
                 ("temperature", "Temperature", -100, 100, 0, 1, ""),
                 ("saturation", "Saturation", 0, 200, 100, 1, "%"),
                 ("mineral", "Mineral colors", 0, 100, 0, 1, ""),
                 ("clarity", "Clarity", 0, 100, 0, 1, ""),
                 ("sharpness", "Sharpness", 0, 100, 0, 1, ""),
                 ("denoise", "Noise reduction", 0, 100, 0, 1, "")]
        for key, title, low, high, value, factor, suffix in specs:
            widget = Adjustment(title, low, high, value, factor, suffix)
            if key == "white_balance":
                widget.setToolTip("Balances the average lunar disk color using a neutral-gray assumption. This is a creative adjustment, not a measurement of chemical composition.")
            widget.changed.connect(self.settings_changed)
            self.adjustments[key] = widget
            sliders.addWidget(widget)
        sliders.addSpacing(6)
        sliders.addWidget(label("FINISHING", "eyebrow"))
        sliders.addWidget(label("Background stars", "muted"))
        self.background_mode = QComboBox()
        self.background_mode.addItem("Original background", "original")
        self.background_mode.addItem("Suppress stars", "remove")
        self.background_mode.addItem("Add stars · effect", "add")
        self.background_mode.setToolTip("Added stars are a synthetic visual effect, not an astronomical measurement.")
        self.background_mode.currentIndexChanged.connect(self.finishing_changed)
        sliders.addWidget(self.background_mode)
        self.signature_checkbox = QCheckBox("Add signature")
        self.signature_checkbox.toggled.connect(self.finishing_changed)
        sliders.addWidget(self.signature_checkbox)
        self.signature_input = QLineEdit("Lunar HDR")
        self.signature_input.setPlaceholderText("Your signature")
        self.signature_input.setMaxLength(100)
        self.signature_input.setEnabled(False)
        self.signature_input.textChanged.connect(self.finishing_changed)
        sliders.addWidget(self.signature_input)
        crop_row = QHBoxLayout()
        self.crop_button = QPushButton("Crop…")
        self.crop_button.setObjectName("quiet")
        self.crop_button.clicked.connect(self.edit_crop)
        crop_row.addWidget(self.crop_button, 1)
        self.crop_reset_button = QPushButton("Reset crop")
        self.crop_reset_button.setObjectName("quiet")
        self.crop_reset_button.clicked.connect(self.reset_crop)
        crop_row.addWidget(self.crop_reset_button)
        sliders.addLayout(crop_row)
        self.crop_info = label("Full image", "muted")
        self.crop_info.setStyleSheet("font-size:10px; color:#81979f;")
        sliders.addWidget(self.crop_info)
        sliders.addStretch()
        scroll.setWidget(controls)
        layout.addWidget(scroll, 1)
        self.export_button = QPushButton("Export image  ↗")
        self.export_button.setObjectName("primary")
        self.export_button.clicked.connect(self.export_image)
        self.export_button.setToolTip("PNG, JPEG and TIFF include adjustments, background effects, crop and signature. HDR saves the full linear image without these edits.")
        layout.addWidget(self.export_button)
        export_note = label("PNG / JPEG / TIFF: edited and cropped\nHDR: full linear image, unedited", "muted")
        export_note.setStyleSheet("font-size:10px; color:#81979f;")
        export_note.setWordWrap(True)
        layout.addWidget(export_note)
        return rail

    def settings(self):
        result = {key: control.value() for key, control in self.adjustments.items()}
        if self._all_monochrome():
            result.update(temperature=0, white_balance=0, saturation=100, mineral=0)
        return result

    def finishing_options(self):
        return dict(background=self.background_mode.currentData(), stars_strength=50,
                    signature_enabled=self.signature_checkbox.isChecked(),
                    signature_text=self.signature_input.text(), crop_enabled=self.crop_enabled,
                    crop_rect=tuple(self.crop_rect))

    def finishing_changed(self, *args):
        self.signature_input.setEnabled(self.signature_checkbox.isChecked())
        self._preview_timer.start()

    def edit_crop(self):
        if self._busy or self._preview_base is None:
            return
        options = self.finishing_options()
        options.update(crop_enabled=False, signature_enabled=False)
        pixels = finish_image(engine.adjust_image(self._preview_base, self.settings()), options)
        dialog = CropDialog(pixels, self.crop_rect if self.crop_enabled else (0, 0, 1, 1), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.crop_rect = tuple(dialog.selected_rect())
            self.crop_enabled = not np.allclose(self.crop_rect, (0, 0, 1, 1))
            self._update_crop_info()
            self._preview_timer.start()

    def reset_crop(self):
        self.crop_rect = (0.0, 0.0, 1.0, 1.0)
        self.crop_enabled = False
        self._update_crop_info()
        self._preview_timer.start()

    def _update_crop_info(self):
        self.crop_info.setText(f"Crop {self.crop_rect[2]*100:.1f}% × {self.crop_rect[3]*100:.1f}%" if self.crop_enabled else "Full image")
        self.crop_reset_button.setEnabled(self.crop_enabled and not self._busy)

    def settings_changed(self):
        for button in self.preset_buttons.values():
            button.setChecked(False)
        self._preview_timer.start()

    def apply_preset(self, name):
        for key, value in PRESETS[name].items():
            self.adjustments[key].set_value(value)
        for key, button in self.preset_buttons.items():
            button.setChecked(key == name)
        self._preview_timer.start()

    def reset_settings(self):
        for key, value in DEFAULTS.items():
            self.adjustments[key].set_value(value)
        for button in self.preset_buttons.values():
            button.setChecked(False)
        self.background_mode.setCurrentIndex(0)
        self.signature_checkbox.setChecked(False)
        self.reset_crop()
        self._preview_timer.start()

    def update_preview(self):
        if self._preview_base is None:
            return
        try:
            options = self.finishing_options()
            self._preview_after = finish_image(engine.adjust_image(self._preview_base, self.settings()), options)
            before = self._preview_before
            if before is not None and self.crop_enabled:
                before = finish_image(before, dict(crop_enabled=True, crop_rect=tuple(self.crop_rect)))
            self.canvas.set_images(self._preview_after, before)
        except Exception as exc:
            self.status.setText(f"Could not update the preview: {exc}")

    def set_compare(self, enabled):
        self.canvas.compare = enabled
        self.canvas.update()

    def _all_monochrome(self):
        return bool(self.frames) and all((getattr(frame, "metadata", {}) or {}).get("monochrome", False) for frame in self.frames)

    def _refresh_actions(self):
        ready = len(self.frames) >= 2
        self.merge_button.setEnabled(ready and not self._busy)
        self.export_button.setEnabled(self.composite is not None and not self._busy and not self._merge_dirty)
        self.manual_button.setEnabled(self.automatic_alignment is not None and not self._busy)
        self.demo_button.setEnabled(not self._busy)
        self.load_button.setEnabled(not self._busy)
        self.add_button.setEnabled(not self._busy)
        self.reference_selector.setEnabled(bool(self.frames) and not self._busy)
        self.mode.setEnabled(not self._busy)
        self.crop_button.setEnabled(self._preview_base is not None and not self._busy)
        self._update_crop_info()
        for card in self.cards:
            card.setEnabled(not self._busy)
        self.source_count.setText(f"{len(self.frames)} images")
        mono = self._all_monochrome()
        for key in ("temperature", "white_balance", "saturation", "mineral"):
            self.adjustments[key].setEnabled(not mono)
        self.preset_buttons["Mineral Moon"].setEnabled(not mono)
        self.mineral_note.setText("Monochrome data: color adjustments are disabled because these images contain no mineral color information." if mono else "Mineral Moon enhances existing subtle surface color differences.")

    def _progress(self, value, message):
        self.progress.setValue(max(0, min(100, value)))
        self.status.setText(message)

    def _start_task(self, function, title, complete):
        if self._busy:
            return
        self._busy = True
        self.progress.setValue(0)
        self.status.setText(title)
        self._refresh_actions()
        worker = Task(function, self)
        self._task = worker
        worker.progressed.connect(self._progress)
        worker.result.connect(lambda result: self._task_result(complete, result))
        worker.failed.connect(self._task_error)
        worker.finished.connect(self._task_finished)
        worker.start()

    def _task_result(self, complete, result):
        try:
            complete(result)
        except Exception as exc:
            # Qt otherwise writes callback exceptions only to stderr, invisible in a bundled app.
            self._task_error(f"{exc}\n\n{traceback.format_exc()}")

    def _task_error(self, details):
        self.status.setText("Processing failed. Your source files have not been changed.")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Lunar HDR · processing error")
        box.setText(details.split("\n\n", 1)[0])
        box.setDetailedText(details)
        box.exec()

    def _task_finished(self):
        worker = self._task
        self._task = None
        self._busy = False
        self._refresh_actions()
        if worker is not None:
            worker.deleteLater()

    def pick_frame(self, index):
        if self._busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Replace a lunar exposure", "", IMAGE_FILTER)
        if path:
            self.load_frame(index, path)

    def pick_frames(self):
        if self._busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Add lunar exposures", "", IMAGE_FILTER)
        if paths:
            self.load_frames(paths, append=True)

    def pick_three(self):
        # Backwards-compatible entry point; the picker now accepts any count.
        self.pick_frames()

    def load_frames(self, paths, append=True):
        """Load a batch atomically. A failed file leaves the current session intact."""
        paths = [str(path) for path in paths]
        if not paths or self._busy:
            return
        keep_existing = append and not self._synthetic
        old_frames = list(self.frames) if keep_existing else []
        old_evs = [card.ev.value() for card in self.cards] if keep_existing else []
        old_reference = self.reference_index if keep_existing else 0
        use_metadata = not old_frames or self._ev_from_metadata
        def job(progress):
            loaded = []
            for index, path in enumerate(paths):
                progress(5+int(index*90/len(paths)), f"Loading {index+1}/{len(paths)} · {Path(path).name}…")
                loaded.append(engine.read_image(path))
            progress(100, "All selected images are loaded.")
            return loaded
        def complete(loaded):
            self._apply_frames(old_frames+loaded, old_evs+[0.0]*len(loaded), old_reference, auto_metadata=use_metadata)
            self.status.setText(self._import_summary())
        self._start_task(job, "Loading exposures…", complete)

    def load_frame(self, index, path):
        if self._busy:
            return
        replace_existing = not self._synthetic and 0 <= index < len(self.frames)
        old_frames = list(self.frames) if replace_existing else []
        old_evs = [card.ev.value() for card in self.cards] if replace_existing else []
        old_reference = self.reference_index if replace_existing else 0
        use_metadata = not replace_existing or self._ev_from_metadata
        def job(progress):
            progress(10, "Loading image…")
            return engine.read_image(str(path))
        def complete(frame):
            if replace_existing:
                old_frames[index] = frame
                old_evs[index] = 0.0
                self._apply_frames(old_frames, old_evs, old_reference, auto_metadata=use_metadata)
            else:
                self._apply_frames([frame], [0.0], 0)
            self.status.setText(self._import_summary())
        self._start_task(job, "Loading image…", complete)

    def _metadata_evs(self, reference_index):
        times = [getattr(frame, "exposure_seconds", None) for frame in self.frames]
        if times and all(t is not None and np.isfinite(t) and t > 0 for t in times):
            reference_time = times[reference_index]
            return [math.log2(t/reference_time) for t in times]
        return None

    def _rebuild_cards(self, evs):
        for card in self.cards:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.cards = []
        self.reference_selector.blockSignals(True)
        self.reference_selector.clear()
        for index, (frame, ev) in enumerate(zip(self.frames, evs)):
            title = "Reference" if index == self.reference_index else "Exposure"
            card = ExposureCard(index, title, "", ev)
            card.set_frame(frame)
            card.requested.connect(self.pick_frame)
            card.dropped.connect(self.load_frame)
            card.evChanged.connect(self._card_ev_changed)
            card.removed.connect(self.remove_frame)
            self.cards.append(card)
            self.cards_layout.insertWidget(self.cards_layout.count()-1, card)
            self.reference_selector.addItem(f"{index+1:02d} · {frame.name}", index)
        self.reference_selector.setCurrentIndex(self.reference_index if self.frames else -1)
        self.reference_selector.blockSignals(False)

    def _apply_frames(self, frames, evs, reference_index=0, synthetic=False, auto_metadata=True):
        self.frames = list(frames)
        self.reference_index = min(max(reference_index, 0), max(len(frames)-1, 0))
        self._synthetic = synthetic
        metadata_evs = self._metadata_evs(self.reference_index) if auto_metadata else None
        self._ev_from_metadata = metadata_evs is not None
        if metadata_evs is not None:
            evs = metadata_evs
        self.demo_badge.setVisible(synthetic)
        self._rebuild_cards(evs)
        self._invalidate()
        self._refresh_input_info()
        self._show_source()
        self._refresh_actions()

    def remove_frame(self, index):
        if self._busy or not 0 <= index < len(self.frames):
            return
        frames = list(self.frames)
        evs = [card.ev.value() for card in self.cards]
        del frames[index]
        del evs[index]
        reference = self.reference_index
        if index < reference:
            reference -= 1
        elif index == reference:
            reference = min(reference, max(len(frames)-1, 0))
        if evs:
            offset = evs[reference]
            evs = [ev-offset for ev in evs]
        self._apply_frames(frames, evs, reference, synthetic=self._synthetic, auto_metadata=self._ev_from_metadata)
        self.status.setText(f"Image removed. {len(frames)} exposures remaining." if len(frames)>=2 else "Add at least two images to merge.")

    def _reference_changed(self, position):
        if self._busy or not 0 <= position < len(self.frames) or position == self.reference_index:
            return
        evs = [card.ev.value() for card in self.cards]
        offset = evs[position]
        evs = [ev-offset for ev in evs]
        self._apply_frames(self.frames, evs, position, synthetic=self._synthetic, auto_metadata=self._ev_from_metadata)
        self.status.setText("Reference changed. EV values are now relative to it; rebuild the composition.")

    def _exposure_metadata_warning(self):
        times = [getattr(frame, "exposure_seconds", None) for frame in self.frames]
        times = [time for time in times if time is not None and np.isfinite(time) and time > 0]
        if len(times) < 2:
            return ""
        ratio = max(times)/min(times)
        if ratio <= 1000:
            return ""
        return f"EXPTIME range is {ratio:.0f}×: verify stack normalization or choose fusion. EV values have been preserved."

    def _refresh_input_info(self):
        if not self.frames:
            self.input_info.setText("Add at least two images.")
            self.input_info.setToolTip("")
            return
        if self._synthetic:
            text = "Demo: synthetic exposures with EV values relative to the reference."
        elif self._ev_from_metadata:
            text = "EV values from EXPTIME / EXPOSURE, relative to the reference."
        else:
            text = "EV values are manual. New images start at 0; enter the actual exposure differences."
        mono_count = sum(bool((getattr(frame, "metadata", {}) or {}).get("monochrome")) for frame in self.frames)
        if mono_count:
            text += f"\nMonochrome images: {mono_count}."
        warnings = [f"{frame.name}: {warning}" for frame in self.frames for warning in getattr(frame, "warnings", [])]
        exposure_warning = self._exposure_metadata_warning()
        if exposure_warning:
            text += "\n" + exposure_warning
            warnings.insert(0, exposure_warning)
        if warnings:
            text += f"\nImport warnings: {len(warnings)} (hover for details)."
        self.input_info.setText(text)
        self.input_info.setToolTip("\n".join(warnings) or text)

    def _import_summary(self):
        warnings = [warning for frame in self.frames for warning in getattr(frame, "warnings", [])]
        exposure_warning = self._exposure_metadata_warning()
        if exposure_warning:
            warnings.insert(0, exposure_warning)
        base = f"Loaded {len(self.frames)} images. "
        base += "EV values loaded from exposure times." if self._ev_from_metadata else "Check the manual EV values; zero does not mean the exposure was detected."
        self.status.setToolTip("\n\n".join(str(w) for w in warnings))
        if exposure_warning:
            return base + " " + exposure_warning
        return base + (f" · {len(warnings)} warnings (hover for details)." if warnings else "")

    def _card_ev_changed(self):
        self._ev_from_metadata = False
        self._refresh_input_info()
        self._ev_changed()

    def _invalidate(self):
        self.automatic_alignment = None
        self.alignment = None
        self.composite = None
        self._merge_dirty = True
        self.corrections = [{} for _ in self.frames]
        self.alignment_info.setText("Ready to align lunar disks and surface details automatically.")
        self.preview_title.setText("Reference image")

    def _show_source(self):
        if not self.frames:
            self._preview_base = self._preview_before = self._preview_after = None
            self.canvas.after = self.canvas.before = None
            self.canvas.update()
            self.image_info.setText("—")
            return
        frame = self.frames[self.reference_index]
        self._preview_base = preview_size(frame.pixels)
        self._preview_before = self._preview_base.copy()
        self.update_preview()
        self.canvas.fit()
        height, width = frame.pixels.shape[:2]
        metadata = getattr(frame, "metadata", {}) or {}
        kind = "FITS · mono" if metadata.get("monochrome") else "RGB"
        self.image_info.setText(f"{width:,} × {height:,} px · reference {self.reference_index+1:02d} · {kind}".replace(",", " "))

    def load_demo(self):
        path = Path(__file__).resolve().parent / "assets" / "demo_reference.png"
        if self._busy or not path.exists():
            return
        def job(progress):
            progress(10, "Preparing the synthetic demo…")
            source = engine.read_image(str(path)).pixels
            h, w = source.shape[:2]
            linear = np.where(source <= 0.04045, source/12.92, ((source+0.055)/1.055)**2.4)
            frames = []
            for index, (ev, angle, scale, dx, dy) in enumerate([(-2, 0.6, 1.012, 13, -9), (0, 0, 1, 0, 0), (2, -0.5, 0.988, -11, 8)]):
                shifted = np.clip(linear * (2.0**ev), 0, 1)
                pixels = np.where(shifted <= 0.0031308, shifted*12.92, 1.055*shifted**(1/2.4)-0.055)
                if index != 1:
                    matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, scale)
                    matrix[:, 2] += (dx, dy)
                    pixels = cv2.warpAffine(pixels, matrix, (w, h), flags=cv2.INTER_LINEAR,
                                            borderMode=cv2.BORDER_CONSTANT)
                frames.append(engine.ImageFrame(path=f"demo://exposure-{ev:+d}",
                                                name=f"Demo {ev:+d} EV", pixels=pixels.astype(np.float32), bit_depth=8))
            progress(100, "The demo is ready.")
            return frames
        def complete(frames):
            self._apply_frames(frames, [-2.0, 0.0, 2.0], 1, synthetic=True, auto_metadata=False)
            self.preview_title.setText("Mineral Moon · demo")
            self.status.setText("Demo: three synthetic exposures from a reference image. Adding your own files replaces the demo.")
        self._start_task(job, "Loading demo…", complete)

    def _ev_changed(self, *args):
        if self.composite is not None:
            self._merge_dirty = True
            self._refresh_actions()
            self.status.setText("EV values or the merge method changed. Click Align and build HDR for a new result.")

    def merge(self):
        if self._busy or len(self.frames) < 2:
            return
        frames = list(self.frames)
        evs = [card.ev.value() for card in self.cards]
        mode = self.mode.currentData()
        reference_index = self.reference_index
        def job(progress):
            automatic = engine.align_images(frames, reference_index=reference_index,
                                            progress=lambda n, message: progress(int(n*0.64), message))
            composite = engine.merge_hdr(automatic, evs=evs, mode=mode,
                                         progress=lambda n, message: progress(64+int(n*0.36), message))
            return automatic, composite
        def complete(result):
            self.automatic_alignment, self.composite = result
            self.alignment = self.automatic_alignment
            self.corrections = [{} for _ in self.frames]
            self._show_composite()
        self._start_task(job, "Matching lunar disks and surface details…", complete)

    def _show_composite(self):
        self._merge_dirty = False
        self._preview_base = preview_size(self.composite.base)
        self._preview_before = preview_size(self.frames[self.reference_index].pixels)
        self.update_preview()
        self.preview_title.setText("Lunar HDR" if self.composite.mode == "radiance" else "Lunar · exposure fusion")
        h, w = self.composite.base.shape[:2]
        self.image_info.setText(f"{w:,} × {h:,} px  ·  {len(self.frames)} exposures  ·  {'HDR radiance' if self.composite.linear is not None else 'Exposure fusion'}".replace(",", " "))
        lines = []
        for index in range(len(self.frames)):
            if index == self.reference_index:
                continue
            matrix = self.alignment.matrices[index]
            scale = float(math.hypot(matrix[0, 0], matrix[1, 0]))
            rotation = float(math.degrees(math.atan2(matrix[1, 0], matrix[0, 0])))
            name = f"{index+1:02d}"
            report = self.alignment.reports[index]
            confidence = float(report.get("confidence", 0))
            verification = "check manually" if report.get("warning") else f"confidence {confidence:.0%}"
            lines.append(f"{name}: Δx {matrix[0, 2]:+.1f} px · Δy {matrix[1, 2]:+.1f} px · {rotation:+.2f}° · {scale:.4f}× · {verification}")
        visible = lines[:3]
        if len(lines) > 3:
            visible.append(f"+ {len(lines)-3} more images · details in Fine-tune…")
        self.alignment_info.setText("\n".join(visible))
        reports = getattr(self.alignment, "reports", [])
        self.alignment_info.setToolTip("\n".join(
            f"{report.get('name', '')}: {report.get('method', '')} · {report.get('inliers', 0)} points\n{report.get('warning', '')}"
            for report in reports))
        warnings = list(getattr(self.composite, "warnings", []))
        exposure_warning = self._exposure_metadata_warning()
        if exposure_warning:
            warnings.insert(0, exposure_warning)
        self.status.setText("HDR is ready. Adjust the look and export." if not warnings else
                            f"Composition is ready · {len(warnings)} warnings. Hover over this message for details.")
        self.status.setToolTip("\n\n".join(str(w) for w in warnings))
        self.progress.setValue(100)

    def manual_alignment(self):
        if self.automatic_alignment is None or self._busy:
            return
        dialog = ManualAlignmentDialog(self.corrections, self.automatic_alignment.reports, self,
                                       alignment=self.automatic_alignment, frames=self.frames)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        corrections = dialog.corrections()
        baseline = self.automatic_alignment
        frames = list(self.frames)
        evs = [card.ev.value() for card in self.cards]
        mode = self.mode.currentData()
        def job(progress):
            progress(5, "Applying alignment corrections…")
            adjusted = baseline
            for index in range(len(frames)):
                correction = corrections[index]
                changed = any(abs(correction.get(key, default)-default) > 1e-10
                              for key, default in (("dx", 0), ("dy", 0), ("rotation", 0), ("scale", 1)))
                if index != baseline.reference_index and changed:
                    adjusted = engine.manual_alignment(adjusted, frames, index, **correction)
            composite = engine.merge_hdr(adjusted, evs=evs, mode=mode,
                                         progress=lambda n, message: progress(20+int(n*.8), message))
            return adjusted, composite
        def complete(result):
            self.alignment, self.composite = result
            self.corrections = corrections
            self._show_composite()
        self._start_task(job, "Rebuilding the composition…", complete)

    def export_image(self):
        if self._busy or self.composite is None or self._merge_dirty:
            return
        available_formats = EXPORT_FORMATS if self.composite.linear is not None else EXPORT_FORMATS[:-1]
        filters = ";;".join(item[0] for item in available_formats)
        directory = self._export_directory
        if directory is None or not directory.is_dir() or not os.access(directory, os.W_OK):
            directory = default_export_directory()
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Lunar HDR", str(directory / "Lunar-HDR.png"), filters,
            EXPORT_FORMATS[0][0], options=QFileDialog.Option.DontUseNativeDialog)
        if not path:
            return
        try:
            destination = Path(path).expanduser()
            if not destination.is_absolute():
                destination = directory / destination
            path = resolve_export_path(str(destination), selected_filter)
        except (TypeError, ValueError, OSError) as exc:
            self._task_error(f"Could not prepare the export path: {exc}")
            return
        settings = self.settings()
        finishing = self.finishing_options()
        composite = self.composite
        if Path(path).suffix.lower() == ".hdr" and composite.linear is None:
            QMessageBox.information(self, "Linear HDR is unavailable", "Exposure fusion has no linear radiance. Choose PNG, JPEG or TIFF, or rebuild the result in HDR mode.")
            return
        def job(progress):
            progress(10, "Preparing a full-resolution export…")
            try:
                if Path(path).suffix.lower() == ".hdr":
                    engine.write_image(path, composite.base, linear_hdr=composite.linear)
                else:
                    pixels = finish_image(engine.adjust_image(composite.base, settings), finishing)
                    progress(70, "Writing image…")
                    engine.write_image(path, pixels)
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
                    raise OSError(exc.errno,
                                  f"Cannot write to '{Path(path).parent}'. Choose Pictures or another writable folder when exporting.",
                                  path) from exc
                raise
            progress(100, "Export complete.")
            return path
        def complete(saved):
            self._export_directory = Path(saved).parent
            self.status.setText(f"Exported: {saved}" + (" · full linear radiance without adjustments, crop or signature" if Path(saved).suffix.lower()==".hdr" else ""))
        self._start_task(job, "Exporting image…", complete)

    def closeEvent(self, event):
        self._onboarding_timer.stop()
        if self._task is not None and self._task.isRunning():
            QMessageBox.information(self, "Processing in progress", "Wait for the current operation to finish before closing.")
            event.ignore()
            return
        if self._help_dialog is not None:
            self._help_dialog.close()
        super().closeEvent(event)
