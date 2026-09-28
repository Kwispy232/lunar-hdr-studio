import os
import sys
from pathlib import Path


def main():
    # OpenCV's headless distribution avoids a competing Qt installation.
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from lunarhdr.ui import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Lunar HDR Studio")
    app.setOrganizationName("LunarHDR")
    from lunarhdr import __version__
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    icon = Path(__file__).parent / "assets" / "icon.svg"
    app.setWindowIcon(QIcon(str(icon)))
    smoke_test = "--smoke-test" in sys.argv
    window = MainWindow(show_onboarding=not smoke_test)
    window.setWindowIcon(app.windowIcon())
    window.show()
    if smoke_test:
        # A successful boot includes the bundled image and the asynchronous
        # preview worker and offline guide, not just an empty window. Avoid
        # changing the user's first-run preference during this check.
        from time import monotonic
        deadline = monotonic() + 30
        smoke_timer = QTimer(window)

        def check_startup():
            if not window._busy and len(window.frames) == 3 and window._preview_base is not None:
                smoke_timer.stop()
                from lunarhdr.help_dialog import HelpDialog
                guide = HelpDialog(window, initial_topic="export")
                ready = (guide.topic_list.count() == 8
                         and "16-bit TIFF" in guide.content.toPlainText())
                app.exit(0 if ready else 1)
            elif monotonic() >= deadline:
                smoke_timer.stop()
                app.exit(1)

        smoke_timer.timeout.connect(check_startup)
        smoke_timer.start(100)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
