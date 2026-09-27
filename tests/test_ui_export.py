"""Regressions for save destinations, finishing controls and Qt callbacks."""
import errno
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from lunarhdr import engine, ui


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qt_app, monkeypatch):
    monkeypatch.setattr(ui.MainWindow, "load_demo", lambda self: None)
    result = ui.MainWindow()
    pixels = np.full((24, 32, 3), 0.4, np.float32)
    result.composite = engine.Composite(pixels, pixels * 3, "radiance", [])
    result._preview_base = pixels.copy()
    result._preview_before = pixels.copy()
    result._merge_dirty = False
    result.errors = []
    monkeypatch.setattr(result, "_task_error", result.errors.append)
    result._refresh_actions()
    yield result
    result._preview_timer.stop()
    if result._task is not None:
        result._task.wait(5000)
        qt_app.processEvents()
    result.close()
    result.deleteLater()
    qt_app.processEvents()


def wait_for_export(window, qt_app):
    deadline = time.monotonic() + 8
    while window._busy and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.005)
    qt_app.processEvents()
    assert not window._busy, "export worker did not complete"


@pytest.mark.parametrize("filename,filter_name,expected", [
    ("moon.png", "", "moon.png"),
    ("moon.tiff", "", "moon.tiff"),
    ("moon.hdr", "", "moon.hdr"),
    ("moon", "", "moon.png"),
    ("moon.png", "16-bit TIFF (*.tif)", "moon.tif"),
    ("moon.png", "TIFF image (*.tiff)", "moon.tif"),
    ("moon.JPEG", "JPEG (*.jpg)", "moon.JPEG"),
    ("moon.tif", "unrecognized native label", "moon.tif"),
])
def test_native_dialog_format_resolution(filename, filter_name, expected):
    assert ui.resolve_export_path(filename, filter_name) == expected


def test_save_dialog_default_is_absolute_when_launched_from_root(window, monkeypatch, tmp_path):
    pictures = tmp_path / "Pictures"
    pictures.mkdir()
    monkeypatch.setattr(ui.QStandardPaths, "writableLocation", staticmethod(lambda location: str(pictures)))
    monkeypatch.chdir("/")
    captured = {}
    def dialog(*args, **kwargs):
        captured.update(directory=args[2], selected=args[4], options=kwargs["options"])
        return "", ""
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(dialog))
    window.export_image()
    assert Path(captured["directory"]) == pictures / "Lunar-HDR.png"
    assert Path(captured["directory"]).is_absolute()
    assert captured["selected"] == "PNG (*.png)"
    assert captured["options"] & QFileDialog.Option.DontUseNativeDialog


def test_missing_pictures_directory_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.setattr(ui.QStandardPaths, "writableLocation", staticmethod(lambda location: str(tmp_path / "missing")))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert ui.default_export_directory() == tmp_path
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("suffix,expected_dtype", [(".png", np.uint8), (".tif", np.uint16), (".hdr", np.float32)])
def test_empty_native_filter_still_exports(window, qt_app, monkeypatch, tmp_path, suffix, expected_dtype):
    destination = tmp_path / ("mesiac žltý" + suffix)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(destination), "")))
    window.export_image()
    wait_for_export(window, qt_app)
    assert window.errors == []
    assert destination.is_file()
    decoded = cv2.imdecode(np.fromfile(destination, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    assert decoded.dtype == expected_dtype
    assert window.export_button.isEnabled()
    assert str(destination) in window.status.text()
    assert window._export_directory == tmp_path


def test_relative_dialog_return_uses_export_folder_not_process_root(window, qt_app, monkeypatch, tmp_path):
    window._export_directory = tmp_path
    monkeypatch.chdir("/")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("moon.png", "")))
    window.export_image()
    wait_for_export(window, qt_app)
    assert window.errors == []
    assert (tmp_path / "moon.png").is_file()


def test_write_failure_is_visible_and_export_can_retry(window, qt_app, monkeypatch, tmp_path):
    destination = tmp_path / "moon.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(destination), "PNG (*.png)")))
    real_write = engine.write_image
    def fail(*args, **kwargs):
        raise OSError(errno.EROFS, "Read-only file system", str(destination))
    monkeypatch.setattr(engine, "write_image", fail)
    window.export_image()
    wait_for_export(window, qt_app)
    assert len(window.errors) == 1 and str(tmp_path) in window.errors[0]
    assert "Obrázky" in window.errors[0]
    assert not destination.exists()
    assert window.export_button.isEnabled()
    monkeypatch.setattr(engine, "write_image", real_write)
    window.export_image()
    wait_for_export(window, qt_app)
    assert destination.exists()


def test_completion_callback_exception_is_visible(window):
    def fail(_result):
        raise ValueError("completion callback failed")
    window._task_result(fail, "moon.png")
    assert len(window.errors) == 1
    assert "completion callback failed" in window.errors[0]


def test_busy_export_does_not_open_a_second_dialog(window, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("save dialog opened during active work")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", unexpected)
    window._busy = True
    try:
        window.export_image()
    finally:
        window._busy = False


def test_finishing_crop_matches_preview_comparison_and_raster_export(window, qt_app, monkeypatch, tmp_path):
    window.background_mode.setCurrentIndex(2)
    window.signature_checkbox.setChecked(True)
    window.signature_input.setText("Lunar test")
    window.crop_rect = (.25, .25, .5, .5)
    window.crop_enabled = True
    window.update_preview()
    assert window.finishing_options()["background"] == "add"
    assert window.finishing_options()["signature_text"] == "Lunar test"
    assert window.canvas.after.width() == window.canvas.before.width() == 16
    assert window.canvas.after.height() == window.canvas.before.height() == 12
    destination = tmp_path / "finished.tif"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(destination), "16-bit TIFF (*.tif)")))
    window.export_image()
    wait_for_export(window, qt_app)
    assert not window.errors
    decoded = cv2.imread(str(destination), cv2.IMREAD_UNCHANGED)[..., ::-1]
    assert decoded.shape == (12, 16, 3)
    np.testing.assert_allclose(decoded.astype(np.float32)/65535, window._preview_after, atol=2/65535)


def test_linear_hdr_bypasses_crop_background_signature_and_development(window, qt_app, monkeypatch, tmp_path):
    window.background_mode.setCurrentIndex(2)
    window.signature_checkbox.setChecked(True)
    window.crop_rect = (.25, .25, .5, .5)
    window.crop_enabled = True
    window.adjustments["exposure"].set_value(2)
    destination = tmp_path / "linear.hdr"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(destination), "Lineárna radiancia HDR bez úprav (*.hdr)")))
    window.export_image()
    wait_for_export(window, qt_app)
    decoded = cv2.imread(str(destination), cv2.IMREAD_UNCHANGED)[..., ::-1]
    assert decoded.shape == window.composite.linear.shape
    np.testing.assert_allclose(decoded, window.composite.linear, atol=.01)


def test_crop_mouse_selection_and_reset(qt_app):
    pixels = np.full((100, 100, 3), .5, np.float32)
    crop = ui.CropCanvas(pixels)
    crop.resize(600, 400)
    crop.show()
    qt_app.processEvents()
    rect = crop.image_rect()
    start = QPoint(round(rect.x()+rect.width()*.2), round(rect.y()+rect.height()*.3))
    end = QPoint(round(rect.x()+rect.width()*.8), round(rect.y()+rect.height()*.9))
    QTest.mousePress(crop, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(crop, end)
    QTest.mouseRelease(crop, Qt.MouseButton.LeftButton, pos=end)
    np.testing.assert_allclose(crop.crop_rect, (.2, .3, .6, .6), atol=.005)
    crop.reset()
    assert crop.crop_rect == (0., 0., 1., 1.)
    crop.close()
    crop.deleteLater()


def test_develop_reset_also_clears_finishing_but_preserves_signature_text(window):
    window.background_mode.setCurrentIndex(2)
    window.signature_checkbox.setChecked(True)
    window.signature_input.setText("My lunar image")
    window.crop_rect = (.2, .2, .5, .5)
    window.crop_enabled = True
    window.reset_settings()
    options = window.finishing_options()
    assert options["background"] == "original"
    assert not options["signature_enabled"] and not options["crop_enabled"]
    assert options["crop_rect"] == (0., 0., 1., 1.)
    assert options["signature_text"] == "My lunar image"
