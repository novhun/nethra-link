"""
worker.py
---------
QThread-based video worker that reads JPEG frames from a thread-safe
queue.Queue (fed by WebSocketServer) and emits PyQt6 signals.

Keeps the GUI completely non-blocking – all decode work happens here.
"""

import queue
import logging

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
        """Signal the run-loop to exit, then block until it does."""
        self._running = False
        self.wait()

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
                continue

            # Convert BGR to RGB for both Qt and VirtualCam
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape

            # Handle Virtual Camera
            if self._vcam_enabled:
                if vcam is None or vcam.width != w or vcam.height != h:
                    if vcam: vcam.close()
                    try:
                        # Try to find a specific device, or let pyvirtualcam pick the best one
                        vcam = pyvirtualcam.Camera(width=w, height=h, fps=20, device=self._vcam_name)
                        log.info("Virtual Camera started: %s", vcam.device)
                    except Exception as e:
                        log.warning("Custom VCam (%s) failed: %s. Trying default...", self._vcam_name, e)
                        try:
                            vcam = pyvirtualcam.Camera(width=w, height=h, fps=20)
                            log.info("Virtual Camera started (default): %s", vcam.device)
                        except Exception as e2:
                            log.error("Virtual Camera Error: %s", e2)
                            self._vcam_enabled = False
                
                if vcam:
                    try:
                        vcam.send(rgb)
                        vcam.sleep_until_next_frame()
                    except ValueError as ve:
                        log.warning("VCam shape mismatch: %s. Re-initializing...", ve)
                        vcam.close()
                        vcam = None
                    except Exception as e:
                        log.error("VCam send error: %s", e)
                        vcam.close()
                        vcam = None
            elif vcam:
                vcam.close()
                vcam = None
                log.info("Virtual Camera stopped.")

            if first_frame:
                self.connected.emit()
                first_frame = False

            q_image = QImage(
                rgb.data, w, h, ch * w, QImage.Format.Format_RGB888
            ).copy()

            self.frame_ready.emit(q_image)

        if vcam:
            vcam.close()

        if self._running:
            self.disconnected.emit("Stream ended.")
        self._running = False
