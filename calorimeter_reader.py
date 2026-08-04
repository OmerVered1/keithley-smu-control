# READ-ONLY MODULE
"""
Setaram calorimeter LAN reader (C80, Drop, other Setaram Ethernet controllers).

This module is read-only by construction. `_read_channel` sends only the two
hard-coded GET commands taken from the CALORIMETERS registry. No public method
accepts arbitrary bytes. Do not add write/set commands here without explicit
safety review — the connected calorimeter may be running an unattended
temperature profile driven by Calisto, and modifying its state from a second
tool could damage samples or the instrument.

Protocol (reverse-engineered Aug 2026 from a C80 Wireshark capture):
    Frame layout:  <hdr:2> <cmd:2> <arg:2> [payload…]   (big-endian)
    Server echoes the 6 request bytes and appends payload (float32 BE for
    scalar reads).

The Drop calorimeter (Alexsys) is assumed to use the same command bytes until
verified on-bench. If its HF/T values look wrong, capture Drop traffic and
extend the registry with per-instrument commands.
"""

from __future__ import annotations

import re
import socket
import struct
import subprocess
import sys
import time

from PyQt5.QtCore import QThread, pyqtSignal


C80_PORT = 1210


# ----- Registry -------------------------------------------------------------

CALORIMETERS: dict[str, dict] = {
    "C80 (Setaram)": {
        "mac": "00:50:c2:30:e1:cc",
        # C80 wire capture: HF is on channel 1, Sample T on channel 4.
        "cmd_hf": bytes.fromhex("000100" "0a" "0001"),
        "cmd_t":  bytes.fromhex("000100" "08" "0004"),
        "hf_unit": "mW",
        "t_unit": "°C",
    },
    "Drop (Alexsys)": {
        "mac": "00:50:c2:30:e1:eb",
        # Calisto config shows HF at address 2, Sample T at address 4
        # (S-type thermocouple, -49 to 1620 °C). Assuming the `arg` byte of
        # <hdr><cmd><arg> matches Calisto's address. If HF returns garbage,
        # try `00 01 00 0a 00 01` (C80 channel 1) or capture Drop TCP:1210
        # traffic to nail down the family byte.
        "cmd_hf": bytes.fromhex("000100" "0a" "0002"),
        "cmd_t":  bytes.fromhex("000100" "08" "0004"),
        "hf_unit": "mW",
        "t_unit": "°C",
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
    """Background thread that polls the two configured GET commands and emits
    sample(wall_clock_ts, hf, temp) at ~interval_s cadence. Emits error(msg)
    and exits on connect/read failure.

    `wall_clock_ts` is `time.time()` (seconds since epoch). The consuming UI
    subtracts its own reference clock to draw a relative-time axis.
    """

    sample = pyqtSignal(float, float, float)
    error = pyqtSignal(str)

    def __init__(
        self,
        host: str,
        cmd_hf: bytes,
        cmd_t: bytes,
        port: int = C80_PORT,
        interval_s: float = 1.0,
        parent=None,
    ):
        super().__init__(parent)
        self._host = host
        self._port = port
        self._cmd_hf = cmd_hf
        self._cmd_t = cmd_t
        self._interval = max(0.1, float(interval_s))
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def _read_channel(self, sock: socket.socket, cmd: bytes) -> float:
        # Only two `cmd` values ever reach this method, both hard-coded in
        # the CALORIMETERS registry. See module docstring.
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

        next_tick = time.monotonic()
        try:
            while not self._stop:
                try:
                    hf = self._read_channel(sock, self._cmd_hf)
                    t = self._read_channel(sock, self._cmd_t)
                except Exception as e:
                    self.error.emit(f"read failed: {e}")
                    return
                self.sample.emit(time.time(), hf, t)
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
