"""
LAN Instrument Network Helper
==============================
Helps reach LAN-connected instruments (e.g. a Keithley 2611A on a static IP
like 192.168.0.2) that sit on a dedicated network adapter with no DHCP.
In that setup, the PC's adapter comes up on a link-local (169.254.x.x)
address that can't route to the instrument until a matching static IP is
added — this module detects that and can add one as a secondary address
(existing addresses on the adapter are left alone).

Windows only for the auto-configure path (uses netsh + a UAC elevation
prompt); other platforms get instructions to configure it manually.

Author: Omer Vered
Date: 2026
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from typing import List, Dict, Optional, Tuple


def is_reachable(ip: str, timeout_ms: int = 500) -> bool:
    """Ping-check whether an IP is reachable, cross-platform."""
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=(timeout_ms / 1000) + 2)
        return result.returncode == 0
    except Exception:
        return False


def suggest_secondary_ip(target_ip: str) -> str:
    """Propose a host address in the same /24 as target_ip (avoiding the target itself)."""
    parts = target_ip.split(".")
    if len(parts) != 4:
        return target_ip
    a, b, c, d = parts
    host = "10" if d != "10" else "11"
    return f"{a}.{b}.{c}.{host}"


def _prefix_to_mask(prefix_len: int) -> str:
    bits = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
    return ".".join(str((bits >> (8 * i)) & 0xFF) for i in (3, 2, 1, 0))


_LIST_ADAPTERS_PS = r"""
$out = Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object {
    $ip = (Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -ne '127.0.0.1' } | Select-Object -First 1).IPAddress
    [PSCustomObject]@{ Name = $_.Name; IPAddress = $ip }
}
$out | ConvertTo-Json -Compress
"""


def list_windows_adapters() -> List[Dict[str, Optional[str]]]:
    """List active network adapters (name + current IPv4) for the user to pick from."""
    if sys.platform != "win32":
        return []
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _LIST_ADAPTERS_PS],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout.strip() or "[]")
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception:
        return []


def add_secondary_ip_windows(adapter_name: str, ip: str, prefix_len: int = 24) -> Tuple[bool, str]:
    """
    Add `ip` as a secondary IPv4 address on `adapter_name` via an elevated
    netsh call (existing addresses on the adapter are untouched). Triggers
    a UAC prompt — the caller should tell the user to expect it.
    """
    if sys.platform != "win32":
        return False, "Auto-configure is only supported on Windows."

    mask = _prefix_to_mask(prefix_len)
    script = f'netsh interface ipv4 add address name="{adapter_name}" address={ip} mask={mask}\n'

    fd, script_path = tempfile.mkstemp(suffix=".ps1", prefix="k2611a_netcfg_")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(script)

        launcher = (
            "Start-Process powershell -Verb RunAs -ArgumentList "
            f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{script_path}' -Wait"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", launcher],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            return False, f"Elevation failed or was cancelled: {err}" if err else \
                "Elevation was cancelled (UAC prompt declined)."
    except subprocess.TimeoutExpired:
        return False, "Timed out waiting for administrator approval."
    except Exception as e:
        return False, f"Failed to run elevated command: {e}"
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass

    time.sleep(1.0)
    return True, f"Requested {ip}/{prefix_len} on '{adapter_name}'."
