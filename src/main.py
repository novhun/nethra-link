"""
main.py
-------
QApplication entry point for NethraLink.

Usage (from project root, with venv activated):
    python src/main.py

The script ensures the `src/` directory is on sys.path so that all
internal package imports work regardless of where the script is invoked.
"""

import sys
import os

# ── Path setup ──────────────────────────────────────────────────────────────
# Add 'src/' to the module search path so that 'from gui import …' etc. work
# when the script is run as: python src/main.py  (from the project root).
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# ── Qt imports ──────────────────────────────────────────────────────────────
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

# ── App imports ─────────────────────────────────────────────────────────────
from gui.main_window import MainWindow
import gui.main_window
print(f"DEBUG: Loading MainWindow from {gui.main_window.__file__}")


def main() -> int:
    """
    Create the QApplication, apply global font, show the window, and
    start the event loop.

    Returns
    -------
    int
        The exit code returned by QApplication.exec().
    """
    # High-DPI rendering (enabled by default in PyQt6 ≥ 6.0)
    app = QApplication(sys.argv)
    app.setApplicationName("NethraLink")
    app.setOrganizationName("IT & Media Department")
    app.setApplicationVersion("1.0.0")

    # Set a clean, modern default font
    default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)

    # Instantiate and show the main window
    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
