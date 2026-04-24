"""
manager.py
----------
Thin subprocess wrapper around the `adb` CLI (Android Debug Bridge).
Supports USB and Wi-Fi (TCP/IP) connections.
All functions are synchronous – call from a QThread, never the GUI thread.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger(__name__)

# ── ADB executable resolution ───────────────────────────────────────────────
# Check multiple known locations so the app works right after install
# even if PATH hasn't been refreshed in the current process.
_CANDIDATE_PATHS = [
    # NethraLink auto-installer location
    Path(os.path.expanduser("~")) / "platform-tools" / "adb.exe",
    # Common manual installs
    Path("C:/platform-tools/adb.exe"),
    Path("C:/Android/platform-tools/adb.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
]


def _adb_exe() -> str:
    """Return the first usable adb executable path."""
    # 1. Check PATH (works after terminal restart)
    found = shutil.which("adb")
    if found:
        return found
    # 2. Check known install locations
    for candidate in _CANDIDATE_PATHS:
        if candidate.exists():
            log.debug("Using adb from: %s", candidate)
            return str(candidate)
    return "adb"  # will raise FileNotFoundError with clear message


# ── Data types ──────────────────────────────────────────────────────────────

class AdbDevice(NamedTuple):
    serial: str
    state: str   # "device" | "offline" | "unauthorized"
    model: str   # may be empty


# ── Public API ──────────────────────────────────────────────────────────────

def is_adb_available() -> bool:
    """Return True if adb is available (PATH or known install locations)."""
    if shutil.which("adb"):
        return True
    return any(p.exists() for p in _CANDIDATE_PATHS)


def list_devices() -> list:
    """Run `adb devices -l` and return a list of AdbDevice (USB + Wi-Fi)."""
    try:
        result = subprocess.run(
            [_adb_exe(), "devices", "-l"],
            capture_output=True, text=True, timeout=6
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("adb list_devices: %s", exc)
        return []

    devices = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        model = next(
            (p.split(":", 1)[1].replace("_", " ")
             for p in parts[2:] if p.startswith("model:")),
            ""
        )
        # Tag Wi-Fi connections
        if ":" in serial:
            model = model or serial
        devices.append(AdbDevice(serial=serial, state=state, model=model))
    return devices


def setup_reverse(port: int, serial: str | None = None) -> bool:
    """Run `adb reverse tcp:PORT tcp:PORT`. Returns True on success."""
    cmd = _base(serial) + ["reverse", f"tcp:{port}", f"tcp:{port}"]
    log.info("adb: %s", " ".join(cmd))
    return _run(cmd)


def teardown_reverse(port: int, serial: str | None = None) -> None:
    """Run `adb reverse --remove tcp:PORT`."""
    _run(_base(serial) + ["reverse", "--remove", f"tcp:{port}"], check=False)


def open_browser(url: str, serial: str | None = None) -> bool:
    """Launch the default browser on the device at *url*."""
    cmd = _base(serial) + [
        "shell", "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", url,
    ]
    return _run(cmd)


# ── Wi-Fi ADB ───────────────────────────────────────────────────────────────

def enable_tcpip(port: int = 5555, serial: str | None = None) -> bool:
    """
    Enable TCP/IP mode on the device (requires active USB connection).
    Run this before disconnecting the USB cable for Wi-Fi ADB.
    """
    cmd = _base(serial) + ["tcpip", str(port)]
    log.info("adb: %s", " ".join(cmd))
    ok = _run(cmd)
    if ok:
        import time
        time.sleep(1.5)   # give device time to switch modes
    return ok


def connect_wifi(ip: str, port: int = 5555) -> tuple:
    """
    Run `adb connect IP:PORT`.
    Returns (success: bool, message: str).
    """
    addr = f"{ip}:{port}"
    try:
        result = subprocess.run(
            [_adb_exe(), "connect", addr],
            capture_output=True, text=True, timeout=10
        )
        output = (result.stdout + result.stderr).strip()
        success = ("connected" in output.lower()) and ("unable" not in output.lower()) and ("failed" not in output.lower())
        
        # Also succeed if already connected
        if "already connected" in output.lower():
            success = True
            
        log.info("adb connect %s → %s", addr, output)
        return success, output
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        msg = str(exc)
        log.warning("adb connect_wifi: %s", msg)
        return False, msg


def disconnect_wifi(ip: str, port: int = 5555) -> None:
    """Run `adb disconnect IP:PORT`."""
    addr = f"{ip}:{port}"
    try:
        subprocess.run([_adb_exe(), "disconnect", addr],
                       capture_output=True, timeout=5)
        log.info("adb disconnect %s", addr)
    except Exception as exc:
        log.warning("adb disconnect_wifi: %s", exc)


# ── Internal helpers ─────────────────────────────────────────────────────────

def _base(serial: str | None) -> list:
    exe = _adb_exe()
    return [exe, "-s", serial] if serial else [exe]


def _run(cmd: list, check: bool = True) -> bool:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if check and result.returncode != 0:
            log.warning("adb failed [%s]: %s",
                        " ".join(str(c) for c in cmd),
                        result.stderr.strip())
            return False
        return True
    except FileNotFoundError:
        log.warning("adb not found. Expected at: %s", _CANDIDATE_PATHS[0])
        return False
    except subprocess.TimeoutExpired:
        log.warning("adb timed out: %s", " ".join(str(c) for c in cmd))
        return False
