# Keithley 2450 SourceMeter Control Program

A professional, user-friendly GUI control application for the Keithley 2450 Source Measure Unit (SMU), designed with safety as a top priority.

## Features

- **Safe Operation**: Configurable safety limits to protect your expensive instrument
- **Source Voltage/Current**: Easy configuration with compliance protection
- **Live Measurements**: Real-time voltage, current, resistance, and power display
- **IV Sweep**: Voltage and current sweeps with bidirectional option
- **Data Plotting**: Interactive I-V, V-t, I-t, and R-t plots
- **Data Logging**: Automatic data logging with CSV export
- **Simulation Mode**: Test the software without hardware connected
- **Modern Interface**: Clean, KickStart-inspired user interface

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements_keithley.txt
```

### 2. Install VISA Backend (Choose One)

#### Option A: NI-VISA (Recommended for best compatibility)
1. Download and install NI-VISA from [ni.com](https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html)
2. This provides the most reliable USB and GPIB communication

#### Option B: Pure Python Backend (No NI-VISA required)
```bash
pip install pyvisa-py pyusb
```
Note: For USB on Windows, you may need to install libusb drivers using Zadig.

## Usage

### Starting the Application

```bash
python keithley2450_gui.py
```

### Quick Start Guide

1. **Connect to Instrument**
   - Click "Refresh" to find available VISA resources
   - Select your Keithley 2450 from the dropdown
   - Click "Connect"
   - Or use "Simulate" to test without hardware

2. **Configure Source**
   - Select Voltage or Current source mode
   - Enter the source value and compliance limit
   - Click "Apply Source Settings"

3. **Enable Output**
   - Review your settings
   - Click "Turn OUTPUT ON" (requires confirmation)
   - Use "EMERGENCY OFF" for immediate shutdown

4. **Take Measurements**
   - Use "Measure Once" for single readings
   - Use "Start Continuous" for live monitoring
   - Adjust measurement interval as needed

5. **Run IV Sweeps**
   - Go to the "IV Sweep" tab
   - Configure sweep parameters (start, stop, points)
   - Click "Run Sweep" and confirm

6. **Export Data**
   - Go to the "Data Log" tab
   - Click "Export CSV" to save your data

## Safety Features

### Software Safety Limits

The program includes configurable safety limits to prevent damage:

| Parameter | Default Limit |
|-----------|--------------|
| Max Voltage | ±20 V |
| Max Current | ±100 mA |
| Compliance Voltage | 21 V |
| Compliance Current | 105 mA |
| Power Limit | 20 W |

Access via **Instrument → Safety Settings**

### Safety Behaviors

- **Output Confirmation**: Enabling output requires user confirmation
- **Emergency Stop**: Red button immediately disables output and resets
- **Safe Disconnect**: Output automatically disabled before disconnecting
- **Safe Initialization**: Instrument reset to 0V output on connection
- **Value Validation**: All source values checked against safety limits

## File Structure

```
keithley2450_driver.py    # Core instrument driver with safety features
keithley2450_gui.py       # Main GUI application
requirements_keithley.txt # Python dependencies
README_keithley.md        # This file
```

## Driver API

The driver can also be used independently in scripts:

```python
from keithley2450_driver import Keithley2450, SafetyLimits

# Create custom safety limits
limits = SafetyLimits(max_voltage=10.0, max_current=0.05)

# Connect and use
with Keithley2450(safety_limits=limits) as smu:
    smu.connect("USB0::0x05E6::0x2450::04096331::INSTR")
    
    # Source voltage, measure current
    smu.set_source_voltage(5.0, compliance_current=0.01)
    smu.output_on()
    
    result = smu.measure_all()
    print(f"V={result.voltage}, I={result.current}")
    
    # Run IV sweep
    data = smu.voltage_sweep(0, 10, 100)
    
    # Output automatically disabled on exit
```

## Troubleshooting

### No instruments found
- Ensure the Keithley 2450 is powered on and connected via USB
- Check that NI-VISA or pyvisa-py backend is installed
- Try running as Administrator (Windows)
- Check Device Manager for the instrument

### Connection timeout
- Increase timeout in driver settings
- Check USB cable connection
- Try a different USB port

### "Not a Keithley 2450" error
- Verify you selected the correct VISA resource
- Use simulation mode to test the software

## License

This software is provided as-is for controlling Keithley 2450 instruments.
Use at your own risk. Always ensure proper safety measures are in place
when operating precision measurement equipment.

## Support

For issues with the Keithley 2450 instrument itself, contact Tektronix/Keithley support.
