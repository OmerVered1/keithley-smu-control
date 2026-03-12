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

## Features (Both Instruments)

- Live multimeter mode with large digital displays
- I-V sweep characterization (Linear, List, Log)
- Dual Y-axis graphing with presets
- Wave generator tool for custom waveforms
- CSV export with auto-save
- Configuration save/load (JSON)
- Safety limits enforcement
- Simulation mode for testing without hardware

## Quick Start

### Keithley 2450
```bash
pip install -r requirements_k2450.txt
python keithley2450_pyqt.py
```

### Keithley 6430
```bash
pip install -r requirements_k6430.txt
python keithley6430_pyqt.py
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

K2450Suite/                 # K2450 packaging resources
```

## Author

**Omer Vered**

## License

Copyright 2026 Omer Vered. All rights reserved.
