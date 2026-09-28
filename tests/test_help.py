"""Behavioral coverage for the searchable guide and persistent first-run welcome."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from lunarhdr import engine, ui
from lunarhdr.help_dialog import HelpDialog


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "onboarding.ini"), QSettings.Format.IniFormat)


def wait_until(qt_app, condition, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if condition():
            return
        QTest.qWait(5)
    assert condition(), "Qt behavior did not complete before the deadline"


@pytest.fixture
def make_window(qt_app, monkeypatch, settings):
    monkeypatch.setattr(ui.MainWindow, "load_demo", lambda self: None)
    windows = []

    def create(**kwargs):
        window = ui.MainWindow(settings=kwargs.pop("settings", settings), **kwargs)
        windows.append(window)
        return window

    yield create
    for window in windows:
        window.close()
        window.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()


@pytest.fixture
def guide(qt_app):
    dialog = HelpDialog()
    dialog.show()
    qt_app.processEvents()
    yield dialog
    dialog.close()
    dialog.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_first_visible_launch_shows_guide_once_and_persists_dismissal(make_window, settings, qt_app):
    first = make_window()
    assert not settings.value("onboarding/seen_v1", False, type=bool)
    assert getattr(first, "_help_dialog", None) is None
    first.show()
    wait_until(qt_app, lambda: getattr(first, "_help_dialog", None) is not None
               and first._help_dialog.isVisible())
    assert first._help_dialog.current_topic == "quick-start"
    # Merely displaying the guide must not suppress the next welcome.
    assert not settings.value("onboarding/seen_v1", False, type=bool)
    QTest.mouseClick(first._help_dialog.close_button, Qt.MouseButton.LeftButton)
    wait_until(qt_app, lambda: not first._help_dialog.isVisible())
    settings.sync()
    assert settings.value("onboarding/seen_v1", False, type=bool)
    first.close()

    fresh_settings = QSettings(settings.fileName(), QSettings.Format.IniFormat)
    second = make_window(settings=fresh_settings)
    second.show()
    QTest.qWait(350)
    assert getattr(second, "_help_dialog", None) is None or not second._help_dialog.isVisible()
    second.hide()
    second.show()
    QTest.qWait(150)
    assert getattr(second, "_help_dialog", None) is None or not second._help_dialog.isVisible()


def test_onboarding_opt_out_does_not_change_saved_preference(make_window, settings, qt_app):
    window = make_window(show_onboarding=False)
    window.show()
    QTest.qWait(350)
    assert getattr(window, "_help_dialog", None) is None
    assert not settings.value("onboarding/seen_v1", False, type=bool)


def test_closing_window_before_welcome_timer_does_not_open_or_mark_guide(make_window, settings, qt_app):
    window = make_window()
    window.show()
    window.close()
    QTest.qWait(350)
    assert getattr(window, "_help_dialog", None) is None or not window._help_dialog.isVisible()
    assert not settings.value("onboarding/seen_v1", False, type=bool)


def test_help_reopens_existing_guide_at_requested_topic_without_changing_edit(make_window, qt_app):
    window = make_window(show_onboarding=False)
    pixels = np.full((24, 32, 3), 0.4, np.float32)
    window.composite = engine.Composite(pixels, pixels * 2, "radiance", [])
    window._preview_base = pixels.copy()
    window._preview_before = pixels.copy()
    window._merge_dirty = False
    window.adjustments["exposure"].set_value(1.2)
    window.adjustments["mineral"].set_value(35)
    window.signature_input.setText("My Moon")
    window.signature_checkbox.setChecked(True)
    window.crop_rect, window.crop_enabled = (.1, .2, .6, .5), True
    window.update_preview()
    edit_settings = window.settings().copy()
    finishing = window.finishing_options().copy()
    preview = window._preview_after.copy()
    composite = window.composite
    window.show()
    window.show_help("alignment")
    dialog = window._help_dialog
    assert dialog.isVisible() and dialog.current_topic == "alignment"
    dialog.search_input.setText("export")
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    wait_until(qt_app, lambda: not dialog.isVisible())

    window.show_help("export")
    assert window._help_dialog is dialog
    assert dialog.isVisible() and dialog.current_topic == "export"
    assert dialog.search_input.text() == ""
    dialog.reject()
    assert window.settings() == edit_settings
    assert window.finishing_options() == finishing
    assert window.composite is composite
    np.testing.assert_array_equal(window._preview_after, preview)
    assert not window._merge_dirty


def test_header_menu_and_f1_open_help_without_duplicate_dialogs(make_window, qt_app):
    window = make_window(show_onboarding=False)
    window.show()
    qt_app.processEvents()
    QTest.mouseClick(window.help_button, Qt.MouseButton.LeftButton)
    guide = window._help_dialog
    assert guide.isVisible() and guide.current_topic == "quick-start"
    guide.reject()

    help_menu = next(action.menu() for action in window.menuBar().actions()
                     if action.text().replace("&", "") == "Help")
    user_guide = next(action for action in help_menu.actions() if action.text() == "User guide")
    user_guide.trigger()
    assert window._help_dialog is guide
    assert guide.isVisible() and guide.current_topic == "import"
    guide.reject()

    window.activateWindow()
    qt_app.processEvents()
    QTest.keyClick(window, Qt.Key.Key_F1)
    wait_until(qt_app, lambda: guide.isVisible())
    assert window._help_dialog is guide
    assert guide.current_topic == "quick-start"


def test_topic_navigation_search_and_no_results_recovery(guide, qt_app):
    assert guide.current_topic == "quick-start"
    assert not guide.previous_button.isEnabled()
    assert guide.next_button.isEnabled()
    QTest.mouseClick(guide.next_button, Qt.MouseButton.LeftButton)
    assert guide.current_topic == "import"
    assert "FITS" in guide.content.toPlainText()
    QTest.mouseClick(guide.previous_button, Qt.MouseButton.LeftButton)
    assert guide.current_topic == "quick-start"

    # Search article text, rather than only the short navigation headings.
    guide.search_input.setText("WHITE BALANCE")
    qt_app.processEvents()
    matches = []
    while True:
        matches.append(guide.current_topic)
        assert "white balance" in guide.content.toPlainText().casefold()
        if not guide.next_button.isEnabled():
            break
        QTest.mouseClick(guide.next_button, Qt.MouseButton.LeftButton)
    assert "develop" in matches
    assert len(matches) == len(set(matches))

    guide.search_input.setText("no-such-lunar-guide-topic-918273")
    qt_app.processEvents()
    assert guide.current_topic is None
    assert "no matching topics" in guide.content.toPlainText().casefold()
    assert not guide.next_button.isEnabled() and not guide.previous_button.isEnabled()

    guide.select_topic("export")
    assert guide.search_input.text() == ""
    assert guide.current_topic == "export"
    assert "HDR" in guide.content.toPlainText()
    guide.select_topic("unknown-topic")
    assert guide.current_topic == "quick-start"


def test_escape_dismissal_is_recorded_and_manual_help_remains_available(make_window, settings, qt_app):
    window = make_window()
    window.show()
    wait_until(qt_app, lambda: getattr(window, "_help_dialog", None) is not None
               and window._help_dialog.isVisible())
    guide = window._help_dialog
    QTest.keyClick(guide, Qt.Key.Key_Escape)
    wait_until(qt_app, lambda: settings.value("onboarding/seen_v1", False, type=bool))
    assert guide.result() == QDialog.DialogCode.Rejected
    window.show_help()
    assert guide.isVisible()
    assert guide.current_topic == "quick-start"
