"""
Pickems — entry point.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from ui.main_window import MainWindow
import traceback


def excepthook(exc_type, exc_value, exc_tb):
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print("FATAL ERROR:\n", tb, file=sys.stderr)
    try:
        with open("crash.log", "w", encoding="utf-8") as f:
            f.write(tb)
    except Exception:
        pass
    sys.exit(1)


import sys
sys.excepthook = excepthook


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Pickems")
    app.setOrganizationName("Pickems")

    from PyQt6.QtCore import QFileSystemWatcher

    # Load stylesheet and watch for changes to live reload
    style_path = Path(__file__).parent / "ui" / "styles.qss"
    if style_path.exists():
        with open(style_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

        watcher = QFileSystemWatcher()
        watcher.addPath(str(style_path))

        def reload_stylesheet(path: str) -> None:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    app.setStyleSheet(f.read())
            except Exception:
                pass

        watcher.fileChanged.connect(reload_stylesheet)
        app.style_watcher = watcher  # Keep reference alive

    # Set a sensible default font
    font = QFont()
    font.setFamilies(["Inter", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "Helvetica Neue", "Arial"])
    font.setPointSize(9)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
