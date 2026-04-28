"""
adb_screen_worker.py
--------------------
QThread that captures the Android phone screen continuously
using `adb exec-out screencap -p` and emits QImage signals.

No app or special permission required on the phone — only
USB Debugging must be enabled.
"""

import logging
import subprocess
import time
import platform

import cv2
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

log = logging.getLogger(__name__)


class AdbScreenWorker(QThread):
    """
    Background thread that captures phone screen frames via ADB.

    Signals
    -------
    frame_ready   : pyqtSignal(QImage)
    connected     : pyqtSignal()       – emitted on first successful frame
    disconnected  : pyqtSignal(str)    – emitted on stop or error
    fps_updated   : pyqtSignal(float)
    error         : pyqtSignal(str)
    """

    frame_ready:  pyqtSignal = pyqtSignal(QImage)
    connected:    pyqtSignal = pyqtSignal()
    disconnected: pyqtSignal = pyqtSignal(str)
    fps_updated:  pyqtSignal = pyqtSignal(float)
    error:        pyqtSignal = pyqtSignal(str)

    def __init__(self, serial: str | None = None, target_fps: int = 10, 
                 scale: float = 1.0,
                 virtual_camera_enabled: bool = False, device_name: str | None = None, parent=None):
        super().__init__(parent)
        self._serial     = serial
        self._target_fps = target_fps
        self._scale      = scale
        self._running    = False
        self._vcam_enabled = virtual_camera_enabled
        self._vcam_name = device_name

    # ── Public API ─────────────────────────────────────────────────────────

    def set_serial(self, serial: str | None) -> None:
        self._serial = serial

    def set_fps(self, fps: int) -> None:
        self._target_fps = max(1, min(fps, 60))

    def set_scale(self, scale: float) -> None:
        self._scale = max(0.1, min(scale, 1.0))

    def set_vcam_enabled(self, enabled: bool, device_name: str | None = None) -> None:
        """Dynamically enable/disable virtual camera output."""
        self._vcam_enabled = enabled
        if device_name:
            self._vcam_name = device_name

    def stop(self) -> None:
        self._running = False
        self.quit()
        self.wait(2000)

    # ── Thread ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        import pyvirtualcam
        self._running = True
        first_frame   = True
        frame_count   = 0
        fps_timer     = time.monotonic()
        interval      = 1.0 / self._target_fps
        vcam = None

        log.info("AdbScreenWorker started (serial=%s, target_fps=%d, scale=%.2f, vcam=%s)",
                 self._serial, self._target_fps, self._scale, self._vcam_enabled)

        while self._running:
            t0 = time.monotonic()

            png_bytes = self._capture_frame()

            if png_bytes is None:
                # ADB not ready or device disconnected – wait and retry
                time.sleep(0.2) 
                continue

            arr   = np.frombuffer(png_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                continue

            # ── Handle Scaling ──────────────────────────────────────────
            if self._scale < 1.0:
                h, w = frame.shape[:2]
                new_w, new_h = int(w * self._scale), int(h * self._scale)
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

            # Convert BGR to RGB for both Qt and VirtualCam
            rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # ── Handle Virtual Camera Preparation ──────────────────────────
            # We use a FIXED resolution for the virtual camera to avoid "Pixel buffer size mismatch" 
            # and expensive re-initializations when the phone rotates or resolution changes.
            vcam_w, vcam_h = 1920, 1080
            
            # Scale and letterbox the frame to fit the fixed VCam resolution
            h_orig, w_orig = rgb.shape[:2]
            scale = min(vcam_w / w_orig, vcam_h / h_orig)
            nw, nh = int(w_orig * scale), int(h_orig * scale)
            # Ensure even dimensions for the scaled part
            nw &= ~1
            nh &= ~1
            
            scaled = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
            
            # Create black canvas and center the frame
            vcam_frame = np.zeros((vcam_h, vcam_w, 3), dtype=np.uint8)
            y_off = (vcam_h - nh) // 2
            x_off = (vcam_w - nw) // 2
            vcam_frame[y_off:y_off+nh, x_off:x_off+nw] = scaled
            
            # Final buffer for VCam must be C-contiguous
            vcam_frame = np.ascontiguousarray(vcam_frame)
            
            # GUI image still uses the original or slightly normalized size
            h_gui, w_gui = rgb.shape[:2]
            if w_gui % 2 != 0 or h_gui % 2 != 0:
                rgb = cv2.resize(rgb, (w_gui & ~1, h_gui & ~1), interpolation=cv2.INTER_NEAREST)
                h_gui, w_gui = rgb.shape[:2]
            q_image_data = np.ascontiguousarray(rgb)

            # ── Handle Virtual Camera ───────────────────────────────────
            if self._vcam_enabled:
                if vcam is None or vcam.width != vcam_w or vcam.height != vcam_h:
                    # Cooldown to avoid spamming logs if initialization fails
                    now = time.monotonic()
                    if hasattr(self, '_last_vcam_init') and now - self._last_vcam_init < 2.0:
                        pass # Wait for cooldown
                    else:
                        self._last_vcam_init = now
                        if vcam: vcam.close()
                        try:
                            # On macOS, if a custom device is specified, try 'unitycamera' backend first
                            if platform.system() == "Darwin" and self._vcam_name and "OBS" not in self._vcam_name:
                                try:
                                    vcam = pyvirtualcam.Camera(width=vcam_w, height=vcam_h, fps=self._target_fps, device=self._vcam_name, backend='unitycamera')
                                    log.info("Screen VCam started (unitycamera): %s (%dx%d)", vcam.device, vcam_w, vcam_h)
                                except Exception:
                                    vcam = pyvirtualcam.Camera(width=vcam_w, height=vcam_h, fps=self._target_fps, device=self._vcam_name)
                                    log.info("Screen VCam started (custom): %s (%dx%d)", vcam.device, vcam_w, vcam_h)
                            else:
                                vcam = pyvirtualcam.Camera(width=vcam_w, height=vcam_h, fps=self._target_fps, device=self._vcam_name)
                                log.info("Screen VCam started: %s (%dx%d)", vcam.device, vcam_w, vcam_h)
                        except Exception as e:
                            log.warning("Screen VCam (%s) failed: %s. Trying fallback...", self._vcam_name, e)
                            try:
                                vcam = pyvirtualcam.Camera(width=vcam_w, height=vcam_h, fps=self._target_fps)
                                log.info("Screen VCam started (fallback): %s (%dx%d)", vcam.device, vcam_w, vcam_h)
                            except Exception as e2:
                                # Final attempt: try unitycamera or obs backends specifically if on Mac
                                if platform.system() == "Darwin":
                                    backends = ['obs', 'unitycamera']
                                    success = False
                                    for be in backends:
                                        try:
                                            vcam = pyvirtualcam.Camera(width=vcam_w, height=vcam_h, fps=self._target_fps, backend=be)
                                            log.info("Screen VCam started (%s): %s (%dx%d)", be, vcam.device, vcam_w, vcam_h)
                                            success = True
                                            break
                                        except Exception:
                                            continue
                                    if not success:
                                        log.error("Screen VCam Error: No compatible backends found on macOS.")
                                        self._vcam_enabled = False
                                else:
                                    log.error("Screen VCam Error: %s", e2)
                                    self._vcam_enabled = False
                
                if vcam:
                    try:
                        vcam.send(vcam_frame)
                    except Exception as e:
                        log.error("Screen VCam send error: %s", e)
                        vcam.close(); vcam = None
            elif vcam:
                vcam.close(); vcam = None
                log.info("Screen VCam stopped.")

            # ── Handle GUI ──────────────────────────────────────────────
            if first_frame:
                self.connected.emit()
                first_frame = False

            q_image = QImage(
                q_image_data.data, w_gui, h_gui, 3 * w_gui, QImage.Format.Format_RGB888
            ).copy()

            self.frame_ready.emit(q_image)

            # FPS counter
            frame_count += 1
            now = time.monotonic()
            elapsed = now - fps_timer
            if elapsed >= 1.0:
                self.fps_updated.emit(frame_count / elapsed)
                frame_count = 0
                fps_timer   = now

            # Throttle to target FPS
            spent = time.monotonic() - t0
            sleep_for = interval - spent
            if sleep_for > 0:
                time.sleep(sleep_for)

        if vcam: vcam.close()
        self.disconnected.emit("Stopped")
        log.info("AdbScreenWorker stopped")

    # ── Internals ──────────────────────────────────────────────────────────

    def _adb_cmd(self) -> list[str]:
        import shutil
        import os
        from pathlib import Path

        exe = shutil.which("adb")
        if not exe:
            candidates = [
                # Windows
                Path(os.path.expanduser("~")) / "platform-tools" / "adb.exe",
                Path("C:/platform-tools/adb.exe"),
                Path("C:/Android/platform-tools/adb.exe"),
                # Mac / Linux
                Path("/opt/homebrew/bin/adb"),
                Path("/usr/local/bin/adb"),
                Path(os.path.expanduser("~")) / "Library/Android/sdk/platform-tools/adb",
                Path("/usr/bin/adb"),
            ]
            for c in candidates:
                if c.exists():
                    exe = str(c)
                    break
            else:
                exe = "adb"

        cmd = [exe]
        if self._serial:
            cmd += ["-s", self._serial]
        return cmd

    def _capture_frame(self) -> bytes | None:
        """Run `adb exec-out screencap -p` and return raw PNG bytes, or None."""
        cmd = self._adb_cmd() + ["exec-out", "screencap", "-p"]
        try:
            # Increased timeout to 12s for slow ADB connections
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=12,
            )
            
            if result.returncode != 0:
                err = result.stderr.decode(errors="replace").strip()
                if "unauthorized" in err.lower() or "not found" in err.lower():
                    self.error.emit(f"Device error: {err}")
                    self._running = False
                return None

            if not result.stdout or len(result.stdout) < 1000:
                return None

            # Fix Windows line-ending corruption: \r\n → \n in PNG stream
            # On macOS/Linux, exec-out is already binary-safe.
            data = result.stdout
            if subprocess.os.name == 'nt':
                data = data.replace(b"\r\n", b"\n")
            return data

        except subprocess.TimeoutExpired:
            if not hasattr(self, '_last_timeout_log') or time.monotonic() - self._last_timeout_log > 15:
                log.warning("ADB screencap timed out (12s). Connection too slow?")
                self._last_timeout_log = time.monotonic()
            return None
        except Exception as e:
            log.error("ADB screencap exception: %s", e)
            return None
