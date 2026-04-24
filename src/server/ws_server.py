"""
ws_server.py
------------
aiohttp HTTP + WebSocket server that:
  - Serves the phone camera page at  GET /
  - Accepts WebSocket connections at  GET /ws
  - Puts received JPEG bytes into a thread-safe queue.Queue
    consumed by VideoWorker.

Runs inside a daemon thread with its own asyncio event loop so it
never touches Qt's event loop.
"""

import asyncio
import os
import queue
import threading
import logging
import ssl
from pathlib import Path

from aiohttp import web, WSMsgType
from networking.ssl_gen import generate_self_signed_cert

log = logging.getLogger(__name__)

_HTML_PATH = Path(__file__).parent / "camera_page.html"


class WebSocketServer:
    """Async HTTP + WebSocket server, lifecycle-managed from Qt thread."""

    def __init__(self, port: int = 9000, frame_queue: "queue.Queue | None" = None):
        self._port = port
        self._frame_queue: queue.Queue = frame_queue or queue.Queue(maxsize=8)
        self._loop: "asyncio.AbstractEventLoop | None" = None
        self._runner: "web.AppRunner | None" = None
        self._stop_event: "asyncio.Event | None" = None
        self._thread: "threading.Thread | None" = None
        self._on_connect = None
        self._on_disconnect = None

        # ── SSL Setup ──────────────────────────────────────────────────────
        self._cert_path = os.path.join("assets", "cert.pem")
        self._key_path = os.path.join("assets", "key.pem")
        try:
            generate_self_signed_cert(self._cert_path, self._key_path)
            self._use_ssl = True
        except Exception as e:
            log.error("Failed to generate SSL cert: %s. Falling back to HTTP.", e)
            self._use_ssl = False

    # ── Public ─────────────────────────────────────────────────────────────

    @property
    def port(self) -> int:
        return self._port

    @property
    def frame_queue(self) -> queue.Queue:
        return self._frame_queue

    def set_callbacks(self, on_connect=None, on_disconnect=None):
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect

    def start(self, host: str = "0.0.0.0") -> None:
        """Start the server in a background daemon thread."""
        self._thread = threading.Thread(
            target=self._run_loop, args=(host,), daemon=True, name="NethraWS"
        )
        self._thread.start()

    def stop(self) -> None:
        """Gracefully shut the server down (blocks up to 4 s)."""
        if self._loop and self._loop.is_running():
            log.info("Stopping WebSocketServer...")
            try:
                # Trigger internal cleanup
                fut = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
                fut.result(timeout=3)
            except Exception as e:
                log.warning("Server shutdown error: %s", e)
            
            # Stop the loop
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=1)
            log.info("Server stopped.")

    # ── Internals ──────────────────────────────────────────────────────────

    async def _shutdown(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._runner:
            await self._runner.cleanup()
        
        # Await pending tasks to avoid 'Task was destroyed but it is pending'
        tasks = [t for t in asyncio.all_tasks(self._loop) if t is not asyncio.current_task()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _run_loop(self, host: str) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve(host))

    async def _serve(self, host: str) -> None:
        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/icon.png", self._handle_icon)
        app.router.add_get("/ws", self._handle_ws)

        self._runner = web.AppRunner(app)
        await self._runner.setup()

        ssl_ctx = None
        if self._use_ssl:
            ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(self._cert_path, self._key_path)

        # Try to bind with a few retries for Windows TIME_WAIT issues
        max_retries = 3
        for i in range(max_retries):
            try:
                site = web.TCPSite(self._runner, host, self._port, ssl_context=ssl_ctx)
                await site.start()
                break
            except OSError as e:
                if i == max_retries - 1: raise
                log.warning(f"Port {self._port} busy, retrying in 2s... ({e})")
                await asyncio.sleep(2)
        
        proto = "https" if self._use_ssl else "http"
        log.info("NethraLink server  %s://%s:%d", proto, host, self._port)

        self._stop_event = asyncio.Event()
        await self._stop_event.wait()


    async def _handle_index(self, request: web.Request) -> web.Response:
        html = _HTML_PATH.read_text(encoding="utf-8")
        return web.Response(content_type="text/html", text=html)

    async def _handle_icon(self, request: web.Request) -> web.Response:
        icon_path = os.path.join("assets", "icon.png")
        if os.path.exists(icon_path):
            with open(icon_path, "rb") as f:
                return web.Response(body=f.read(), content_type="image/png")
        return web.Response(status=404)

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(max_msg_size=5 * 1024 * 1024)
        await ws.prepare(request)

        log.info("WebSocket client connected from %s", request.remote)
        if self._on_connect:
            self._on_connect()

        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                try:
                    self._frame_queue.put_nowait(msg.data)
                except queue.Full:
                    pass  # drop frame – back-pressure
            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break

        log.info("WebSocket client disconnected from %s", request.remote)
        if self._on_disconnect:
            self._on_disconnect()
        return ws
