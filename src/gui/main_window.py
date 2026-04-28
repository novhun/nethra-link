"""
main_window.py
--------------
Top-level PyQt6 MainWindow for NethraLink v2.

Owns:
  - WebSocketServer  (aiohttp, runs in a daemon thread)
  - VideoWorker      (QThread – reads camera frames from the server's queue)
  - VideoWorker      (QThread – reads screen-share frames from the server's screen_queue)
  - ConnectionTab    (Wi-Fi QR + USB/ADB panel)
  - LiveFeedTab      (camera video canvas, screenshot, stop)
  - ScreenShareTab   (screen-share canvas, screenshot, stop)
  - Status bar       (connection state + PC IP + port)
"""

import os
import queue
import logging
from functools import partial

from PyQt6.QtCore import Qt, QSize, pyqtSlot, QTimer, QSettings
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel, QApplication, QPushButton, QFrame, QVBoxLayout, QHBoxLayout, QMessageBox
)

from networking.ip_discovery import get_local_ip
from qr.generator import generate_qr
from video.worker import VideoWorker
from video.adb_screen_worker import AdbScreenWorker
from utils.i18n import t, translator
from server.ws_server import WebSocketServer
from gui.widgets import ConnectionTab, LiveFeedTab, ScreenShareTab, DashboardTab


# ── Constants ───────────────────────────────────────────────────────────────

def get_resource_path(relative_path):
    import sys
    import os
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative_path)

APP_TITLE    = "NethraLink – Wireless Camera Bridge"
QR_OUT_PATH  = get_resource_path("assets/qr_code.png")

DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #0D0F1A;
    color: #E0E6FF;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
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
    Application shell that wires the WebSocket server, video workers,
    and UI tabs together.
    """

    def __init__(self) -> None:
        super().__init__()
        # Multi-device state
        self._camera_workers: dict[str, VideoWorker] = {}
        self._device_names: dict[str, str] = {}
        self._screen_worker: AdbScreenWorker | None = None
        self._selected_live_device: str | None = None  # Which device to show in LiveFeedTab


        # ── Shared frame queues ────────────────────────────────────────────
        self._screen_queue: queue.Queue = queue.Queue(maxsize=8)

        self._pc_ip = get_local_ip()
        self._proto = "https"
        self._server_port = 9000  # Default, will be loaded in _load_settings
        
        # ── Window ────────────────────────────────────────────────────────
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(get_resource_path("assets/icon.png")))
        self.setMinimumSize(QSize(860, 660))
        self.setStyleSheet(DARK_STYLE)

        self._load_language()  # Load language BEFORE building tabs
        self._load_settings()  # Load core settings (port) BEFORE building server or tabs
        
        # Initial QR path (placeholder, will be regenerated after server starts)
        self._qr_path = QR_OUT_PATH 

        self._build_tabs()
        self._apply_ui_settings() # Apply UI settings AFTER building tabs
        self._build_status_bar()
        self._connect_signals()

        # ── Start the WebSocket / HTTP server ──────────────────────────────
        self._server = WebSocketServer(port=self._server_port)
        self._server.set_callbacks(
            on_connect=self._on_phone_connected,
            on_disconnect=self._on_phone_disconnected,
        )
        self._server.start()
        
        # Update protocol based on actual server state
        self._proto = "https" if self._server.using_ssl else "http"
        
        # Regenerate QR code with CORRECT protocol and port
        self._qr_path = generate_qr(
            f"{self._proto}://{self._pc_ip}:{self._server_port}",
            QR_OUT_PATH,
        )
        
        self._connection_tab.refresh_qr(self._qr_path)
        self._connection_tab.update_connection_info(self._pc_ip, self._server_port, self._proto)

        # Sync the server's screen queue with our reference
        self._screen_queue = self._server.screen_queue

    # ── UI construction ────────────────────────────────────────────────────

    def _build_tabs(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        # Tab 0: Dashboard (Multi-Viewer)
        self._dashboard_tab = DashboardTab()
        self._tabs.addTab(self._dashboard_tab, t('dashboard'))

        # Tab 1: Connection
        self._connection_tab = ConnectionTab(
            pc_ip=self._pc_ip,
            qr_image_path=self._qr_path,
            server_port=self._server_port,
        )
        self._tabs.addTab(self._connection_tab, t('connection'))

        # Tab 2: Live Camera Feed
        self._live_tab = LiveFeedTab()
        self._tabs.addTab(self._live_tab, t('live_feed'))

        # Tab 3: Screen Share (ADB Mirror)
        self._screen_tab = ScreenShareTab()
        self._tabs.addTab(self._screen_tab, t('screen_share'))

        # Tab 4: Settings
        from gui.widgets import SettingsTab
        self._settings_tab = SettingsTab()
        self._tabs.addTab(self._settings_tab, t("settings"))

        self.setCentralWidget(self._tabs)

    def _build_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._status_label = QLabel(f"● {t('status_disconnected')}")
        self._status_label.setContentsMargins(10, 0, 10, 0)
        self._status_bar.addWidget(self._status_label)

        # Language Switcher
        self._lang_btn = QPushButton(f"🌐 {t('language')}: {translator.get_lang().upper()}")
        self._lang_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_btn.setStyleSheet("QPushButton{background:#1E2236; color:#7EB8F7; border-radius:6px; padding:2px 10px; font-size:11px;}")
        self._lang_btn.clicked.connect(self._toggle_language)
        self._status_bar.addPermanentWidget(self._lang_btn)

        import webbrowser
        self._test_btn = QPushButton(f"🌐 {t('test_server')}")
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.setStyleSheet(
            "QPushButton{background:#1E2236; color:#7EB8F7; border:1px solid #2A2F50; "
            "border-radius:6px; padding:2px 8px; font-size:10px; font-weight:bold;}"
            "QPushButton:hover{background:#2A2F50;}"
        )
        self._test_btn.clicked.connect(lambda: webbrowser.open(f"{self._proto}://localhost:{self._server_port}"))
        self._status_bar.addPermanentWidget(self._test_btn)

        # Screen share quick-launch button
        self._screen_btn = QPushButton(f"🖥️ {t('screen_page')}")
        self._screen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._screen_btn.setStyleSheet(
            "QPushButton{background:#1E2236; color:#B08CFF; border:1px solid #2A2F50; "
            "border-radius:6px; padding:2px 8px; font-size:10px; font-weight:bold;}"
            "QPushButton:hover{background:#2A2F50;}"
        )
        self._screen_btn.clicked.connect(lambda: webbrowser.open(f"{self._proto}://localhost:{self._server_port}/screen"))
        self._status_bar.addPermanentWidget(self._screen_btn)

    def _connect_signals(self) -> None:
        # Tab signals
        self._connection_tab.start_requested.connect(self._start_stream)
        self._live_tab.start_requested.connect(self._start_stream)
        self._live_tab.stop_requested.connect(self._stop_stream)
        self._live_tab.device_selected.connect(self._on_live_device_selected)
        self._screen_tab.start_requested.connect(self._start_screen_stream)
        self._screen_tab.stop_requested.connect(self._stop_screen_stream)
        self._settings_tab.save_requested.connect(self._save_settings)
        
        # Live Feed VCam signals
        self._live_tab.vcam_toggled.connect(self._on_live_vcam_toggled)
        self._live_tab.vcam_name_changed.connect(self._on_live_vcam_name_changed)
        
        # Dashboard signals
        self._dashboard_tab.vcam_requested.connect(self._on_device_vcam_requested)
        self._dashboard_tab.scr_vcam_requested.connect(self._on_screen_vcam_toggled)
        self._dashboard_tab.disconnect_requested.connect(self._on_phone_disconnected)

    def _on_device_vcam_requested(self, device_id: str, enabled: bool, name: str) -> None:
        if device_id in self._camera_workers:
            self._camera_workers[device_id].set_vcam_enabled(enabled, device_name=name)
            logging.getLogger(__name__).info(f"VCam for {device_id} -> {enabled} ({name})")
        # Also sync LiveFeedTab if this is the selected device
        if device_id == self._selected_live_device:
            self._live_tab.set_vcam_state(enabled, name)

    def _on_live_vcam_toggled(self, enabled: bool):
        if self._selected_live_device and self._selected_live_device in self._camera_workers:
            name = self._live_tab.get_vcam_name()
            self._camera_workers[self._selected_live_device].set_vcam_enabled(enabled, device_name=name)
            # Sync back to Dashboard
            self._dashboard_tab.sync_vcam_state(self._selected_live_device, enabled, name)

    def _on_live_vcam_name_changed(self, name: str):
        if self._selected_live_device and self._selected_live_device in self._camera_workers:
            enabled = self._live_tab.is_vcam_enabled()
            self._camera_workers[self._selected_live_device].set_vcam_enabled(enabled, device_name=name)
            # Sync back to Dashboard
            self._dashboard_tab.sync_vcam_state(self._selected_live_device, enabled, name)

    def _toggle_language(self):
        new_lang = "km" if translator.get_lang() == "en" else "en"
        translator.set_lang(new_lang)
        
        # Persist immediately
        settings = QSettings("NethraLink", "Config")
        settings.setValue("language", new_lang)
        
        self._retranslate_ui()
        logging.getLogger(__name__).info(f"Language toggled to {new_lang}")

    def _retranslate_ui(self):
        """Dynamically updates all UI strings across the application."""
        # Update Main Window tabs
        self._tabs.setTabText(0, t('dashboard'))
        self._tabs.setTabText(1, t('connection'))
        self._tabs.setTabText(2, t('live_feed'))
        self._tabs.setTabText(3, t('screen_share'))
        self._tabs.setTabText(4, t('settings'))
        
        # Update Status Bar
        self._lang_btn.setText(f"🌐 {t('language')}: {translator.get_lang().upper()}")
        self._test_btn.setText(f"🌐 {t('test_server')}")
        self._screen_btn.setText(f"🖥️ {t('screen_page')}")
        
        # Trigger retranslation in tabs
        if hasattr(self._dashboard_tab, 'retranslate_ui'):
            self._dashboard_tab.retranslate_ui()
        if hasattr(self._live_tab, 'retranslate_ui'):
            self._live_tab.retranslate_ui()
        if hasattr(self._screen_tab, 'retranslate_ui'):
            self._screen_tab.retranslate_ui()
        if hasattr(self._settings_tab, 'retranslate_ui'):
            self._settings_tab.retranslate_ui()
        
        # Refresh current status text
        self._set_status(self._status_label.text(), "#6070A0") # Color will be overridden by _set_status logic if needed

    def _on_live_device_selected(self, device_id: str):
        self._selected_live_device = device_id
        logging.getLogger(__name__).info(f"Live View Target -> {device_id}")

    def _on_screen_vcam_toggled(self, enabled: bool, name: str = "OBS Virtual Camera") -> None:
        if self._screen_worker:
            self._screen_worker.set_vcam_enabled(enabled, device_name=name)
            logging.getLogger(__name__).info(f"Screen VCam -> {enabled} ({name})")

    # ── Camera stream lifecycle ────────────────────────────────────────────

    def _on_phone_connected(self, device_id: str, name: str, q: queue.Queue) -> None:
        """Called when a new phone camera connects via WebSocket."""
        # STOP existing worker if same ID reconnects (prevents thread/vcam leak)
        if device_id in self._camera_workers:
            log = logging.getLogger(__name__)
            log.info(f"Device {device_id} reconnected. Stopping old worker.")
            old_worker = self._camera_workers.pop(device_id)
            old_worker.stop()

        # Initialize worker with current UI settings for VCam
        vcam_enabled = self._live_tab.is_vcam_enabled()
        vcam_name = self._live_tab.get_vcam_name()
        
        worker = VideoWorker(q, virtual_camera_enabled=vcam_enabled, device_name=vcam_name)
        worker.frame_ready.connect(partial(self._on_device_frame, device_id))
        worker.error.connect(self._on_worker_error)
        worker.start()
        
        self._camera_workers[device_id] = worker
        self._device_names[device_id] = name
        self._dashboard_tab.add_camera(device_id, name)
        
        # Update Live Feed dropdown
        self._live_tab.update_device_list([(did, self._device_names[did]) for did in self._camera_workers])
        
        if not self._selected_live_device:
            self._selected_live_device = device_id
            
        self._set_status(f"● {len(self._camera_workers)} {t('live_feed')}", "#27AE60")

    def _on_phone_disconnected(self, device_id: str) -> None:
        """Called when a phone camera disconnects."""
        if device_id in self._camera_workers:
            worker = self._camera_workers.pop(device_id)
            worker.stop()
            # Explicitly delete later to be safe, though wait() should have finished
            worker.deleteLater()
            self._device_names.pop(device_id, None)
            
        self._dashboard_tab.remove_camera(device_id)
        
        # Update Live Feed dropdown
        self._live_tab.update_device_list([(did, self._device_names.get(did, "Device")) for did in self._camera_workers])
        
        # If the currently selected live device disconnected, clear it
        if self._selected_live_device == device_id:
            self._selected_live_device = None
            if self._camera_workers:
                # Pick the first available device
                self._selected_live_device = next(iter(self._camera_workers))
            else:
                self._live_tab.show_placeholder(t("status_waiting"))

        if not self._camera_workers:
            self._set_status(f"● {t('no_devices')}", "#E74C3C")
        else:
            self._set_status(f"● {len(self._camera_workers)} {t('live_feed')}", "#27AE60")

    @pyqtSlot()
    def _start_stream(self):
        # Open the default web browser to the local connection page
        import webbrowser
        webbrowser.open(f"{self._proto}://localhost:{self._server_port}")
        self._set_status(t("status_waiting"), "#F39C12")

    @pyqtSlot()
    def _stop_stream(self) -> None:
        # Stop ALL cameras
        for device_id in list(self._camera_workers.keys()):
            self._on_phone_disconnected(device_id)

    def _on_worker_error(self, msg: str):
        QMessageBox.warning(self, "Virtual Camera Error", msg)

    # ── Screen share lifecycle ─────────────────────────────────────────────

    def _start_screen_stream(self, serial: str, fps: int, scale: float) -> None:
        """Start the AdbScreenWorker for screen mirror."""
        self._stop_screen_stream()
        self._set_status("Starting ADB screen mirror…", "#9B59B6")

        self._screen_worker = AdbScreenWorker(
            serial=serial, 
            target_fps=fps,
            scale=scale,
            virtual_camera_enabled=self._screen_tab.is_vcam_enabled(),
            device_name=self._screen_tab.get_vcam_name()
        )
        self._screen_worker.frame_ready.connect(self._on_screen_frame_ready)
        self._screen_worker.connected.connect(self._on_screen_stream_connected)
        self._screen_worker.disconnected.connect(self._on_screen_stream_disconnected)
        self._screen_worker.fps_updated.connect(self._screen_tab.update_fps)
        self._screen_worker.error.connect(lambda msg: self._screen_tab.show_placeholder(f"ADB Error: {msg}"))
        self._screen_worker.start()

        self._tabs.setCurrentWidget(self._screen_tab)

    @pyqtSlot()
    def _stop_screen_stream(self) -> None:
        if self._screen_worker:
            worker = self._screen_worker
            self._screen_worker = None
            if worker.isRunning():
                worker.stop()
            worker.deleteLater()
            
        self._screen_tab.show_placeholder("Screen mirror stopped.")
        self._screen_tab.set_streaming_status(False)
        self._set_status("● Disconnected", "#E74C3C")

    # ── Camera worker signals ──────────────────────────────────────────────

    def _on_device_frame(self, device_id: str, image) -> None:
        # logging.getLogger(__name__).debug(f"Frame received from {device_id}")
        self._dashboard_tab.update_cam_frame(device_id, image)
        
        if not self._selected_live_device:
            self._selected_live_device = device_id

        # ONLY update LiveFeedTab if this is the SELECTED device
        if device_id == self._selected_live_device:
            self._live_tab.update_frame(image)

    def _on_connected(self) -> None:
        self._set_status("● Connected  –  Camera Streaming", "#27AE60")
        self._live_tab.set_controls_enabled(True)

    def _on_disconnected(self, reason: str) -> None:
        self._live_tab.show_placeholder(f"Disconnected: {reason}")
        self._set_status("● Disconnected", "#E74C3C")
        self._worker = None

    # ── Screen share worker signals ────────────────────────────────────────

    def _on_screen_frame_ready(self, image) -> None:
        self._screen_tab.update_frame(image)
        self._dashboard_tab.update_scr_frame(image)

    def _on_screen_stream_connected(self) -> None:
        self._set_status("● Connected  –  ADB Screen Mirroring", "#9B59B6")
        self._screen_tab.set_controls_enabled(True)
        self._screen_tab.set_streaming_status(True)

    def _on_screen_stream_disconnected(self, reason: str) -> None:
        self._screen_tab.show_placeholder(f"Screen share ended: {reason}")
        self._screen_worker = None

    # ── Server callbacks ────────────────────────────────────────────────
    # Handled by _on_phone_connected(device_id, name, q) and _on_phone_disconnected(device_id) above.

    # ── Settings ───────────────────────────────────────────────────────────

    def _load_language(self):
        """Loads language preference before UI construction."""
        settings = QSettings("NethraLink", "Config")
        lang = settings.value("language", "en")
        translator.set_lang(lang)

    def _load_settings(self):
        """Loads core configuration needed before UI setup."""
        settings = QSettings("NethraLink", "Config")
        
        # Load Port
        port = int(settings.value("server_port", 9000))
        self._server_port = port

    def _apply_ui_settings(self):
        """Applies UI-specific settings to widgets after they are built."""
        settings = QSettings("NethraLink", "Config")
        
        self._screen_tab._vcam_name_input.setCurrentText(settings.value("scr_vcam_name", "Nethra Screen VCam"))
        self._screen_tab._fps_combo.setCurrentText(settings.value("scr_fps", "15"))
        self._screen_tab._scale_combo.setCurrentText(settings.value("scr_scale", "75%"))
        self._dashboard_tab._scr_vname.setCurrentText(settings.value("scr_vcam_name", "Nethra Screen VCam"))
        self._settings_tab._port_input.setText(str(self._server_port))
        self._settings_tab._adb_input.setText(settings.value("adb_path", ""))
        
        # Apply adb path to manager immediately
        import adb.manager as adb_mgr
        adb_mgr.set_custom_adb_path(settings.value("adb_path", ""))

    def _save_settings(self):
        settings = QSettings("NethraLink", "Config")
        settings.setValue("scr_vcam_name", self._screen_tab._vcam_name_input.currentText())
        settings.setValue("scr_fps", self._screen_tab._fps_combo.currentText())
        settings.setValue("scr_scale", self._screen_tab._scale_combo.currentText())
        settings.setValue("cam_vcam_name", self._live_tab._vcam_name.currentText())
        
        # Save Port and check for changes
        old_port = self._server_port
        try:
            new_port = int(self._settings_tab._port_input.text())
        except ValueError:
            new_port = 9000
            
        settings.setValue("server_port", new_port)
        self._server_port = new_port

        # Save ADB path
        adb_path = self._settings_tab._adb_input.text().strip()
        settings.setValue("adb_path", adb_path)
        import adb.manager as adb_mgr
        adb_mgr.set_custom_adb_path(adb_path)

        # If language changed via settings tab, also update translator for current session
        translator.set_lang(new_lang)
        self._retranslate_ui()

        # If port changed, restart server
        if old_port != new_port:
            logging.getLogger(__name__).info(f"Port changed from {old_port} to {new_port}. Restarting server...")
            self._server.stop()
            self._server = WebSocketServer(port=self._server_port)
            self._server.set_callbacks(
                on_connect=self._on_phone_connected,
                on_disconnect=self._on_phone_disconnected,
            )
            self._server.start()
            
            # Update protocol and UI
            self._proto = "https" if self._server.using_ssl else "http"
            self._qr_path = generate_qr(
                f"{self._proto}://{self._pc_ip}:{self._server_port}",
                QR_OUT_PATH,
            )
            self._connection_tab.refresh_qr(self._qr_path)
            self._connection_tab.update_connection_info(self._pc_ip, self._server_port, self._proto)
            
            QMessageBox.information(self, "Server Restarted", f"Server restarted on port {new_port}.\nPlease reconnect your devices.")

    # ── Helpers ────────────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str) -> None:
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color:{color};font-weight:600;font-size:12px;"
        )
        # Also update dashboard badge
        if hasattr(self, '_dashboard_tab'):
            self._dashboard_tab._status_badge.setText(text.replace("● ", "").upper())
            self._dashboard_tab._status_badge.setStyleSheet(f"background:{color}; color:white; padding:4px 12px; border-radius:12px; font-size:10px; font-weight:bold;")

    # ── Close ──────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self._save_settings()
        
        # Stop workers carefully to avoid QBasicTimer errors
        self._stop_stream()
        self._stop_screen_stream()
        
        # Give a small moment for threads to clean up their internal resources
        QApplication.processEvents()
        
        self._server.stop()
        event.accept()

