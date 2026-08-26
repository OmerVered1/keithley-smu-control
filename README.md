# Keithley SMU Control Suite

Professional control and I-V characterization software for Keithley Source Measure Units (SMUs).

## Supported Instruments

### Keithley 2450 SourceMeter
- USB VISA communication (pyvisa)
- Source voltage/current: +/-200V, +/-1A
- Multiple GUI versions (PyQt5, tkinter)
- See [README_keithley.md](README_keithley.md) for details

### Keithley 6430 Sub-Femtoamp Remote SourceMeter
- RS-232 serial communication (pyserial) via USB-to-serial converter
- Source voltage/current: +/-105V, +/-105mA
- Sub-femtoamp current measurement (down to 0.4 fA)
- Guard mode for ultra-low current
- See [README_k6430.md](README_k6430.md) for details

### Keithley 2602B Dual-Channel SourceMeter
- VISA communication (USB, GPIB, Ethernet, RS-232 via pyvisa)
- Dual independent channels (smua/smub)
- Source voltage/current: +/-40V, +/-3A DC (10A pulse), 40.4W per channel
- TSP (Test Script Processor) native command interface
- Channel A/B toggle with independent output controls

### Keithley 2611A SourceMeter
- LAN (LXI Class C / VXI-11), USB, GPIB, RS-232
- Source voltage/current: +/-200V, +/-1.5A
- Single channel (smua), TSP native command interface
- Same TSP command family as the 2602B

## Features (All Instruments)

- Live multimeter mode with large digital displays
- I-V sweep characterization (Linear, List, Log)
- Dual Y-axis graphing with presets
- Wave generator tool for custom waveforms
- CSV export with auto-save
- Configuration save/load (JSON)
- Safety limits enforcement
- Simulation mode for testing without hardware

## Quick Start

### Unified Launcher (recommended)
```bash
pip install -r requirements_k2602b.txt
python launcher.py
```

### Individual Instruments
```bash
# Keithley 2450
pip install -r requirements_k2450.txt
python keithley2450_pyqt.py

# Keithley 6430
pip install -r requirements_k6430.txt
python keithley6430_pyqt.py

# Keithley 2602B
pip install -r requirements_k2602b.txt
python keithley2602b_pyqt.py

# Keithley 2611A
pip install -r requirements_k2611a.txt
python keithley2611a_pyqt.py
```

## File Structure

```
keithley2450_driver.py      # K2450 VISA driver
keithley2450_pyqt.py        # K2450 PyQt5 GUI (recommended)
keithley2450_gui.py         # K2450 tkinter GUI (legacy)
keithley2450_app.py         # K2450 tkinter GUI (extended)
requirements_k2450.txt      # K2450 dependencies
requirements_keithley.txt   # K2450 dependencies (alternate)
README_keithley.md          # K2450 documentation

keithley6430_driver.py      # K6430 RS-232 serial driver
keithley6430_pyqt.py        # K6430 PyQt5 GUI
requirements_k6430.txt      # K6430 dependencies
README_k6430.md             # K6430 documentation

keithley2602b_driver.py     # K2602B TSP driver (dual-channel)
keithley2602b_pyqt.py       # K2602B PyQt5 GUI
requirements_k2602b.txt     # K2602B dependencies

keithley2611a_driver.py     # K2611A TSP driver (single-channel, LAN/GPIB/USB/RS-232)
keithley2611a_pyqt.py       # K2611A PyQt5 GUI
requirements_k2611a.txt     # K2611A dependencies

launcher.py                 # Unified instrument launcher
K2450Suite/                 # K2450 packaging resources
```

## Author

**Omer Vered**

## Disclaimer

This project is an independent, open-source tool developed by a third party. It is **not affiliated with, endorsed by, or supported by Tektronix, Inc. or Keithley Instruments**. "Keithley" and "SourceMeter" are registered trademarks of Tektronix, Inc. These names are used solely for the purpose of identifying the instruments this software is designed to communicate with.

Communication with instruments is performed using standard SCPI commands and TSP (Test Script Processor) as documented in the publicly available Keithley reference manuals. No proprietary Keithley/Tektronix software or source code was used or reproduced.

**Use at your own risk.** This software controls physical instruments capable of sourcing potentially hazardous voltages and currents. The author accepts no responsibility for damage to instruments, equipment, or any other harm resulting from the use or misuse of this software. Always verify safety limits and operating parameters before use. It is the user's sole responsibility to ensure safe and correct operation in accordance with the instrument's official documentation.

## License

MIT License — see [LICENSE](LICENSE) for full text.

Copyright (c) 2026 Omer Vered
