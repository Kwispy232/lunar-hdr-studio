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
    window = MainWindow()
    window.setWindowIcon(app.windowIcon())
    window.show()
    if "--smoke-test" in sys.argv:
        # A successful boot includes the bundled image and the asynchronous
        # preview worker, not just creating an empty top-level window.
        from time import monotonic
        deadline = monotonic() + 30
        smoke_timer = QTimer(window)

        def check_startup():
            if not window._busy and len(window.frames) == 3 and window._preview_base is not None:
                smoke_timer.stop()
                app.exit(0)
            elif monotonic() >= deadline:
                smoke_timer.stop()
                app.exit(1)

        smoke_timer.timeout.connect(check_startup)
        smoke_timer.start(100)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
