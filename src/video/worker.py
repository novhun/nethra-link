"""
worker.py
---------
QThread-based video worker that reads JPEG frames from a thread-safe
queue.Queue (fed by WebSocketServer) and emits PyQt6 signals.

Keeps the GUI completely non-blocking – all decode work happens here.
"""

import queue
import logging
import time
import platform

log = logging.getLogger(__name__)

import cv2
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage


class VideoWorker(QThread):
    """
    Background thread that decodes JPEG frames from a queue.Queue.

    Signals
    -------
    frame_ready : pyqtSignal(QImage)
        Emitted every time a new frame is decoded.
    connected : pyqtSignal()
        Emitted once, when the first frame arrives successfully.
    disconnected : pyqtSignal(str)
        Emitted when stop() is called or the thread exits naturally.
    """

    frame_ready:  pyqtSignal = pyqtSignal(QImage)
    connected:    pyqtSignal = pyqtSignal()
    disconnected: pyqtSignal = pyqtSignal(str)
    error:        pyqtSignal = pyqtSignal(str)

    def __init__(self, frame_queue: queue.Queue, virtual_camera_enabled: bool = False, device_name: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._queue = frame_queue
        self._running = False
        self._vcam_enabled = virtual_camera_enabled
        self._vcam_name = device_name

    # ── Public API ─────────────────────────────────────────────────────────

    def set_vcam_enabled(self, enabled: bool, device_name: str | None = None) -> None:
        """Dynamically enable/disable virtual camera output."""
        self._vcam_enabled = enabled
        if device_name:
            self._vcam_name = device_name

    def stop(self) -> None:
        """Signal the run-loop to exit and return quickly."""
        self._running = False
        self.quit()
        self.wait(2000) # Give it 2 seconds to close vcam and exit

    # ── Thread entry point ─────────────────────────────────────────────────

    def run(self) -> None:
        """Decode JPEG bytes from the queue and emit QImage signals."""
        import pyvirtualcam
        self._running = True
        first_frame = True
        vcam = None

        while self._running:
            try:
                jpeg_bytes = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                log.warning("Failed to decode JPEG frame.")
                continue

            # Convert BGR to RGB for both Qt and VirtualCam
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
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

            # Handle Virtual Camera
            if self._vcam_enabled:
                # Re-initialize if vcam is missing, or resolution changed, or DEVICE NAME changed
                name_changed = vcam and hasattr(vcam, 'device') and self._vcam_name and self._vcam_name not in vcam.device
                
                if vcam is None or vcam.width != vcam_w or vcam.height != vcam_h or name_changed:
                    # Cooldown to avoid spamming logs if initialization fails
                    now = time.monotonic()
                    if hasattr(self, '_last_vcam_init') and now - self._last_vcam_init < 2.0:
                        pass # Wait for cooldown
                    else:
                        self._last_vcam_init = now
                        if vcam:
                            try: vcam.close()
                            except: pass
                        try:
                            # Use the FIXED resolution for initialization
                            if platform.system() == "Darwin" and self._vcam_name and "OBS" not in self._vcam_name:
                                try:
                                    vcam = pyvirtualcam.Camera(width=vcam_w, height=vcam_h, fps=20, device=self._vcam_name, backend='unitycamera')
                                    log.info("Virtual Camera started (unitycamera): %s (%dx%d)", vcam.device, vcam_w, vcam_h)
                                except Exception:
                                    vcam = pyvirtualcam.Camera(width=vcam_w, height=vcam_h, fps=20, device=self._vcam_name)
                                    log.info("Virtual Camera started (custom): %s (%dx%d)", vcam.device, vcam_w, vcam_h)
                            else:
                                vcam = pyvirtualcam.Camera(width=vcam_w, height=vcam_h, fps=20, device=self._vcam_name)
                                log.info("Virtual Camera started: %s (%dx%d)", vcam.device, vcam_w, vcam_h)
                        except Exception as e:
                            log.warning("Custom VCam (%s) failed: %s. Trying fallback...", self._vcam_name, e)
                            try:
                                vcam = pyvirtualcam.Camera(width=vcam_w, height=vcam_h, fps=20)
                                log.info("Virtual Camera started (fallback): %s (%dx%d)", vcam.device, vcam_w, vcam_h)
                            except Exception as e2:
                                if platform.system() == "Darwin":
                                    backends = ['obs', 'unitycamera']
                                    success = False
                                    for be in backends:
                                        try:
                                            vcam = pyvirtualcam.Camera(width=vcam_w, height=vcam_h, fps=20, backend=be)
                                            log.info("Virtual Camera started (%s): %s (%dx%d)", be, vcam.device, vcam_w, vcam_h)
                                            success = True
                                            break
                                        except Exception:
                                            continue
                                    if not success:
                                        msg = "No compatible Virtual Camera backends found on macOS."
                                        log.error(msg)
                                        self.error.emit(msg)
                                        self._vcam_enabled = False
                                else:
                                    msg = f"Virtual Camera Error: {e2}"
                                    log.error(msg)
                                    self.error.emit(msg)
                                    self._vcam_enabled = False
                
                if vcam:
                    try:
                        vcam.send(vcam_frame)
                        vcam.sleep_until_next_frame()
                    except ValueError as ve:
                        log.warning("VCam shape mismatch: %s. Re-initializing...", ve)
                        vcam.close()
                        vcam = None
                    except Exception as e:
                        log.error("VCam send error: %s", e)
                        try: vcam.close()
                        except: pass
                        vcam = None
            elif vcam:
                try: vcam.close()
                except: pass
                vcam = None
                log.info("Virtual Camera stopped.")

            if first_frame:
                self.connected.emit()
                first_frame = False

            q_image = QImage(
                q_image_data.data, w_gui, h_gui, 3 * w_gui, QImage.Format.Format_RGB888
            ).copy()

            self.frame_ready.emit(q_image)

        if vcam:
            try: vcam.close()
            except: pass

        if self._running:
            self.disconnected.emit("Stream ended.")
        self._running = False
