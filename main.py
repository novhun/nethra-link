import sys
import os
import logging
import ctypes
from pathlib import Path

# Ensure Windows taskbar correctly groups the app and shows the icon
if os.name == 'nt':
    myappid = 'novhun.nethralink.camera.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Add 'src' to path so modules like 'gui', 'server' are found
_ROOT = os.path.abspath(".")
_SRC = os.path.join(_ROOT, "src")
if getattr(sys, 'frozen', False):
    # In bundle, 'src' is at the top level of _MEIPASS
    _SRC = sys._MEIPASS

if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt

# Import from 'src' subfolders (now top-level in sys.path)
from gui.main_window import MainWindow

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NethraLink")
    app.setWindowIcon(QIcon(get_resource_path("assets/icon.png")))
    
    default_font = QFont("Segoe UI", 10)
    app.setFont(default_font)

    window = MainWindow()
    window.show()

    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
