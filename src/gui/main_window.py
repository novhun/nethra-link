"""
main_window.py
--------------
Top-level PyQt6 MainWindow for NethraLink v2.

Owns:
  - WebSocketServer  (aiohttp, runs in a daemon thread)
  - VideoWorker      (QThread – reads frames from the server's queue)
  - ConnectionTab    (Wi-Fi QR + USB/ADB panel)
  - LiveFeedTab      (video canvas, screenshot, stop)
  - Status bar       (connection state + PC IP + port)
"""

import os
import queue
import logging

from PyQt6.QtCore import Qt, QSize, pyqtSlot, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel, QApplication, QPushButton
)

from networking.ip_discovery import get_local_ip
from qr.generator import generate_qr
from video.worker import VideoWorker
from server.ws_server import WebSocketServer
from gui.widgets import ConnectionTab, LiveFeedTab


# ── Constants ───────────────────────────────────────────────────────────────

APP_TITLE    = "NethraLink – Wireless Camera Bridge"
QR_OUT_PATH  = os.path.join("assets", "qr_code.png")
SERVER_PORT  = 9000

DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #0D0F1A;
    color: #E0E6FF;
}
QTabWidget::pane {
    border: none;
}
QTabBar::tab {
    background: #1A1D2E;
    color: #7080AA;
    padding: 10px 24px;
    font-weight: 600;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: #4A6CF7;
    color: white;
}
QStatusBar {
    background: #090B15;
    color: #6070A0;
}
"""


# ══════════════════════════════════════════════════════════════════════════
#  MainWindow
# ══════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """
    Application shell that wires the WebSocket server, video worker,
    and UI tabs together.
    """

    def __init__(self) -> None:
        super().__init__()
        self._worker: VideoWorker | None = None

        # ── Shared frame queue (server → worker) ───────────────────────────
        self._frame_queue: queue.Queue = queue.Queue(maxsize=8)

        self._pc_ip = get_local_ip()
        self._proto = "https"
        self._qr_path = generate_qr(
            f"{self._proto}://{self._pc_ip}:{SERVER_PORT}",
            QR_OUT_PATH,
        )

        # ── Window ────────────────────────────────────────────────────────
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(QSize(860, 660))
        self.setStyleSheet(DARK_STYLE)

        self._build_tabs()
        self._build_status_bar()
        self._connect_signals()

        # ── Start the WebSocket / HTTP server ──────────────────────────────
        self._server = WebSocketServer(port=SERVER_PORT, frame_queue=self._frame_queue)
        self._server.set_callbacks(
            on_connect=self._on_phone_connected,
            on_disconnect=self._on_phone_disconnected,
        )
        self._server.start()

        # Server and UI are already initialized

    # ── UI construction ────────────────────────────────────────────────────

    def _build_tabs(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._connection_tab = ConnectionTab(
            pc_ip=self._pc_ip,
            qr_image_path=self._qr_path,
            server_port=SERVER_PORT,
        )
        self._tabs.addTab(self._connection_tab, "🔗  Connection")

        self._live_tab = LiveFeedTab()
        self._tabs.addTab(self._live_tab, "📹  Live Feed")

        self.setCentralWidget(self._tabs)

    def _build_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._status_label = QLabel("● Disconnected")
        self._status_label.setStyleSheet("color:#E74C3C;font-weight:600;")
        self._status_bar.addWidget(self._status_label)

        self._status_bar.addWidget(QLabel("  |  "))

        self._ip_label = QLabel(f"PC: {self._proto}://{self._pc_ip}:{SERVER_PORT}")
        self._ip_label.setStyleSheet("color:#7EB8F7; font-weight:bold;")
        self._status_bar.addWidget(self._ip_label)

        self._phone_label = QLabel("")
        self._phone_label.setStyleSheet("color:#27AE60;font-weight:600;")
        self._status_bar.addPermanentWidget(self._phone_label)

        import webbrowser
        test_btn = QPushButton("🌐 Test Server")
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setStyleSheet(
            "QPushButton{background:#1E2236; color:#7EB8F7; border:1px solid #2A2F50; "
            "border-radius:6px; padding:2px 8px; font-size:10px; font-weight:bold;}"
            "QPushButton:hover{background:#2A2F50;}"
        )
        test_btn.clicked.connect(lambda: webbrowser.open(f"{self._proto}://localhost:{SERVER_PORT}"))
        self._status_bar.addPermanentWidget(test_btn)

    def _connect_signals(self) -> None:
        self._connection_tab.start_requested.connect(self._start_stream)
        self._live_tab.stop_requested.connect(self._stop_stream)
        self._live_tab.vcam_toggled.connect(self._on_vcam_toggled)

    def _on_vcam_toggled(self, enabled: bool) -> None:
        if self._worker:
            device_name = self._live_tab.get_vcam_name()
            self._worker.set_vcam_enabled(enabled, device_name=device_name)
            logging.getLogger(__name__).info(f"Virtual Camera toggled: {enabled} ({device_name})")

    # ── Stream lifecycle ───────────────────────────────────────────────────

    @pyqtSlot()
    def _start_stream(self) -> None:
        """Start (or restart) the VideoWorker."""
        self._stop_stream()
        self._set_status("Waiting for phone camera…", "#F39C12")

        # Drain any stale frames from a previous session
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except Exception:
                break

        self._worker = VideoWorker(
            self._frame_queue, 
            virtual_camera_enabled=self._live_tab.is_vcam_enabled(),
            device_name=self._live_tab.get_vcam_name()
        )
        self._worker.frame_ready.connect(self._on_frame_ready)
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.start()

        self._tabs.setCurrentWidget(self._live_tab)

    @pyqtSlot()
    def _stop_stream(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self._worker = None
        self._live_tab.show_placeholder("Stream stopped.")
        self._set_status("● Disconnected", "#E74C3C")

    # ── Worker signals ─────────────────────────────────────────────────────

    def _on_frame_ready(self, image) -> None:
        self._live_tab.update_frame(image)

    def _on_connected(self) -> None:
        self._set_status("● Connected  –  Streaming", "#27AE60")
        self._live_tab.set_controls_enabled(True)

    def _on_disconnected(self, reason: str) -> None:
        self._live_tab.show_placeholder(f"Disconnected: {reason}")
        self._set_status("● Disconnected", "#E74C3C")
        self._worker = None

    # ── Server callbacks (called from asyncio thread → use Qt-safe update) ─

    def _on_phone_connected(self) -> None:
        # Update UI text
        self._phone_label.setText("  📱 Phone connected")
        # Trigger stream start safely
        QTimer.singleShot(0, self._start_stream)

    def _on_phone_disconnected(self) -> None:
        self._phone_label.setText("")
        # Trigger stream stop safely
        QTimer.singleShot(0, self._stop_stream)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str) -> None:
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color:{color};font-weight:600;font-size:12px;"
        )

    # ── Close ──────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self._stop_stream()
        self._server.stop()
        event.accept()
