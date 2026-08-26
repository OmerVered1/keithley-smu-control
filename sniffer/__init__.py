"""
Passive LAN packet capture/decode, vendored from OmerVered1/lan-signal-sniffer.

Watches an instrument's traffic and decodes it against a saved DeviceProfile,
without ever opening a connection to the instrument itself — so vendor
software (e.g. Calisto) keeps its single allowed TCP client while this
records alongside it. See calorimeter_reader.py's SniffingCalorimeterReader
for how this is used.

Needs a packet capture driver (Npcap on Windows, BPF on macOS/Linux) and
elevated/admin rights — see capture.capture_readiness() for a diagnosable
check before starting a capture.
"""
