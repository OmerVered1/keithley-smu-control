"""
Setaram C80 Calvet calorimeter — LAN reader
============================================

Reads heat flow (mW) and sample temperature (°C) from a C80 over TCP:1210
while Calisto is running on the same PC. Calisto keeps handling BOOTP so
the C80 has an IP; we discover it by looking up the C80's fixed MAC in the
OS ARP cache, then open a second TCP connection to port 1210 alongside
Calisto's connection.

Protocol reverse-engineered from a Wireshark capture (Aug 2026):
    Frame layout:  <hdr:2> <cmd:2> <arg:2> [payload…]   (big-endian)
    Heat flow:     send  00 01 00 0a 00 01  → 10-byte response, float32-BE in bytes [6:10] = mW
    Sample T:      send  00 01 00 08 00 04  → 10-byte response, float32-BE in bytes [6:10] = °C

Multi-client TCP is confirmed OK; we do not disturb Calisto's stream.
"""

from __future__ import annotations

import re
import socket
import struct
import subprocess
import sys
import time

from PyQt5.QtCore import QThread, pyqtSignal


C80_MAC = "00:50:c2:30:e1:cc"
C80_PORT = 1210

CMD_HF = bytes.fromhex("000100 0a 0001".replace(" ", ""))
CMD_T = bytes.fromhex("000100 08 0004".replace(" ", ""))
RSP_LEN = 10


def discover_c80_ip() -> str | None:
    """Return the C80's current IP by looking up its MAC in the OS ARP cache.

    Requires that Calisto (or something else) has recently talked to the C80
    so the mapping is cached. Returns None if not found or arp is unavailable.
    """
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(["arp", "-a"], text=True, timeout=3)
        else:
            out = subprocess.check_output(["arp", "-an"], text=True, timeout=3)
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

    target = bytes(int(b, 16) for b in C80_MAC.split(":"))
    mac_re = re.compile(r"[0-9a-fA-F]{1,2}(?:[:-][0-9a-fA-F]{1,2}){5}")
    ip_re = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    for line in out.splitlines():
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
                    return m.group(0)
    return None


class C80Reader(QThread):
    """Background thread polling HF and T from the C80.

    Emits sample(elapsed_s, hf_mW, t_C) at ~interval_s cadence.
    Emits error(msg) and exits on connect/read failure.
    """

    sample = pyqtSignal(float, float, float)
    error = pyqtSignal(str)

    def __init__(self, host: str, port: int = C80_PORT, interval_s: float = 1.0, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._interval = max(0.1, float(interval_s))
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def _read_channel(self, sock: socket.socket, cmd: bytes) -> float:
        sock.sendall(cmd)
        buf = b""
        while len(buf) < RSP_LEN:
            chunk = sock.recv(RSP_LEN - len(buf))
            if not chunk:
                raise ConnectionError("socket closed by peer")
            buf += chunk
        return struct.unpack(">f", buf[6:10])[0]

    def run(self) -> None:
        try:
            sock = socket.create_connection((self._host, self._port), timeout=3.0)
            sock.settimeout(2.0)
        except OSError as e:
            self.error.emit(f"connect failed: {e}")
            return

        t0 = time.monotonic()
        next_tick = t0
        try:
            while not self._stop:
                try:
                    hf = self._read_channel(sock, CMD_HF)
                    t = self._read_channel(sock, CMD_T)
                except Exception as e:
                    self.error.emit(f"read failed: {e}")
                    return
                self.sample.emit(time.monotonic() - t0, hf, t)
                next_tick += self._interval
                remaining_ms = int((next_tick - time.monotonic()) * 1000)
                if remaining_ms > 0:
                    self.msleep(remaining_ms)
                else:
                    next_tick = time.monotonic()
        finally:
            try:
                sock.close()
            except OSError:
                pass
