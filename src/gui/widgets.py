"""
widgets.py
----------
Custom PyQt6 widgets for NethraLink v2:

    ConnectionTab  – Wi-Fi (QR) / USB (ADB) mode toggle + Start button.
    LiveFeedTab    – Video canvas + Screenshot + Stop buttons.
    AdbWorker      – QThread for blocking ADB calls (detect / connect).
"""

import os
import logging
from datetime import datetime

log = logging.getLogger(__name__)

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QMessageBox, QComboBox, QTextEdit,
    QLineEdit
)

import adb.manager as adb_mgr


# ── Helper ─────────────────────────────────────────────────────────────────

def qimage_to_pixmap(image: QImage) -> QPixmap:
    return QPixmap.fromImage(image)


# ── ADB background worker ──────────────────────────────────────────────────

class AdbWorker(QThread):
    """Run a single ADB operation off the GUI thread."""
    result = pyqtSignal(bool, str)   # success, message

    DETECT  = "detect"
    CONNECT = "connect"
    ENABLE_TCPIP = "enable_tcpip"
    CONNECT_WIFI = "connect_wifi"

    def __init__(self, op: str, port: int = 9000, serial: str | None = None, ip: str | None = None):
        super().__init__()
        self._op     = op
        self._port   = port
        self._serial = serial
        self._ip     = ip

    def run(self):
        try:
            if self._op == self.DETECT:
                devices = adb_mgr.list_devices()
                online  = [d for d in devices if d.state == "device"]
                if not devices:
                    self.result.emit(False, "No devices found. Check USB cable & USB Debugging.")
                elif not online:
                    self.result.emit(False, f"{len(devices)} device(s) found but none are ready.\n"
                                            "Check USB Debugging is enabled.")
                else:
                    self.result.emit(True, "\n".join(
                        f"✔ {d.model or d.serial}  ({d.serial})" for d in online
                    ))
            elif self._op == self.CONNECT:
                is_wifi = self._serial and ":" in self._serial
                if not is_wifi:
                    # USB mode: use reverse proxy for localhost
                    ok = adb_mgr.setup_reverse(self._port, self._serial)
                    if not ok:
                        self.result.emit(False, "adb reverse failed. Check device connection.")
                        return
                    url = f"https://localhost:{self._port}"
                else:
                    # Wireless ADB mode: can't use reverse, must use PC IP
                    from networking.ip_discovery import get_local_ip
                    pc_ip = get_local_ip()
                    url = f"https://{pc_ip}:{self._port}"
                
                adb_mgr.open_browser(url, self._serial)
                self.result.emit(True, f"Link established. Browser launched → {url}")
            
            elif self._op == self.ENABLE_TCPIP:
                ok = adb_mgr.enable_tcpip(5555, self._serial)
                if ok:
                    self.result.emit(True, "Wireless mode enabled on device. You can now unplug USB.")
                else:
                    self.result.emit(False, "Failed to enable wireless mode.")

            elif self._op == self.CONNECT_WIFI:
                if not self._ip:
                    self.result.emit(False, "No IP provided for wireless connection.")
                    return
                ok, msg = adb_mgr.connect_wifi(self._ip)
                self.result.emit(ok, msg)
        except Exception as e:
            msg = str(e)
            if "not found" in msg.lower() or "device offline" in msg.lower():
                msg = "Device connection lost. Please reconnect USB or Wi-Fi and click 'Detect'."
            self.result.emit(False, f"ADB Error: {msg}")


# ── Styled button factory ──────────────────────────────────────────────────

def _btn(label: str, bg: str, hover: str, text: str = "white") -> QPushButton:
    b = QPushButton(label)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{bg};color:{text};font-size:13px;font-weight:600;"
        f"border-radius:10px;padding:11px 0;}}"
        f"QPushButton:hover{{background:{hover};}}"
        f"QPushButton:disabled{{background:#1E2236;color:#3A3F6A;}}"
    )
    return b


# ── Mode toggle button ─────────────────────────────────────────────────────

TOGGLE_ACTIVE = (
    "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4A6CF7,stop:1 #6A3DE8);"
    "color:#fff;font-weight:700;"
)
TOGGLE_IDLE = "background:#1A1D2E;color:#7080AA;font-weight:600;"
TOGGLE_BASE = "font-size:13px;border-radius:9px;padding:9px 0;border:1px solid #2A2F50;"


class ModeButton(QPushButton):
    def __init__(self, label: str):
        super().__init__(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self._refresh()

    def _refresh(self):
        style = (TOGGLE_ACTIVE if self.isChecked() else TOGGLE_IDLE) + TOGGLE_BASE
        self.setStyleSheet(style)

    def setChecked(self, v):
        super().setChecked(v)
        self._refresh()

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self._refresh()


# ══════════════════════════════════════════════════════════════════════════
#  ConnectionTab
# ══════════════════════════════════════════════════════════════════════════

class ConnectionTab(QWidget):
    """
    Connection tab with Wi-Fi (QR) and USB (ADB) modes.

    Signals
    -------
    start_requested : pyqtSignal()
        Emitted when the user clicks Start Stream in either mode.
    """

    start_requested: pyqtSignal = pyqtSignal()

    def __init__(self, pc_ip: str, qr_image_path: str, server_port: int, parent=None):
        super().__init__(parent)
        self._pc_ip      = pc_ip
        self._port       = server_port
        self._qr_path    = qr_image_path
        self._adb_worker = None
        self._devices    = []
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        root.setSpacing(0)

        # Header
        hdr = QLabel("📡  NethraLink – Wireless Camera Bridge")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.setStyleSheet("font-size:20px;font-weight:800;color:#E0E6FF;margin-bottom:18px;")
        root.addWidget(hdr)

        # Mode toggle row
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(8)
        self._wifi_btn = ModeButton("📶  Wi-Fi")
        self._usb_btn  = ModeButton("🔌  USB / ADB")
        self._wifi_btn.setChecked(True)
        self._wifi_btn.clicked.connect(lambda: self._set_mode("wifi"))
        self._usb_btn.clicked.connect(lambda: self._set_mode("usb"))
        toggle_row.addWidget(self._wifi_btn)
        toggle_row.addWidget(self._usb_btn)
        root.addLayout(toggle_row)

        root.addSpacing(18)

        # Stacked panels (use visibility trick)
        self._wifi_panel = self._build_wifi_panel()
        self._usb_panel  = self._build_usb_panel()
        root.addWidget(self._wifi_panel)
        root.addWidget(self._usb_panel)
        self._usb_panel.setVisible(False)

        root.addSpacing(16)

        # Start button (shared)
        self._start_btn = _btn(
            "▶  Start Stream",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4A6CF7,stop:1 #6A3DE8)",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5A7CFF,stop:1 #7A4DF8)",
        )
        self._start_btn.setStyleSheet(
            self._start_btn.styleSheet() + "QPushButton{font-size:15px;padding:14px 0;}"
        )
        self._start_btn.clicked.connect(self.start_requested.emit)
        root.addWidget(self._start_btn)
        root.addStretch()

    # ── Wi-Fi panel ────────────────────────────────────────────────────────

    def _build_wifi_panel(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#11142B;border:1px solid #2A2F50;border-radius:14px;padding:4px;}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        note = QLabel(
            "1. Connect phone to the <b>same Wi-Fi</b> as this PC.<br>"
            "2. Open <b>Chrome</b> and scan the QR code.<br>"
            "3. <b>SSL Warning:</b> Click 'Advanced' → 'Proceed' to bypass the security screen.<br>"
            "4. Allow camera access → press <b>Start Stream</b>.<br>"
            "<i style='color:#F39C12;font-size:11px;'>🔒 We use HTTPS so the camera works in Chrome!</i>"
        )
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet("font-size:12px;color:#A0AACC;line-height:1.6;")
        lay.addWidget(note)

        # QR image
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(220, 220)
        self._qr_label.setStyleSheet("background:#fff;border-radius:10px;")
        self._load_qr(self._qr_path)
        lay.addWidget(self._qr_label, alignment=Qt.AlignmentFlag.AlignCenter)

        url_lbl = QLabel(f"<b>http://{self._pc_ip}:{self._port}</b>")
        url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        url_lbl.setStyleSheet("font-size:13px;color:#7EB8F7;")
        lay.addWidget(url_lbl)

        return frame

    # ── USB panel ──────────────────────────────────────────────────────────

    def _build_usb_panel(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#11142B;border:1px solid #2A2F50;border-radius:14px;padding:4px;}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # Device selection section
        lay.addWidget(QLabel("<b>Device Selection</b>"))
        
        self._adb_status = QLabel()
        self._adb_status.setStyleSheet("font-size:11px; font-weight:600;")
        lay.addWidget(self._adb_status)
        self._refresh_adb_check()

        # Instructions for Wireless ADB
        instruct = QLabel(
            "<b>Wireless ADB:</b> 1. Connect USB. 2. Click 'Enable Wireless'. "
            "3. Unplug USB. 4. Enter Phone IP & click 'Connect IP'. "
            "5. Select the IP device and click 'ADB Link'."
        )
        instruct.setWordWrap(True)
        instruct.setStyleSheet("font-size:10px; color:#A0AACC; margin-bottom:5px;")
        lay.addWidget(instruct)

        self._device_combo = QComboBox()
        self._device_combo.setStyleSheet(
            "QComboBox{background:#1E2236;color:#E0E6FF;border:1px solid #3A3F6A;"
            "border-radius:8px;padding:6px 10px;font-size:13px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#1E2236;color:#E0E6FF;selection-background-color:#3A3F6A;}"
        )
        self._device_combo.addItem("— click Detect Devices —")
        lay.addWidget(self._device_combo)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._detect_btn = _btn("🔍  Detect", "#1E2744", "#2A3558")
        self._detect_btn.clicked.connect(self._on_detect)
        self._connect_usb_btn = _btn("🔗  ADB Link", "#1A4A2A", "#21613A")
        self._connect_usb_btn.clicked.connect(self._on_connect_usb)
        btn_row.addWidget(self._detect_btn)
        btn_row.addWidget(self._connect_usb_btn)
        lay.addLayout(btn_row)

        # Wireless ADB section
        lay.addSpacing(5)
        lay.addWidget(QLabel("<b>Wireless ADB Setup</b>"))
        
        wifi_setup_row = QHBoxLayout()
        self._enable_tcpip_btn = _btn("📶 Enable Wireless", "#3A3F6A", "#4A4F7A")
        self._enable_tcpip_btn.setToolTip("Enables wireless mode (requires USB first)")
        self._enable_tcpip_btn.clicked.connect(self._on_enable_tcpip)
        wifi_setup_row.addWidget(self._enable_tcpip_btn)
        lay.addLayout(wifi_setup_row)

        wifi_connect_row = QHBoxLayout()
        self._wifi_ip_input = QLineEdit()
        self._wifi_ip_input.setPlaceholderText("Phone IP (e.g. 192.168.1.5)")
        self._wifi_ip_input.setStyleSheet(
            "background:#0A0C18; color:#E0E6FF; border:1px solid #2A2F50; "
            "border-radius:8px; padding:6px; font-size:12px;"
        )
        self._connect_wifi_btn = _btn("🔗 Connect IP", "#4A6CF7", "#5A7CFF")
        self._connect_wifi_btn.setFixedWidth(100)
        self._connect_wifi_btn.clicked.connect(self._on_connect_wifi)
        wifi_connect_row.addWidget(self._wifi_ip_input)
        wifi_connect_row.addWidget(self._connect_wifi_btn)
        lay.addLayout(wifi_connect_row)

        # Log output
        self._adb_log = QTextEdit()
        self._adb_log.setReadOnly(True)
        self._adb_log.setFixedHeight(70)
        self._adb_log.setStyleSheet(
            "QTextEdit{background:#0A0C18;color:#7EB8F7;border:1px solid #2A2F50;"
            "border-radius:8px;font-family:'Consolas','Courier New',monospace;font-size:11px;padding:6px;}"
        )
        self._adb_log.setPlaceholderText("ADB log output…")
        lay.addWidget(self._adb_log)

        return frame

    # ── Mode switch ────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        wifi = (mode == "wifi")
        self._wifi_btn.setChecked(wifi)
        self._usb_btn.setChecked(not wifi)
        self._wifi_panel.setVisible(wifi)
        self._usb_panel.setVisible(not wifi)

    # ── ADB operations ─────────────────────────────────────────────────────

    def _refresh_adb_check(self):
        if adb_mgr.is_adb_available():
            self._adb_status.setText("✅  ADB found")
            self._adb_status.setStyleSheet("font-size:11px;font-weight:600;color:#27AE60;")
        else:
            self._adb_status.setText("❌  ADB not found")
            self._adb_status.setStyleSheet("font-size:11px;font-weight:600;color:#E74C3C;")

    def _on_detect(self):
        self._detect_btn.setEnabled(False)
        self._run_adb(AdbWorker.DETECT)

    def _on_connect_usb(self):
        serial = self._get_selected_serial()
        self._connect_usb_btn.setEnabled(False)
        self._log(f"Linking {serial or 'device'} via USB...")
        self._run_adb(AdbWorker.CONNECT, serial=serial)

    def _on_enable_tcpip(self):
        serial = self._get_selected_serial()
        self._enable_tcpip_btn.setEnabled(False)
        self._log(f"Enabling wireless mode on {serial or 'device'}...")
        self._run_adb(AdbWorker.ENABLE_TCPIP, serial=serial)

    def _on_connect_wifi(self):
        ip = self._wifi_ip_input.text().strip()
        if not ip:
            self._log("Error: Please enter the phone's IP address.")
            return
        self._connect_wifi_btn.setEnabled(False)
        self._log(f"Connecting to wireless device at {ip}...")
        self._run_adb(AdbWorker.CONNECT_WIFI, ip=ip)

    def _run_adb(self, op: str, serial: str | None = None, ip: str | None = None):
        self._adb_worker = AdbWorker(op, port=self._port, serial=serial, ip=ip)
        self._adb_worker.result.connect(self._on_adb_result)
        self._adb_worker.start()

    def _on_adb_result(self, ok: bool, msg: str):
        self._detect_btn.setEnabled(True)
        self._connect_usb_btn.setEnabled(True)
        self._enable_tcpip_btn.setEnabled(True)
        self._connect_wifi_btn.setEnabled(True)

        self._log(msg)

        # Populate combo when detect succeeds
        if ok and self._adb_worker and self._adb_worker._op == AdbWorker.DETECT:
            devices = adb_mgr.list_devices()
            self._devices = [d for d in devices if d.state == "device"]
            self._device_combo.clear()
            if self._devices:
                for d in self._devices:
                    label = f"{d.model or d.serial}  [{d.serial}]"
                    self._device_combo.addItem(label)
            else:
                self._device_combo.addItem("— no online devices —")

    def _get_selected_serial(self) -> str | None:
        idx = self._device_combo.currentIndex()
        if self._devices and 0 <= idx < len(self._devices):
            return self._devices[idx].serial
        return None

    def _log(self, text: str):
        self._adb_log.append(text)

    # ── QR helpers ─────────────────────────────────────────────────────────

    def _load_qr(self, path: str):
        if os.path.exists(path):
            px = QPixmap(path).scaled(
                200, 200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._qr_label.setPixmap(px)
        else:
            self._qr_label.setText("QR generation\nfailed")

    def refresh_qr(self, path: str):
        self._load_qr(path)


# ══════════════════════════════════════════════════════════════════════════
#  LiveFeedTab
# ══════════════════════════════════════════════════════════════════════════

class LiveFeedTab(QWidget):
    """Live video canvas + Screenshot / Stop controls."""

    stop_requested:       pyqtSignal = pyqtSignal()
    screenshot_requested: pyqtSignal = pyqtSignal()
    vcam_toggled:         pyqtSignal = pyqtSignal(bool)

    SCREENSHOT_DIR = "screenshots"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_frame: QImage | None = None
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        self._video_label = QLabel("Waiting for stream…")
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setMinimumSize(640, 400)
        self._video_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._video_label.setStyleSheet(
            "background:#0D0F1A;border:2px solid #2A2F50;"
            "border-radius:14px;color:#505878;font-size:15px;"
        )
        root.addWidget(self._video_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        # Virtual Camera toggle
        from PyQt6.QtWidgets import QCheckBox
        self._vcam_check = QCheckBox("Virtual Camera Output")
        self._vcam_check.setStyleSheet("color:#A0AACC; font-weight:600; font-size:12px; padding:0 10px;")
        self._vcam_check.toggled.connect(self.vcam_toggled.emit)
        btn_row.addWidget(self._vcam_check)

        self._vcam_name = QLineEdit("OBS Virtual Camera")
        self._vcam_name.setFixedWidth(140)
        self._vcam_name.setPlaceholderText("Device Name...")
        self._vcam_name.setStyleSheet(
            "background:#0A0C18; color:#7EB8F7; border:1px solid #2A2F50; "
            "border-radius:6px; padding:4px; font-size:11px;"
        )
        btn_row.addWidget(self._vcam_name)

        self._screenshot_btn = _btn("📷  Screenshot", "#27AE60", "#219A52")
        self._screenshot_btn.setEnabled(False)
        self._screenshot_btn.clicked.connect(self._on_screenshot)
        btn_row.addWidget(self._screenshot_btn)

        self._stop_btn = _btn("⏹  Stop Stream", "#E74C3C", "#C0392B")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        btn_row.addWidget(self._stop_btn)
        root.addLayout(btn_row)

    # ── Public API ─────────────────────────────────────────────────────────

    def update_frame(self, image: QImage):
        self._current_frame = image
        px = qimage_to_pixmap(image).scaled(
            self._video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._video_label.setPixmap(px)

    def set_controls_enabled(self, enabled: bool):
        self._screenshot_btn.setEnabled(enabled)
        self._stop_btn.setEnabled(enabled)

    def show_placeholder(self, message: str = "Waiting for stream…"):
        self._video_label.clear()
        self._video_label.setText(message)
        self._current_frame = None
        self.set_controls_enabled(False)

    def is_vcam_enabled(self) -> bool:
        """Returns True if the Virtual Camera checkbox is checked."""
        return self._vcam_check.isChecked()

    def get_vcam_name(self) -> str:
        """Returns the user-specified Virtual Camera device name."""
        return self._vcam_name.text().strip()

    # ── Screenshot ─────────────────────────────────────────────────────────

    def _on_screenshot(self):
        if self._current_frame is None:
            QMessageBox.information(self, "No Frame", "No video frame available yet.")
            return
        os.makedirs(self.SCREENSHOT_DIR, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.SCREENSHOT_DIR, f"screenshot_{ts}.png")
        if self._current_frame.save(path):
            QMessageBox.information(self, "Screenshot Saved",
                                    f"Saved to:\n{os.path.abspath(path)}")
            self.screenshot_requested.emit()
        else:
            QMessageBox.critical(self, "Error", f"Failed to save to:\n{path}")
