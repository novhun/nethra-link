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
    QLineEdit, QCheckBox, QGridLayout
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

    def __init__(self, op: str, port: int = 9000, serial: str | None = None, ip: str | None = None, proto: str = "https"):
        super().__init__()
        self._op     = op
        self._port   = port
        self._serial = serial
        self._ip     = ip
        self._proto  = proto

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
                    url = f"{self._proto}://localhost:{self._port}"
                else:
                    # Wireless ADB mode: can't use reverse, must use PC IP
                    from networking.ip_discovery import get_local_ip
                    pc_ip = get_local_ip()
                    url = f"{self._proto}://{pc_ip}:{self._port}"
                
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
        self._proto      = "https" # Default, will be updated
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
            f"<b>{t('connect_guide')}</b><br><br>"
            f"{t('go_to_connection')}<br>"
            f"{t('scan_qr')}<br>"
            "3. <b>SSL Warning:</b> Click 'Advanced' → 'Proceed' to bypass the security screen.<br>"
            f"{t('auto_appear')}<br>"
            "<i style='color:#F39C12;font-size:11px;'>🔒 Fully supports iOS (Safari) and Android (Chrome)!</i>"
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
        
        self._url_lbl = QLabel(f"<b>{self._proto}://{self._pc_ip}:{self._port}</b>")
        self._url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_lbl.setStyleSheet("font-size:13px;color:#7EB8F7;")
        lay.addWidget(self._url_lbl)

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
        self._adb_worker = AdbWorker(op, port=self._port, serial=serial, ip=ip, proto=self._proto)
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

    def update_connection_info(self, pc_ip: str, port: int, proto: str):
        """Update the connection details shown in the UI."""
        self._pc_ip = pc_ip
        self._port = port
        self._proto = proto
        self._url_lbl.setText(f"<b>{proto}://{pc_ip}:{port}</b>")
        # QR path is usually updated separately via refresh_qr


from utils.i18n import t

# ══════════════════════════════════════════════════════════════════════════
#  LiveFeedTab
# ══════════════════════════════════════════════════════════════════════════

class LiveFeedTab(QWidget):
    """
    Professional Live Viewer with Device Selector and Config.
    """
    start_requested:      pyqtSignal = pyqtSignal()
    stop_requested:       pyqtSignal = pyqtSignal()
    screenshot_requested: pyqtSignal = pyqtSignal()
    vcam_toggled:         pyqtSignal = pyqtSignal(bool)
    vcam_name_changed:    pyqtSignal = pyqtSignal(str)
    device_selected:      pyqtSignal = pyqtSignal(str) # device_id

    SCREENSHOT_DIR = "screenshots"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_frame: QImage | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # ── Header Control Row ──────────────────────────────────────────
        header = QHBoxLayout()
        
        self._device_selector = QComboBox()
        self._device_selector.addItem(t("no_devices"))
        self._device_selector.setMinimumWidth(200)
        self._device_selector.setStyleSheet("""
            QComboBox { background: #11142B; color: #7EB8F7; border: 1px solid #2A2F50; 
                        border-radius: 8px; padding: 8px 12px; font-weight: bold; }
            QComboBox::drop-down { border: none; }
        """)
        self._device_selector.currentTextChanged.connect(self._on_device_changed)
        header.addWidget(self._device_selector)
        
        header.addStretch()
        
        self._vcam_check = QCheckBox(t("vcam"))
        self._vcam_check.setStyleSheet("color:#A0AACC; font-weight:600; font-size:12px;")
        self._vcam_check.toggled.connect(self.vcam_toggled.emit)
        header.addWidget(self._vcam_check)

        self._vcam_name = QComboBox()
        self._vcam_name.addItems(["OBS Virtual Camera", "Unity Video Capture", "NDI Video"])
        self._vcam_name.setEditable(True)
        self._vcam_name.setFixedWidth(160)
        self._vcam_name.setStyleSheet("background:#0A0C18; color:#7EB8F7; border:1px solid #2A2F50; border-radius:6px; padding:4px; font-size:11px;")
        self._vcam_name.currentTextChanged.connect(self.vcam_name_changed.emit)
        header.addWidget(self._vcam_name)
        
        root.addLayout(header)

        # ── Video Label ──────────────────────────────────────────────────
        self._video_label = QLabel(t("status_waiting"))
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setMinimumSize(640, 360)
        self._video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._video_label.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #050505, stop:1 #0D0F1A);
            border: 2px solid #2A2F50; border-radius: 20px; color: #505878; font-size: 16px;
        """)
        root.addWidget(self._video_label)

        # ── Bottom Action Row ───────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._start_btn = _btn(f"▶  {t('start')}", "#2980B9", "#2471A3")
        self._start_btn.clicked.connect(self.start_requested.emit)
        btn_row.addWidget(self._start_btn)

        self._screenshot_btn = _btn(f"📷  {t('screenshot')}", "#27AE60", "#219A52")
        self._screenshot_btn.setEnabled(False)
        self._screenshot_btn.clicked.connect(self._on_screenshot)
        btn_row.addWidget(self._screenshot_btn)

        self._stop_btn = _btn(f"⏹  {t('stop')}", "#E74C3C", "#C0392B")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        btn_row.addWidget(self._stop_btn)
        
        root.addLayout(btn_row)
        
        self.retranslate_ui()

    def retranslate_ui(self):
        self._vcam_check.setText(t("vcam"))
        self._start_btn.setText(f"▶  {t('start')}")
        self._screenshot_btn.setText(f"📷  {t('screenshot')}")
        self._stop_btn.setText(f"⏹  {t('stop')}")
        if self._device_selector.count() > 0 and self._device_selector.itemData(0) is None:
             self._device_selector.setItemText(0, t("no_devices"))

    # ── Logic ─────────────────────────────────────────────────────────────

    def update_device_list(self, devices: list[tuple[str, str]]):
        """Update the device selector dropdown."""
        current_data = self._device_selector.currentData()
        
        self._device_selector.blockSignals(True)
        self._device_selector.clear()
        
        if not devices:
            self._device_selector.addItem(t("no_devices"))
        else:
            for did, name in devices:
                self._device_selector.addItem(f"📱 {name} ({did})", did)
        
        # Try to restore selection by DATA, not TEXT
        idx = self._device_selector.findData(current_data)
        if idx >= 0:
            self._device_selector.setCurrentIndex(idx)
        elif devices:
            self._device_selector.setCurrentIndex(0)
            
        self._device_selector.blockSignals(False)
        
        # Emit after unblocking if we fell back to index 0
        if idx < 0 and devices:
            self.device_selected.emit(devices[0][0])

    def _on_device_changed(self, text):
        did = self._device_selector.currentData()
        if did:
            self.device_selected.emit(did)

    def update_frame(self, image: QImage):
        if image.isNull(): return
        self._current_frame = image
        
        lbl_size = self._video_label.size()
        if lbl_size.width() < 10 or lbl_size.height() < 10:
            lbl_size = self._video_label.minimumSize()

        px = qimage_to_pixmap(image).scaled(
            lbl_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._video_label.setPixmap(px)

    def set_controls_enabled(self, enabled: bool):
        self._screenshot_btn.setEnabled(enabled)
        self._stop_btn.setEnabled(enabled)

    def show_placeholder(self, message: str = None):
        if not message: message = t("status_waiting")
        self._video_label.clear()
        self._video_label.setText(f"<h2>{message}</h2>")
        self._current_frame = None
        self.set_controls_enabled(False)

    def is_vcam_enabled(self) -> bool:
        return self._vcam_check.isChecked()

    def get_vcam_name(self) -> str:
        return self._vcam_name.currentText().strip()

    def set_vcam_state(self, enabled: bool, name: str):
        """Sync UI state from a worker/dashboard."""
        self._vcam_check.blockSignals(True)
        self._vcam_name.blockSignals(True)
        self._vcam_check.setChecked(enabled)
        self._vcam_name.setCurrentText(name)
        self._vcam_check.blockSignals(False)
        self._vcam_name.blockSignals(False)

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


# ══════════════════════════════════════════════════════════════════════════
#  ScreenShareTab  (ADB Screen Mirror)
# ══════════════════════════════════════════════════════════════════════════

class ScreenShareTab(QWidget):
    """
    Desktop tab that mirrors the Android phone screen in real-time via ADB.
    Uses `adb exec-out screencap -p` under the hood.

    Signals
    -------
    start_requested : pyqtSignal(str, int)   serial, fps
    stop_requested  : pyqtSignal()
    """

    start_requested: pyqtSignal = pyqtSignal(str, int, float)   # serial, fps, scale
    stop_requested:  pyqtSignal = pyqtSignal()
    vcam_toggled:    pyqtSignal = pyqtSignal(bool)

    SCREENSHOT_DIR = "screenshots"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_frame: QImage | None = None
        self._streaming = False
        self._vcam_enabled = False
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # ── Info banner ─────────────────────────────────────────────────
        info = QLabel(
            "🖥️  <b>ADB Screen Mirror</b> — Capture your phone screen directly via USB.<br>"
            "<span style='color:#A0AACC;font-size:11px;'>"
            "Requires USB Debugging enabled. Connect phone via USB first.</span>"
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet(
            "background:#11142B; border:1px solid #2A2F50; border-radius:10px;"
            "padding:12px 16px; font-size:13px; color:#B08CFF;"
        )
        root.addWidget(info)

        # ── Controls row ────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        # Device selector
        self._device_combo = QComboBox()
        self._device_combo.setToolTip("Select connected ADB device")
        self._device_combo.setStyleSheet(
            "QComboBox{background:#1E2236;color:#E0E6FF;border:1px solid #3A3F6A;"
            "border-radius:8px;padding:6px 10px;font-size:13px;min-width:180px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#1E2236;color:#E0E6FF;"
            "selection-background-color:#3A3F6A;}"
        )
        ctrl.addWidget(self._device_combo)

        self._refresh_btn = _btn("🔄 Refresh", "#1E2744", "#2A3558")
        self._refresh_btn.setFixedWidth(100)
        self._refresh_btn.clicked.connect(self._on_refresh_devices)
        ctrl.addWidget(self._refresh_btn)

        # FPS selector
        fps_lbl = QLabel("FPS:")
        fps_lbl.setStyleSheet("color:#A0AACC; font-size:12px; font-weight:600;")
        ctrl.addWidget(fps_lbl)

        self._fps_combo = QComboBox()
        self._fps_combo.addItems(["5", "10", "15", "20", "30", "60"])
        self._fps_combo.setCurrentText("15")
        self._fps_combo.setFixedWidth(60)
        self._fps_combo.setStyleSheet(
            "QComboBox{background:#1E2236;color:#E0E6FF;border:1px solid #3A3F6A;"
            "border-radius:8px;padding:6px 8px;font-size:13px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#1E2236;color:#E0E6FF;"
            "selection-background-color:#3A3F6A;}"
        )
        ctrl.addWidget(self._fps_combo)

        # Scale (Resolution) selector
        scale_lbl = QLabel("Scale:")
        scale_lbl.setStyleSheet("color:#A0AACC; font-size:12px; font-weight:600; margin-left:10px;")
        ctrl.addWidget(scale_lbl)

        self._scale_combo = QComboBox()
        self._scale_combo.addItems(["50%", "75%", "100%"])
        self._scale_combo.setCurrentText("75%")
        self._scale_combo.setFixedWidth(70)
        self._scale_combo.setStyleSheet(
            "QComboBox{background:#1E2236;color:#E0E6FF;border:1px solid #3A3F6A;"
            "border-radius:8px;padding:6px 8px;font-size:13px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#1E2236;color:#E0E6FF;"
            "selection-background-color:#3A3F6A;}"
        )
        ctrl.addWidget(self._scale_combo)

        root.addLayout(ctrl)

        # ── Video canvas ────────────────────────────────────────────────
        self._video_label = QLabel("Connect a phone via USB and press ▶ Start Mirror")
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setMinimumSize(640, 400)
        self._video_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._video_label.setStyleSheet(
            "background:#0D0F1A; border:2px solid #2A2F50;"
            "border-radius:14px; color:#505878; font-size:14px;"
        )
        root.addWidget(self._video_label)

        # ── Status / FPS bar ────────────────────────────────────────────
        status_row = QHBoxLayout()
        self._status_label = QLabel("Idle")
        self._status_label.setStyleSheet("color:#6070A0; font-size:11px; font-weight:600;")
        status_row.addWidget(self._status_label)

        # Virtual Cam Toggle
        self._vcam_btn = QPushButton("📹 Virtual Camera: OFF")
        self._vcam_btn.setCheckable(True)
        self._vcam_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vcam_btn.setStyleSheet(
            "QPushButton{background:#1A1D2E; color:#7080AA; border:1px solid #2A2F50; "
            "border-radius:6px; padding:4px 10px; font-size:10px; font-weight:bold;}"
            "QPushButton:checked{background:#27AE60; color:white; border:none;}"
        )
        self._vcam_btn.clicked.connect(self._on_vcam_toggled)

        self._vcam_name_input = QComboBox()
        self._vcam_name_input.addItems([
            "OBS Virtual Camera",
            "Unity Video Capture",
            "Unity Video Capture 2",
            "NDI Video"
        ])
        self._vcam_name_input.setEditable(True)
        self._vcam_name_input.setFixedWidth(160)
        self._vcam_name_input.setStyleSheet(
            "QComboBox { background: #0A0C18; color: #7EB8F7; border: 1px solid #2A2F50; "
            "border-radius: 6px; padding: 4px; font-size: 11px; }"
            "QComboBox::drop-down { border: none; }"
        )

        status_row.addStretch()
        status_row.addWidget(self._vcam_btn)
        status_row.addSpacing(10)
        status_row.addWidget(self._vcam_name_input)
        status_row.addSpacing(20)

        self._fps_label = QLabel("")
        self._fps_label.setStyleSheet("color:#6070A0; font-size:11px; font-weight:600;")
        status_row.addWidget(self._fps_label)
        root.addLayout(status_row)

        # ── Buttons row ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._start_btn = _btn(
            "▶  Start Mirror",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6A3DE8,stop:1 #4A6CF7)",
            "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7A4DF8,stop:1 #5A7CFF)",
        )
        self._start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self._start_btn)

        self._screenshot_btn = _btn("📷  Screenshot", "#27AE60", "#219A52")
        self._screenshot_btn.setEnabled(False)
        self._screenshot_btn.clicked.connect(self._on_screenshot)
        btn_row.addWidget(self._screenshot_btn)

        self._stop_btn = _btn("⏹  Stop", "#E74C3C", "#C0392B")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        btn_row.addWidget(self._stop_btn)

        root.addLayout(btn_row)
        
        self.retranslate_ui()

    def retranslate_ui(self):
        self._refresh_btn.setText(f"🔄 {t('refresh')}")
        self._start_btn.setText(f"▶  {t('start')}")
        self._screenshot_btn.setText(f"📷  {t('screenshot')}")
        self._stop_btn.setText(f"⏹  {t('stop')}")
        if not self._streaming:
            self.show_placeholder()

        # Populate devices on startup
        self._on_refresh_devices()

    # ── Device management ──────────────────────────────────────────────────

    def _on_refresh_devices(self):
        self._refresh_btn.setEnabled(False)
        self._device_combo.clear()
        try:
            import adb.manager as adb_mgr
            devices = adb_mgr.list_devices()
            online  = [d for d in devices if d.state == "device"]
            if online:
                for d in online:
                    label = f"{d.model or d.serial}  [{d.serial}]"
                    self._device_combo.addItem(label, userData=d.serial)
                self._set_status(f"✅  {len(online)} device(s) found", "#27AE60")
            else:
                self._device_combo.addItem("— No devices found —")
                self._set_status("❌  No ADB devices connected", "#E74C3C")
        except Exception as e:
            self._device_combo.addItem("— ADB error —")
            self._set_status(f"ADB error: {e}", "#E74C3C")
        self._refresh_btn.setEnabled(True)

    def get_selected_serial(self) -> str | None:
        return self._device_combo.currentData()

    def get_selected_fps(self) -> int:
        try:
            return int(self._fps_combo.currentText())
        except ValueError:
            return 10

    def get_selected_scale(self) -> float:
        try:
            val = self._scale_combo.currentText().replace("%", "")
            return int(val) / 100.0
        except ValueError:
            return 0.75

    # ── Start / Stop ───────────────────────────────────────────────────────

    def _on_start(self):
        serial = self.get_selected_serial()
        fps    = self.get_selected_fps()
        scale  = self.get_selected_scale()
        self.start_requested.emit(serial or "", fps, scale)

    def _on_stop(self):
        self.stop_requested.emit()

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
        self._streaming = enabled
        self._start_btn.setEnabled(not enabled)
        self._screenshot_btn.setEnabled(enabled)
        self._stop_btn.setEnabled(enabled)
        self._device_combo.setEnabled(not enabled)
        self._fps_combo.setEnabled(not enabled)

    def show_placeholder(self, message: str = None):
        if not message:
            message = "Connect a phone via USB and press ▶ Start Mirror" # This one is hardcoded in original, I'll leave it for now or use a generic key if I have one
        self._video_label.clear()
        self._video_label.setText(message)
        self._current_frame = None
        self.set_controls_enabled(False)
        self._fps_label.setText("")

    def update_fps(self, fps: float):
        self._fps_label.setText(f"{fps:.1f} FPS")

    def _set_status(self, text: str, color: str = "#6070A0"):
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color:{color}; font-size:11px; font-weight:600;"
        )

    def set_streaming_status(self, active: bool):
        if active:
            self._set_status("● Mirroring live", "#27AE60")
        else:
            self._set_status("Idle", "#6070A0")
            self._fps_label.setText("")

    def _on_vcam_toggled(self, checked):
        self._vcam_enabled = checked
        self._vcam_btn.setText(f"📹 Virtual Camera: {'ON' if checked else 'OFF'}")
        self.vcam_toggled.emit(checked)

    def is_vcam_enabled(self) -> bool:
        return self._vcam_btn.isChecked()

    def get_vcam_name(self) -> str:
        return self._vcam_name_input.currentText().strip()

    # ── Screenshot ─────────────────────────────────────────────────────────

    def _on_screenshot(self):
        if self._current_frame is None:
            QMessageBox.information(self, "No Frame", "No screen frame available yet.")
            return
        os.makedirs(self.SCREENSHOT_DIR, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.SCREENSHOT_DIR, f"screen_{ts}.png")
        if self._current_frame.save(path):
            QMessageBox.information(self, "Screenshot Saved",
                                    f"Saved to:\n{os.path.abspath(path)}")
        else:
            QMessageBox.critical(self, "Error", f"Failed to save to:\n{path}")

# ══════════════════════════════════════════════════════════════════════════
#  CameraCard (Individual Camera View)
# ══════════════════════════════════════════════════════════════════════════

class CameraCard(QFrame):
    """
    A premium card representing a single connected phone camera.
    """
    vcam_toggled = pyqtSignal(str, bool, str) # device_id, enabled, name
    disconnect_requested = pyqtSignal(str)

    def __init__(self, device_id: str, device_name: str, parent=None):
        super().__init__(parent)
        self._device_id = device_id
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            CameraCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1A1D2E, stop:1 #11142B);
                border: 1px solid #2A2F50;
                border-radius: 16px;
            }
            QLabel { color: #E0E6FF; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header
        head = QHBoxLayout()
        icon_lbl = QLabel("📱")
        icon_lbl.setStyleSheet("font-size: 16px;")
        head.addWidget(icon_lbl)

        name_stack = QVBoxLayout()
        name_lbl = QLabel(f"<b>{device_name}</b>")
        name_lbl.setStyleSheet("font-size: 13px; color: #7EB8F7;")
        name_stack.addWidget(name_lbl)
        id_lbl = QLabel(device_id)
        id_lbl.setStyleSheet("color: #506080; font-size: 10px;")
        name_stack.addWidget(id_lbl)
        head.addLayout(name_stack)
        
        head.addStretch()

        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet("""
            QPushButton {
                background: #2A2F50; color: #7080AA; border: none; border-radius: 12px; font-weight: bold;
            }
            QPushButton:hover { background: #E74C3C; color: white; }
        """)
        self._close_btn.clicked.connect(lambda: self.disconnect_requested.emit(self._device_id))
        head.addWidget(self._close_btn)
        layout.addLayout(head)

        # Video View
        self._view = QLabel("Connecting...")
        self._view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._view.setMinimumSize(320, 240)
        self._view.setStyleSheet("background: #000000; border-radius: 10px; border: 1px solid #1A1D2E;")
        layout.addWidget(self._view)

        # VCam Controls
        v_wrap = QFrame()
        v_wrap.setStyleSheet("background: #0D0F1A; border-radius: 10px; border: 1px solid #2A2F50;")
        v_lay = QHBoxLayout(v_wrap)
        v_lay.setContentsMargins(8, 4, 8, 4)

        self._vbtn = QPushButton("VCam")
        self._vbtn.setCheckable(True)
        self._vbtn.setFixedWidth(55)
        self._vbtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vbtn.setStyleSheet("""
            QPushButton { font-size: 10px; height: 22px; background: #2A2F50; border: none; border-radius: 6px; }
            QPushButton:checked { background: #27AE60; color: white; }
        """)
        self._vbtn.clicked.connect(self._on_vcam)
        self.retranslate_ui()
        v_lay.addWidget(self._vbtn)

        self._vname = QComboBox()
        self._vname.currentTextChanged.connect(lambda: self.vcam_toggled.emit(self._device_id, self._vbtn.isChecked(), self._vname.currentText()))
        self._vname.addItems([
            "OBS Virtual Camera",
            "Unity Video Capture",
            "Unity Video Capture 2",
            "Unity Video Capture 3",
            "Unity Video Capture 4",
            "NDI Video",
            "Nethra VCam 1"
        ])
        self._vname.setEditable(True)
        self._vname.setStyleSheet("""
            QComboBox { font-size: 10px; background: transparent; border: none; color: #B08CFF; min-width: 140px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #11142B; color: #B08CFF; selection-background-color: #2A2F50; }
        """)
        v_lay.addWidget(self._vname)
        layout.addWidget(v_wrap)

    def update_frame(self, img: QImage):
        px = qimage_to_pixmap(img).scaled(self._view.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._view.setPixmap(px)

    def _on_vcam(self, checked):
        self.vcam_toggled.emit(self._device_id, checked, self._vname.currentText().strip())

    def set_vcam_state(self, enabled: bool, name: str):
        self._vbtn.blockSignals(True)
        self._vname.blockSignals(True)
        self._vbtn.setChecked(enabled)
        self._vname.setCurrentText(name)
        self._vbtn.blockSignals(False)
        self._vname.blockSignals(False)

    def retranslate_ui(self):
        self._vbtn.setText(t("vcam").split(" ")[0]) # Use "VCam" or "បើក" for space
        self._vbtn.setToolTip(t("vcam"))

# ══════════════════════════════════════════════════════════════════════════
#  DashboardTab (Multi-Viewer)
# ══════════════════════════════════════════════════════════════════════════

class DashboardTab(QWidget):
    """
    Premium Multi-Viewer Dashboard with support for all streaming tasks.
    """
    vcam_requested = pyqtSignal(str, bool, str)
    scr_vcam_requested = pyqtSignal(bool, str)
    disconnect_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, CameraCard] = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)

        # Welcome / Header
        top = QHBoxLayout()
        self._header_label = QLabel(f"🚀  <b>{t('control_center')}</b>")
        self._header_label.setStyleSheet("font-size: 24px; color: #FFFFFF; font-weight: 800;")
        top.addWidget(self._header_label)
        top.addStretch()
        
        self._status_badge = QLabel(t("system_live"))
        self._status_badge.setStyleSheet("""
            background: #27AE60; color: white; padding: 4px 12px; 
            border-radius: 12px; font-size: 10px; font-weight: bold;
        """)
        top.addWidget(self._status_badge)
        root.addLayout(top)

        # Area 1: Phone Screen Mirror (ADB)
        self._scr_wrap = QFrame()
        self._scr_wrap.setStyleSheet("""
            QFrame { background: #11142B; border: 1px solid #2A2F50; border-radius: 16px; }
            QLabel { color: #E0E6FF; }
        """)
        scr_lay = QVBoxLayout(self._scr_wrap)
        scr_lay.setContentsMargins(15, 15, 15, 15)
        
        scr_head = QHBoxLayout()
        self._scr_title = QLabel(f"🖥️ <b>{t('mirror_title')}</b>")
        scr_head.addWidget(self._scr_title)
        scr_head.addStretch()
        
        self._scr_vbtn = QPushButton("VCam")
        self._scr_vbtn.setCheckable(True)
        self._scr_vbtn.setFixedWidth(60)
        self._scr_vbtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scr_vbtn.setStyleSheet("""
            QPushButton { font-size: 11px; height: 26px; background: #2A2F50; border-radius: 8px; }
            QPushButton:checked { background: #F39C12; color: white; }
        """)
        self._scr_vbtn.clicked.connect(self._on_scr_vcam)
        scr_head.addWidget(self._scr_vbtn)
        
        self._scr_vname = QComboBox()
        self._scr_vname.addItems([
            "OBS Virtual Camera",
            "Unity Video Capture",
            "Unity Video Capture 2",
            "NDI Video",
            "Nethra Screen VCam"
        ])
        self._scr_vname.setEditable(True)
        self._scr_vname.setFixedWidth(160)
        self._scr_vname.setStyleSheet("""
            QComboBox { background: #0D0F1A; border: 1px solid #2A2F50; border-radius: 6px; 
                        padding: 4px; font-size: 11px; color: #F39C12; }
            QComboBox::drop-down { border: none; }
        """)
        scr_head.addWidget(self._scr_vname)
        scr_lay.addLayout(scr_head)

        self._scr_view = QLabel("Screen Share Offline")
        self._scr_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scr_view.setMinimumSize(400, 200)
        self._scr_view.setStyleSheet("background: #000000; border-radius: 12px; border: 1px solid #1A1D2E;")
        scr_lay.addWidget(self._scr_view)
        
        root.addWidget(self._scr_wrap)

        # Area 2: Connected Cameras (Flow/Scroll)
        self._cam_title_label = QLabel(f"📷 <b>{t('camera_title')}</b>")
        self._cam_title_label.setStyleSheet("color: #7EB8F7; font-size: 15px; font-weight: 600;")
        root.addWidget(self._cam_title_label)

        from PyQt6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        self._cam_container = QWidget()
        self._cam_layout = QGridLayout(self._cam_container)
        self._cam_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._cam_layout.setSpacing(20)
        self._cam_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._cam_container)
        
        root.addWidget(scroll, 1)

        # Empty State Help
        self._empty_help = QLabel("")
        self._empty_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_help.setStyleSheet("color:#7080AA; font-size:13px; background:#0D0F18; border:1px dashed #2A2F50; border-radius:12px; padding:40px;")
        self._cam_layout.addWidget(self._empty_help)
        
        self.retranslate_ui()

    def retranslate_ui(self):
        self._header_label.setText(f"🚀  <b>{t('control_center')}</b>")
        self._scr_title.setText(f"🖥️ <b>{t('mirror_title')}</b>")
        self._cam_title_label.setText(f"📷 <b>{t('camera_title')}</b>")
        self._status_badge.setText(t("system_live").upper())
        
        self._empty_help.setText(
            f"{t('auto_appear')}<br><br>"
            "<span style='color:#506080; font-size:11px;'>Multiple devices are supported side-by-side.</span>"
        )
        for card in self._cards.values():
            card.retranslate_ui()

    def add_camera(self, device_id: str, name: str):
        if device_id in self._cards: return
        self._empty_help.hide()
        card = CameraCard(device_id, name)
        card.vcam_toggled.connect(self.vcam_requested.emit)
        card.disconnect_requested.connect(self.disconnect_requested.emit)
        self._cards[device_id] = card
        
        # Grid logic: 2 columns
        count = len(self._cards) - 1
        row = count // 2
        col = count % 2
        self._cam_layout.addWidget(card, row, col)

    def remove_camera(self, device_id: str):
        if device_id in self._cards:
            card = self._cards.pop(device_id)
            self._cam_layout.removeWidget(card)
            card.deleteLater()
            # Relayout remaining cards
            self._relayout_grid()
        if not self._cards:
            self._empty_help.show()

    def _relayout_grid(self):
        """Rearrange cards in the grid when one is removed."""
        # Clear layout (without deleting widgets)
        for i in reversed(range(self._cam_layout.count())):
            item = self._cam_layout.takeAt(i)
            if item.widget():
                self._cam_layout.removeWidget(item.widget())
        
        # Re-add all cards
        for i, card in enumerate(self._cards.values()):
            row = i // 2
            col = i % 2
            self._cam_layout.addWidget(card, row, col)

    def update_cam_frame(self, device_id: str, img: QImage):
        if device_id in self._cards:
            self._cards[device_id].update_frame(img)

    def update_scr_frame(self, img: QImage):
        px = qimage_to_pixmap(img).scaled(self._scr_view.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._scr_view.setPixmap(px)

    def _on_scr_vcam(self, checked):
        self.scr_vcam_requested.emit(checked, self._scr_vname.currentText().strip())

    def set_scr_offline(self):
        self._scr_view.setPixmap(QPixmap())
        self._scr_view.setText("Screen Share Offline")

    def sync_vcam_state(self, device_id: str, enabled: bool, name: str):
        if device_id in self._cards:
            self._cards[device_id].set_vcam_state(enabled, name)


# ══════════════════════════════════════════════════════════════════════════
#  SettingsTab
# ══════════════════════════════════════════════════════════════════════════

class SettingsTab(QWidget):
    """Global configuration for Language, Port, and drivers."""
    
    save_requested: pyqtSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(25)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── General Settings ──────────────────────────────────────────────
        self._gen_box = self._create_group(t("general_settings"))
        gen_lay = QVBoxLayout(self._gen_box)
        
        lang_row = QHBoxLayout()
        self._lang_label = QLabel(f"🌐 {t('language')}")
        lang_row.addWidget(self._lang_label)
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["English", "ភាសាខ្មែរ (Khmer)"])
        self._lang_combo.setFixedWidth(180)
        self._lang_combo.setStyleSheet("background:#1E2236; border:1px solid #2A2F50; padding:5px; border-radius:6px;")
        lang_row.addStretch()
        lang_row.addWidget(self._lang_combo)
        gen_lay.addLayout(lang_row)
        
        root.addWidget(self._gen_box)

        # ── Server Configuration ──────────────────────────────────────────
        self._srv_box = self._create_group(t("server_config"))
        srv_lay = QVBoxLayout(self._srv_box)
        
        port_row = QHBoxLayout()
        self._port_label = QLabel(f"🔌 {t('port')}")
        port_row.addWidget(self._port_label)
        self._port_input = QLineEdit("9000")
        self._port_input.setFixedWidth(100)
        self._port_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._port_input.setStyleSheet("background:#1E2236; border:1px solid #2A2F50; padding:5px; border-radius:6px; color:#7EB8F7; font-weight:bold;")
        port_row.addStretch()
        port_row.addWidget(self._port_input)
        srv_lay.addLayout(port_row)
        
        root.addWidget(self._srv_box)

        # ── Virtual Camera Drivers ─────────────────────────────────────────
        # ── Virtual Camera Drivers ─────────────────────────────────────────
        self._drv_box = self._create_group("Virtual Camera Drivers")
        drv_lay = QVBoxLayout(self._drv_box)
        
        backend_row = QHBoxLayout()
        self._vcam_backend_label = QLabel(f"📹 {t('vcam_backend')}")
        backend_row.addWidget(self._vcam_backend_label)
        self._backend_combo = QComboBox()
        self._backend_combo.addItems(["Unity Video Capture", "OBS Virtual Camera", "NDI Video"])
        self._backend_combo.setFixedWidth(180)
        self._backend_combo.setStyleSheet("background:#1E2236; border:1px solid #2A2F50; padding:5px; border-radius:6px;")
        backend_row.addStretch()
        backend_row.addWidget(self._backend_combo)
        drv_lay.addLayout(backend_row)
        
        root.addWidget(self._drv_box)
        
        # ── ADB Configuration ──────────────────────────────────────────────
        self._adb_box = self._create_group("ADB configuration")
        adb_lay = QVBoxLayout(self._adb_box)
        
        adb_row = QHBoxLayout()
        self._adb_label = QLabel("🛠️ ADB Executable Path")
        adb_row.addWidget(self._adb_label)
        self._adb_input = QLineEdit()
        self._adb_input.setPlaceholderText("e.g. C:/platform-tools/adb.exe")
        self._adb_input.setFixedWidth(250)
        self._adb_input.setStyleSheet("background:#1E2236; border:1px solid #2A2F50; padding:5px; border-radius:6px; color:#7EB8F7;")
        adb_row.addStretch()
        adb_row.addWidget(self._adb_input)
        adb_lay.addLayout(adb_row)
        
        adb_hint = QLabel("Optional. Leave empty to use system PATH or default locations.")
        adb_hint.setStyleSheet("color:#506080; font-size:10px; font-style:italic;")
        adb_lay.addWidget(adb_hint)
        
        root.addWidget(self._adb_box)

        root.addStretch()

        # ── Save Button ──────────────────────────────────────────────────
        self._save_btn = _btn(f"💾 {t('save_settings')}", "#27AE60", "#219A52")
        self._save_btn.setFixedWidth(200)
        self._save_btn.clicked.connect(self.save_requested.emit)
        root.addWidget(self._save_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.retranslate_ui()

    def retranslate_ui(self):
        # Update labels and buttons
        self._lang_label.setText(f"🌐 {t('language')}")
        self._port_label.setText(f"🔌 {t('port')}")
        self._vcam_backend_label.setText(f"📹 {t('vcam_backend')}")
        self._save_btn.setText(f"💾 {t('save_settings')}")
        self._vcam_backend_label.setText(f"📹 {t('vcam_backend')}")
        self._save_btn.setText(f"💾 {t('save_settings')}")

    def _create_group(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background: #11142B; border: 1px solid #2A2F50; border-radius: 12px; padding: 15px; }
            QLabel { color: #A0AACC; font-weight: bold; font-size: 13px; }
        """)
        return frame
