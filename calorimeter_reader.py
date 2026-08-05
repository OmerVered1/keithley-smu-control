# READ-ONLY MODULE
"""
Setaram calorimeter LAN reader (C80, Drop, other Setaram Ethernet controllers).

This module is read-only by construction. `_read_channel` sends only the
hard-coded GET commands taken from the CALORIMETERS registry's `channels`
dict. No public method accepts arbitrary bytes. Do not add write/set commands
here without explicit safety review — the connected calorimeter may be
running an unattended temperature profile driven by Calisto, and modifying
its state from a second tool could damage samples or the instrument.

Protocol (reverse-engineered Aug 2026 from a C80 Wireshark capture):
    Frame layout:  <hdr:2> <cmd:2> <arg:2> [payload…]   (big-endian)
    Server echoes the 6 request bytes and appends payload (float32 BE for
    scalar reads).

Channel names used in the registry are stable keys the UI depends on:
    "hf"     Heat Flow (mW)
    "t"      Sample Temperature (°C)
    "ext_t"  External / QDOS Temperature (°C) — Drop only
"""

from __future__ import annotations

import re
import socket
import struct
import subprocess
import sys
import threading
import time

from PyQt5.QtCore import QThread, pyqtSignal


C80_PORT = 1210


# ----- Registry -------------------------------------------------------------

CALORIMETERS: dict[str, dict] = {
    "C80 (Setaram)": {
        "mac": "00:50:c2:30:e1:cc",
        # Verified on-bench (Aug 2026): HF on channel 1, Sample T on channel 4.
        "channels": {
            "hf": bytes.fromhex("000100" "0a" "0001"),
            "t":  bytes.fromhex("000100" "08" "0004"),
        },
    },
    "Drop (Alexsys)": {
        "mac": "00:50:c2:30:e1:eb",
        # Verified on-bench (Aug 2026) via Wireshark capture of Calisto's
        # polling loop while a live thermocouple pair was attached:
        #   HF     — cmd 0a arg 0001 (Sample T channel returns mW as float32 BE)
        #   Sample T — cmd 08 arg 0004
        #   Ext T  — cmd 08 arg 0005 (NOT arg 0003 as originally guessed from
        #            Calisto's on-screen CAN-address labels)
        "channels": {
            "hf":    bytes.fromhex("000100" "0a" "0001"),
            "t":     bytes.fromhex("000100" "08" "0004"),
            "ext_t": bytes.fromhex("000100" "08" "0005"),
        },
    },
}

RSP_LEN = 10  # hdr(2) + cmd(2) + arg(2) + float32(4)


# ----- Discovery ------------------------------------------------------------

def discover_calorimeter_ip(mac: str) -> tuple[str | None, str]:
    """Look up the calorimeter's current IP by scanning the OS ARP cache for
    its MAC. Returns (ip_or_none, diagnostic_string).

    Requires that Calisto (or something else) has recently talked to the
    instrument so the mapping is cached. Diagnostic is empty on success and
    a specific human-readable reason on failure.
    """
    try:
        cmd = ["arp", "-a"] if sys.platform == "win32" else ["arp", "-an"]
        # capture_output + explicit utf-8 + errors=replace defends against
        # locale-encoding surprises on non-English Windows (e.g. cp1255).
        proc = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
    except FileNotFoundError:
        return None, "arp not on PATH"
    except subprocess.TimeoutExpired:
        return None, "arp -a timed out (>3 s)"
    except OSError as e:
        return None, f"arp failed to launch: {e}"

    if proc.returncode != 0:
        return None, f"arp -a returned code {proc.returncode}: {proc.stderr.strip()[:80]}"

    out = proc.stdout or ""
    lines = out.splitlines()
    try:
        target = bytes(int(b, 16) for b in mac.split(":"))
    except ValueError:
        return None, f"bad MAC in registry: {mac}"

    mac_re = re.compile(r"[0-9a-fA-F]{1,2}(?:[:-][0-9a-fA-F]{1,2}){5}")
    ip_re = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    for line in lines:
        for tok in line.split():
            if not mac_re.fullmatch(tok):
                continue
            try:
                mac_bytes = bytes(int(x, 16) for x in re.split(r"[:-]", tok))
            except ValueError:
                continue
            if mac_bytes == target:
                m = ip_re.search(line)
                if m:
                    return m.group(0), ""

    return None, f"no MAC match for {mac} in {len(lines)}-line arp output"


# ----- Availability probe ---------------------------------------------------

def probe_port_free(host: str, port: int = C80_PORT, timeout: float = 1.0) -> tuple[bool, str]:
    """Try a quick TCP connect and close. Returns (available, reason)."""
    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except ConnectionRefusedError:
        return False, "port busy — is Calisto connected to this instrument?"
    except socket.timeout:
        return False, f"connect timed out (>{timeout:.0f} s) — host reachable?"
    except OSError as e:
        return False, f"unreachable: {e}"
    try:
        s.close()
    except OSError:
        pass
    return True, ""


# ----- Reader thread --------------------------------------------------------

class CalorimeterReader(QThread):
    """Background thread that polls the configured GET commands for one
    calorimeter. Emits sample(wall_clock_ts, readings) at ~interval_s
    cadence when its autonomous polling loop is active, and also whenever
    `poll_once()` is called from an external thread (e.g. the sweep loop
    driving co-sampled reads).

    `readings` is a dict keyed by channel name (e.g. "hf", "t", "ext_t")
    with float32 values. Emits error(msg) and exits its autonomous loop on
    connect/read failure. `poll_once()` raises on error so callers can
    decide whether to keep going.

    Locking: `_sock_lock` serializes all socket access — the autonomous
    loop and any external `poll_once()` call share one socket safely.
    Pausing the autonomous loop (`pause_polling`) is what an experiment
    should do while it wants exclusive control of the socket, to avoid
    redundant polls.
    """

    sample = pyqtSignal(float, dict)
    error = pyqtSignal(str)

    def __init__(
        self,
        host: str,
        channels: dict[str, bytes],
        port: int = C80_PORT,
        interval_s: float = 1.0,
        parent=None,
    ):
        super().__init__(parent)
        self._host = host
        self._port = port
        # Copy so a mutation on the caller side can't affect the polling loop
        self._channels: dict[str, bytes] = dict(channels)
        self._interval = max(0.1, float(interval_s))
        self._stop = False
        self._sock: socket.socket | None = None
        self._sock_lock = threading.Lock()
        # Autonomous loop runs while this event is set; pause_polling()
        # clears it, resume_polling() sets it. Starts set so run() polls
        # immediately once connected.
        self._poll_enabled = threading.Event()
        self._poll_enabled.set()

    def stop(self) -> None:
        self._stop = True
        # Wake the autonomous loop if it's paused
        self._poll_enabled.set()

    def pause_polling(self) -> None:
        """Stop the autonomous polling loop until resume_polling() is
        called. External callers can still use poll_once() while paused."""
        self._poll_enabled.clear()

    def resume_polling(self) -> None:
        self._poll_enabled.set()

    def _read_channel_locked(self, cmd: bytes) -> float:
        # Assumes _sock_lock is held and _sock is not None.
        # `cmd` values only come from the immutable `channels` dict handed
        # in at construction; see module docstring.
        self._sock.sendall(cmd)
        buf = b""
        while len(buf) < RSP_LEN:
            chunk = self._sock.recv(RSP_LEN - len(buf))
            if not chunk:
                raise ConnectionError("socket closed by peer")
            buf += chunk
        return struct.unpack(">f", buf[6:10])[0]

    def _read_all_locked(self) -> dict:
        readings: dict[str, float] = {}
        for name, cmd in self._channels.items():
            readings[name] = self._read_channel_locked(cmd)
        return readings

    def poll_once(self) -> dict:
        """Synchronous read of every configured channel. Returns readings
        dict. Emits the `sample` signal so Real Time listeners see it too.
        Raises on socket errors.
        """
        with self._sock_lock:
            if self._sock is None:
                self._sock = socket.create_connection(
                    (self._host, self._port), timeout=3.0
                )
                self._sock.settimeout(2.0)
            readings = self._read_all_locked()
        # Emit outside the lock so slot handlers can't deadlock the socket
        self.sample.emit(time.time(), readings)
        return readings

    def run(self) -> None:
        # Ensure the socket is open before the autonomous loop starts, so
        # first-poll latency doesn't distort the initial samples.
        try:
            with self._sock_lock:
                if self._sock is None:
                    self._sock = socket.create_connection(
                        (self._host, self._port), timeout=3.0
                    )
                    self._sock.settimeout(2.0)
        except OSError as e:
            self.error.emit(f"connect failed: {e}")
            return

        next_tick = time.monotonic()
        try:
            while not self._stop:
                # If paused, sleep until resumed (or stopped)
                if not self._poll_enabled.wait(timeout=0.1):
                    next_tick = time.monotonic()
                    continue
                try:
                    with self._sock_lock:
                        readings = self._read_all_locked()
                except Exception as e:
                    self.error.emit(f"read failed: {e}")
                    return
                self.sample.emit(time.time(), readings)
                next_tick += self._interval
                remaining_ms = int((next_tick - time.monotonic()) * 1000)
                if remaining_ms > 0:
                    self.msleep(remaining_ms)
                else:
                    next_tick = time.monotonic()
        finally:
            with self._sock_lock:
                if self._sock is not None:
                    try:
                        self._sock.close()
                    except OSError:
                        pass
                    self._sock = None
