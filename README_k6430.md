# K6430 Control Suite — Keithley 6430 Sub-Femtoamp Remote SourceMeter

Professional control and I-V characterization software for the **Keithley 6430 Sub-Femtoamp Remote SourceMeter**, connected via **RS-232 serial** (USB-to-serial converter).

## Features

- **RS-232 Serial Connection** with auto-detect COM port & baud rate
- **Sub-Femtoamp Current Measurement** — display down to fA range
- **Live Multimeter Mode** — large digital displays with recording & graphing
- **I-V Sweep Characterization** — Linear, List, and Log sweep modes
- **2-Wire / 4-Wire Sensing** with Guard mode for ultra-low current
- **Dual Y-axis Graphing** with presets (I-V, I-t, V/P-t, I/R-t)
- **Wave Generator Tool** — sine, square, triangle, sawtooth waveforms
- **Full Safety Protection** — voltage, current, and power limits
- **Auto-Save** — automatic CSV export after each sweep
- **Configuration Save/Load** — JSON-based settings persistence
- **Simulation Mode** — test the software without hardware (with realistic sub-fA noise)

## Keithley 6430 Specifications

| Parameter | Range |
|---|---|
| Source Voltage | ±105 V |
| Source Current | ±105 mA |
| Current Measurement | 100 fA to 105 mA |
| Sub-Femtoamp Resolution | 0.4 fA (with remote preamp) |
| Communication | RS-232 (300–19200 baud) |
| Connection | Triax (for guarded measurements) |

## Installation

### Prerequisites

- Python 3.8+
- USB-to-RS-232 converter (e.g., FTDI, Prolific) with drivers installed
- Keithley 6430 powered on with RS-232 cable connected

### Install Dependencies

```bash
pip install -r requirements_k6430.txt
```

### Run the Application

```bash
python keithley6430_pyqt.py
```

## Quick Start

1. **Connect** your USB-to-serial adapter and power on the Keithley 6430
2. Launch the application: `python keithley6430_pyqt.py`
3. Accept the license agreement (first run only)
4. Click **🔌 Connect (RS-232)** or go to Instrument → Connect
5. Click **🔍 Auto-Detect** to find your instrument automatically
6. Or select your COM port manually and click **Connect**

### Simulation Mode

To test the software without hardware:
1. Open the connection dialog
2. Set a simulation resistance (e.g., 1GΩ for sub-nA currents, 1TΩ for sub-pA)
3. Click **🎮 Start Simulation**

## Usage

### Live Multimeter

- Select source type (Voltage/Current) and measurement type
- Set source value and compliance limit
- Click **▶ START** for continuous readings
- Use **⏺ RECORD** to capture data over time
- Export recordings to CSV

### I-V Sweep

1. Configure source settings (function, range, compliance)
2. Set instrument settings (2/4-Wire, Guard mode)
3. Define sweep values using Linear, Log, or List mode
4. Optionally use the **Wave Generator** for custom waveforms
5. Click **▶ START SWEEP**
6. View results in real-time on the graph
7. Data auto-saves to `~/Documents/K6430_Data/`

### Sub-Femtoamp Tips

- Use **Guard mode** with triax cables for measurements below 1 pA
- Set **NPLC ≥ 5** for lowest noise at sub-fA levels
- Use **longer delays** (≥ 0.5s) to allow settling
- Shield your DUT from electromagnetic interference
- Keep cables short and use low-noise triax connections

## File Structure

```
keithley6430_driver.py   — RS-232 serial driver for Keithley 6430
keithley6430_pyqt.py     — Full PyQt5 GUI application
requirements_k6430.txt   — Python dependencies
README_k6430.md          — This file
```

## Architecture

### Driver (`keithley6430_driver.py`)

- `Keithley6430` class with RS-232 serial communication via `pyserial`
- Auto-detect scans all COM ports at multiple baud rates
- SCPI command interface adapted for 6430 syntax
- Safety limits enforcement (voltage, current, power)
- Simulation mode with realistic sub-femtoamp noise model
- Thread-safe with connection state management

### GUI (`keithley6430_pyqt.py`)

- `Keithley6430App(QMainWindow)` — main application
- `MultimeterPanel` — live measurement with recording
- `ConnectionDialog` — serial port selection with auto-detect
- `SourceSettingsWidget` — voltage/current source configuration
- `InstrumentSettingsWidget` — sense, guard, output off mode
- `MeasureSettingsWidget` — measurement type and range
- `DualAxisGraph` — pyqtgraph with dual Y-axis support
- `WaveToolDialog` — waveform generator
- `SafetyDialog` — safety limits configuration

## Differences from K2450 Suite

| Feature | K2450 | K6430 |
|---|---|---|
| Communication | USB VISA (pyvisa) | RS-232 Serial (pyserial) |
| Max Voltage | ±200 V | ±105 V |
| Max Current | ±1 A | ±105 mA |
| Min Current | ~10 nA | 0.4 fA |
| Power Limit | 22 W | 11 W |
| Terminals | Front/Rear BNC | Triax |
| Guard Mode | No | Yes |
| Connection | Auto-detect VISA | Auto-detect COM port |

## Safety Warning

⚠️ The Keithley 6430 can source up to **105V** and **105mA**. Always:
- Set appropriate safety limits before connecting to your DUT
- Verify compliance settings before enabling output
- Use proper triax cabling for high-impedance measurements
- Never exceed your device under test (DUT) ratings

## Author

**Omer Vered** — Hayun Group, Ben-Gurion University of the Negev (BGU)

## License

Copyright © 2026 Omer Vered, BGU. All rights reserved.
See LICENSE.txt for details.
