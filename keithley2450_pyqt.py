"""
Keithley 2450 SourceMeter Control Application
PyQt5 + pyqtgraph version with ALL features

Features:
- Modern dark theme UI with pyqtgraph plotting
- Live multimeter mode with large digital displays
- Full I-V sweep characterization (Linear, List, Log)
- DC/Pulse mode, Front/Rear terminals, 2/4-Wire sensing
- Dual Y-axis graphs with presets
- Complete safety features
- Menu bar with configuration save/load
"""

import sys
import os
import time
import threading
import csv
import json
import numpy as np
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QTabWidget, QGroupBox, QLabel, QPushButton,
    QComboBox, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QFrame, QMessageBox, QFileDialog, QDialog, QListWidget,
    QProgressBar, QStatusBar, QTextEdit, QSizePolicy, QMenuBar,
    QMenu, QAction, QFormLayout, QScrollArea, QAbstractSpinBox,
    QInputDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QSettings
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon

import pyqtgraph as pg

# Import our driver
from keithley2450_driver import (
    Keithley2450, SafetyLimits, Keithley2450Error,
    SourceFunction, MeasureFunction, SenseMode
)

# Configure pyqtgraph
pg.setConfigOptions(antialias=True, background='#ffffff', foreground='#1a1a2e')

# Version info
__version__ = "2.0.5"
__app_name__ = "K2450 Control Suite"
__author__ = "Omer Vered"
__organization__ = "Omer Vered MSc Research"
__copyright__ = "Copyright 2026 Omer Vered"


@dataclass
class MeasurementPoint:
    """Single measurement data point"""
    index: int
    timestamp: float
    source_value: float
    computer_time: str = ""  # Absolute computer datetime
    voltage: Optional[float] = None
    current: Optional[float] = None
    resistance: Optional[float] = None
    power: Optional[float] = None


# === Experiments ===

EXPERIMENTS_FILE = os.path.join(os.path.expanduser("~"), "Documents",
                                "K2450_Experiments", "experiments.json")


class ExperimentStore:
    """JSON-backed store of named experiments (settings + sweep list + wave config + notes)."""

    def __init__(self, path: str = EXPERIMENTS_FILE):
        self.path = path
        self._experiments: Dict[str, dict] = {}
        self.load()

    def load(self):
        self._experiments = {}
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
            for exp in data.get("experiments", []):
                name = exp.get("name")
                if name:
                    self._experiments[name] = exp
        except Exception as e:
            print(f"ExperimentStore load error: {e}")

    def _persist(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump({"experiments": list(self._experiments.values())}, f, indent=2)

    def names(self) -> List[str]:
        return sorted(self._experiments.keys(), key=str.lower)

    def get(self, name: str) -> Optional[dict]:
        return self._experiments.get(name)

    def save(self, name: str, payload: dict):
        now = datetime.now().isoformat(timespec="seconds")
        existing = self._experiments.get(name, {})
        record = dict(payload)
        record["name"] = name
        record["created_at"] = existing.get("created_at", now)
        record["modified_at"] = now
        self._experiments[name] = record
        self._persist()

    def delete(self, name: str):
        if name in self._experiments:
            del self._experiments[name]
            self._persist()

    def rename(self, old: str, new: str):
        if old not in self._experiments or new == old:
            return
        record = self._experiments.pop(old)
        record["name"] = new
        record["modified_at"] = datetime.now().isoformat(timespec="seconds")
        self._experiments[new] = record
        self._persist()


class LightPalette(QPalette):
    """Light theme: black text on white surfaces with subtle grays for borders."""
    def __init__(self):
        super().__init__()
        self.setColor(QPalette.Window, QColor(255, 255, 255))          # #ffffff
        self.setColor(QPalette.WindowText, QColor(26, 26, 46))         # #1a1a2e (near-black)
        self.setColor(QPalette.Base, QColor(255, 255, 255))            # #ffffff
        self.setColor(QPalette.AlternateBase, QColor(243, 244, 246))   # #f3f4f6
        self.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))     # #ffffff
        self.setColor(QPalette.ToolTipText, QColor(26, 26, 46))        # #1a1a2e
        self.setColor(QPalette.Text, QColor(26, 26, 46))               # #1a1a2e
        self.setColor(QPalette.Button, QColor(243, 244, 246))          # #f3f4f6
        self.setColor(QPalette.ButtonText, QColor(26, 26, 46))         # #1a1a2e
        self.setColor(QPalette.BrightText, QColor(220, 38, 38))        # #dc2626
        self.setColor(QPalette.Link, QColor(37, 99, 235))              # #2563eb
        self.setColor(QPalette.Highlight, QColor(59, 130, 246))        # #3b82f6
        self.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.setColor(QPalette.Disabled, QPalette.WindowText, QColor(156, 163, 175))  # #9ca3af
        self.setColor(QPalette.Disabled, QPalette.Text, QColor(156, 163, 175))
        self.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(156, 163, 175))


class ToggleButton(QPushButton):
    """Toggle button with selected/unselected state"""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._selected = False
        self._update_style()
    
    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()
    
    def is_selected(self) -> bool:
        return self._selected
    
    def _update_style(self):
        if self._selected:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #1a1a2e;
                    color: #ffffff;
                    border: none;
                    padding: 6px 16px;
                    font-weight: bold;
                    font-size: 14px;
                    border-radius: 5px;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff;
                    color: #6b7280;
                    border: 1px solid #d1d5db;
                    padding: 6px 16px;
                    font-weight: 500;
                    font-size: 14px;
                    border-radius: 5px;
                }
                QPushButton:hover { background-color: #f3f4f6; color: #1a1a2e; }
            """)


class DigitalDisplay(QLabel):
    """Large digital display for multimeter readings"""
    
    def __init__(self, unit: str = "", decimals: int = 6):
        super().__init__("----")
        self.unit = unit
        self.decimals = decimals
        self.color = "#22c55e"
        self.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: #22c55e;
                font-family: 'Inter', sans-serif;
                font-size: 28px;
                font-weight: bold;
                padding: 10px 15px;
                border: none;
                qproperty-alignment: AlignRight;
            }
        """)
        self.setMinimumHeight(50)
    
    def set_value(self, value: float):
        if value is None:
            self.setText("----")
            return
        
        abs_val = abs(value)
        if abs_val >= 1e6:
            text = f"{value/1e6:.{self.decimals}f} M{self.unit}"
        elif abs_val >= 1e3:
            text = f"{value/1e3:.{self.decimals}f} k{self.unit}"
        elif abs_val >= 1:
            text = f"{value:.{self.decimals}f} {self.unit}"
        elif abs_val >= 1e-3:
            text = f"{value*1e3:.{self.decimals}f} m{self.unit}"
        elif abs_val >= 1e-6:
            text = f"{value*1e6:.{self.decimals}f} µ{self.unit}"
        elif abs_val >= 1e-9:
            text = f"{value*1e9:.{self.decimals}f} n{self.unit}"
        elif abs_val == 0:
            text = f"0.{'0'*self.decimals} {self.unit}"
        else:
            text = f"{value:.{self.decimals}e} {self.unit}"
        self.setText(text)
    
    def set_color(self, color: str):
        self.color = color
        self.setStyleSheet(f"""
            QLabel {{
                background-color: transparent;
                color: {color};
                font-family: 'Inter', sans-serif;
                font-size: 28px;
                font-weight: bold;
                padding: 10px 15px;
                border: none;
                qproperty-alignment: AlignRight;
            }}
        """)


class MultimeterPanel(QWidget):
    """Live multimeter mode panel"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = parent
        self.running = False
        self.recording = False
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_reading)
        self.reading_count = 0
        self.record_start_time = None
        self.recorded_data = []  # List of (time, voltage, current, resistance, power)
        self.last_resistance: Optional[float] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("Live Multimeter")
        title.setFont(QFont("Google Sans", 28, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Settings row
        settings = QHBoxLayout()
        
        settings.addWidget(QLabel("Measure:"))
        self.measure_type = QComboBox()
        self.measure_type.addItems(["Voltage", "Current", "Resistance", "All"])
        self.measure_type.setCurrentText("All")
        settings.addWidget(self.measure_type)
        
        settings.addWidget(QLabel("Source:"))
        self.source_type = QComboBox()
        self.source_type.addItems(["Voltage", "Current"])
        self.source_type.currentTextChanged.connect(self._update_source_units)
        settings.addWidget(self.source_type)
        
        settings.addWidget(QLabel("Value:"))
        self.source_value = QDoubleSpinBox()
        self.source_value.setRange(-200, 200)
        self.source_value.setDecimals(4)
        self.source_value.setValue(0)
        self.source_value.setSuffix(" V")
        settings.addWidget(self.source_value)
        
        settings.addWidget(QLabel("Limit:"))
        self.compliance = QDoubleSpinBox()
        self.compliance.setRange(0.001, 1.0)
        self.compliance.setDecimals(4)
        self.compliance.setValue(0.1)
        self.compliance.setSuffix(" A")
        settings.addWidget(self.compliance)

        settings.addWidget(QLabel("V Range:"))
        self.voltage_range = QComboBox()
        self.voltage_range.addItems(["Auto", "200 mV", "2 V", "20 V", "200 V"])
        settings.addWidget(self.voltage_range)

        settings.addWidget(QLabel("I Range:"))
        self.current_range = QComboBox()
        self.current_range.addItems(["Auto", "10 nA", "100 nA", "1 µA", "10 µA", "100 µA", "1 mA", "10 mA", "100 mA", "1 A"])
        settings.addWidget(self.current_range)

        settings.addStretch()
        layout.addLayout(settings)

        # Instrument settings row
        inst_row = QHBoxLayout()

        inst_row.addWidget(QLabel("Terminals:"))
        self.front_btn = ToggleButton("Front")
        self.front_btn.clicked.connect(lambda: self._set_terminal("Front"))
        inst_row.addWidget(self.front_btn)

        self.rear_btn = ToggleButton("Rear")
        self.rear_btn.set_selected(True)
        self.rear_btn.clicked.connect(lambda: self._set_terminal("Rear"))
        inst_row.addWidget(self.rear_btn)
        self.terminal = "Rear"

        inst_row.addWidget(QLabel("    Sense:"))
        self.sense_2w = ToggleButton("2-Wire")
        self.sense_2w.clicked.connect(lambda: self._set_sense("2-Wire"))
        inst_row.addWidget(self.sense_2w)

        self.sense_4w = ToggleButton("4-Wire")
        self.sense_4w.set_selected(True)
        self.sense_4w.clicked.connect(lambda: self._set_sense("4-Wire"))
        inst_row.addWidget(self.sense_4w)
        self.sense = "4-Wire"

        inst_row.addStretch()
        layout.addLayout(inst_row)

        # Digital displays
        displays = QGridLayout()

        v_group = QGroupBox("Voltage")
        v_layout = QVBoxLayout(v_group)
        self.voltage_display = DigitalDisplay("V", 6)
        self.voltage_display.set_color("#16a34a")  # Darker green
        v_layout.addWidget(self.voltage_display)
        displays.addWidget(v_group, 0, 0)
        
        i_group = QGroupBox("Current")
        i_layout = QVBoxLayout(i_group)
        self.current_display = DigitalDisplay("A", 6)
        self.current_display.set_color("#ea580c")  # Darker orange
        i_layout.addWidget(self.current_display)
        displays.addWidget(i_group, 0, 1)
        
        r_group = QGroupBox("Resistance")
        r_layout = QVBoxLayout(r_group)
        self.resistance_display = DigitalDisplay("Ω", 4)
        self.resistance_display.set_color("#0891b2")  # Darker cyan
        r_layout.addWidget(self.resistance_display)
        displays.addWidget(r_group, 1, 0)
        
        p_group = QGroupBox("Power")
        p_layout = QVBoxLayout(p_group)
        self.power_display = DigitalDisplay("W", 6)
        self.power_display.set_color("#c026d3")  # Darker magenta
        p_layout.addWidget(self.power_display)
        displays.addWidget(p_group, 1, 1)
        
        layout.addLayout(displays)
        
        # Rate and stats
        rate_layout = QHBoxLayout()
        rate_layout.addWidget(QLabel("Update Rate:"))
        self.update_rate = QComboBox()
        self.update_rate.addItems(["Slow (1 Hz)", "Medium (5 Hz)", "Fast (10 Hz)", "Max (20 Hz)"])
        self.update_rate.setCurrentIndex(1)
        self.update_rate.currentIndexChanged.connect(self._update_rate_changed)
        rate_layout.addWidget(self.update_rate)
        
        self.readings_label = QLabel("Readings: 0")
        rate_layout.addWidget(self.readings_label)
        rate_layout.addStretch()
        layout.addLayout(rate_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("START")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a1a2e; color: #ffffff;
                font-family: 'Inter'; font-size: 14px; font-weight: bold;
                padding: 8px 20px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #374151; }
            QPushButton:disabled { background-color: #e5e7eb; color: #9ca3af; }
        """)
        self.start_btn.clicked.connect(self.start_live)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; color: #ffffff;
                font-family: 'Inter'; font-size: 14px; font-weight: bold;
                padding: 8px 20px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #b91c1c; }
            QPushButton:disabled { background-color: #e5e7eb; color: #9ca3af; }
        """)
        self.stop_btn.clicked.connect(self.stop_live)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        layout.addLayout(btn_layout)

        # Recording buttons
        record_layout = QHBoxLayout()

        self.record_btn = QPushButton("RECORD")
        self.record_btn.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6; color: #1a1a2e;
                font-family: 'Inter'; font-size: 14px; font-weight: bold;
                padding: 8px 20px; border-radius: 6px; border: 1px solid #d1d5db;
            }
            QPushButton:hover { background-color: #e5e7eb; }
            QPushButton:disabled { background-color: #f9fafb; color: #9ca3af; border-color: #e5e7eb; }
        """)
        self.record_btn.clicked.connect(self._start_recording)
        self.record_btn.setEnabled(False)
        record_layout.addWidget(self.record_btn)

        self.pause_record_btn = QPushButton("PAUSE")
        self.pause_record_btn.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6; color: #1a1a2e;
                font-family: 'Inter'; font-size: 14px; font-weight: bold;
                padding: 8px 20px; border-radius: 6px; border: 1px solid #d1d5db;
            }
            QPushButton:hover { background-color: #e5e7eb; }
            QPushButton:disabled { background-color: #f9fafb; color: #9ca3af; border-color: #e5e7eb; }
        """)
        self.pause_record_btn.clicked.connect(self._pause_recording)
        self.pause_record_btn.setEnabled(False)
        record_layout.addWidget(self.pause_record_btn)

        self.save_record_btn = QPushButton("SAVE CSV")
        self.save_record_btn.setStyleSheet("""
            QPushButton {
                background-color: #f3f4f6; color: #1a1a2e;
                font-family: 'Inter'; font-size: 14px; font-weight: bold;
                padding: 8px 20px; border-radius: 6px; border: 1px solid #d1d5db;
            }
            QPushButton:hover { background-color: #e5e7eb; }
            QPushButton:disabled { background-color: #f9fafb; color: #9ca3af; border-color: #e5e7eb; }
        """)
        self.save_record_btn.clicked.connect(self._save_recording)
        self.save_record_btn.setEnabled(False)
        record_layout.addWidget(self.save_record_btn)
        
        self.record_status = QLabel("Recording: Stopped | Points: 0")
        self.record_status.setStyleSheet("color: #9ca3af;")
        record_layout.addWidget(self.record_status)
        record_layout.addStretch()
        
        layout.addLayout(record_layout)
        
        # Recording Graph
        self.record_graph = pg.PlotWidget()
        self.record_graph.setBackground('#ffffff')
        self.record_graph.setLabel('left', 'Value', color='#1a1a2e')
        self.record_graph.setLabel('bottom', 'Time (s)', color='#1a1a2e')
        self.record_graph.setTitle("Recording Graph", color='#1a1a2e', size='14pt')
        self.record_graph.addLegend()
        self.record_graph.showGrid(x=True, y=True, alpha=0.2)
        self.record_graph.setMinimumHeight(200)
        
        # Plot lines with darker colors for visibility on white
        self.voltage_plot = self.record_graph.plot([], [], pen=pg.mkPen('#16a34a', width=2), name='Voltage (V)')
        self.current_plot = self.record_graph.plot([], [], pen=pg.mkPen('#ea580c', width=2), name='Current (A)')
        self.power_plot = self.record_graph.plot([], [], pen=pg.mkPen('#c026d3', width=2), name='Power (W)')
        
        layout.addWidget(self.record_graph)
        
        layout.addStretch()
    
    def _update_source_units(self, source_type):
        if source_type == "Voltage":
            self.source_value.setSuffix(" V")
            self.source_value.setRange(-200, 200)
            self.compliance.setSuffix(" A")
            self.compliance.setRange(0.001, 1.0)
            self.compliance.setValue(0.1)
        else:
            self.source_value.setSuffix(" A")
            self.source_value.setRange(-1, 1)
            self.compliance.setSuffix(" V")
            self.compliance.setRange(0.1, 200)
            self.compliance.setValue(20)
    
    def _set_terminal(self, terminal):
        self.terminal = terminal
        self.front_btn.set_selected(terminal == "Front")
        self.rear_btn.set_selected(terminal == "Rear")
        if self.app.smu and self.app.smu._connected:
            try:
                self.app.smu.set_terminal(terminal.upper())
            except Exception:
                pass

    def _set_sense(self, sense):
        self.sense = sense
        self.sense_2w.set_selected(sense == "2-Wire")
        self.sense_4w.set_selected(sense == "4-Wire")

    def _update_rate_changed(self):
        rates = [1000, 200, 100, 50]
        if self.running:
            self.timer.setInterval(rates[self.update_rate.currentIndex()])

    def start_live(self):
        if not self.app.smu or not self.app.smu._connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to instrument first")
            return
        
        try:
            source_val = self.source_value.value()
            compliance = self.compliance.value()

            # Apply terminal and sense settings
            self.app.smu.set_terminal(self.terminal.upper())

            if self.source_type.currentText() == "Voltage":
                self.app.smu.set_source_voltage(source_val, compliance_current=compliance)
            else:
                self.app.smu.set_source_current(source_val, compliance_voltage=compliance)

            # Apply measurement ranges
            v_range = self.voltage_range.currentText()
            if v_range == "Auto":
                self.app.smu._write("SENS:VOLT:RANG:AUTO ON")
            else:
                range_map = {"200 mV": 0.2, "2 V": 2, "20 V": 20, "200 V": 200}
                self.app.smu._write(f"SENS:VOLT:RANG {range_map[v_range]}")
                self.app.smu._write("SENS:VOLT:RANG:AUTO OFF")

            i_range = self.current_range.currentText()
            if i_range == "Auto":
                self.app.smu._write("SENS:CURR:RANG:AUTO ON")
            else:
                range_map = {"10 nA": 10e-9, "100 nA": 100e-9, "1 µA": 1e-6, "10 µA": 10e-6, "100 µA": 100e-6, "1 mA": 1e-3, "10 mA": 10e-3, "100 mA": 100e-3, "1 A": 1}
                self.app.smu._write(f"SENS:CURR:RANG {range_map[i_range]}")
                self.app.smu._write("SENS:CURR:RANG:AUTO OFF")

            self.app.smu.output_on()
            
            self.running = True
            self.reading_count = 0
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.record_btn.setEnabled(True)  # Enable record when live starts
            
            rates = [1000, 200, 100, 50]
            self.timer.start(rates[self.update_rate.currentIndex()])
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def stop_live(self):
        self.timer.stop()
        self.running = False
        
        if self.app.smu:
            try:
                self.app.smu.output_off()
            except:
                pass
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        # Stop recording if active
        if self.recording:
            self._pause_recording()
        self.record_btn.setEnabled(False)
        self.save_record_btn.setEnabled(len(self.recorded_data) > 0)
    
    def _update_reading(self):
        if not self.app.smu:
            return
        
        try:
            voltage = None
            current = None
            
            measure = self.measure_type.currentText()
            
            if measure in ["Voltage", "Resistance", "All"]:
                self.app.smu._write("SENS:FUNC 'VOLT'")
                voltage = float(self.app.smu._query("READ?"))
            
            if measure in ["Current", "Resistance", "All"]:
                self.app.smu._write("SENS:FUNC 'CURR'")
                current = float(self.app.smu._query("READ?"))
            
            if voltage is not None:
                self.voltage_display.set_value(voltage)
            if current is not None:
                self.current_display.set_value(current)
            
            resistance = 0
            power = 0
            if voltage is not None and current is not None and abs(current) > 1e-12:
                resistance = voltage / current
                power = abs(voltage * current)
                self.resistance_display.set_value(resistance)
                self.power_display.set_value(power)
                self.last_resistance = resistance

            self.reading_count += 1
            self.readings_label.setText(f"Readings: {self.reading_count}")
            
            # Record data if recording
            if self.recording and self.record_start_time is not None:
                elapsed = time.time() - self.record_start_time
                v = voltage if voltage is not None else 0
                i = current if current is not None else 0
                self.recorded_data.append((elapsed, v, i, resistance, power))
                self._update_record_graph()
                self.record_status.setText(f"Recording: Active | Points: {len(self.recorded_data)}")
            
        except Exception as e:
            print(f"Measurement error: {e}")
    
    def _start_recording(self):
        """Start recording measurements"""
        self.recording = True
        self.record_start_time = time.time()
        self.recorded_data = []
        self.record_btn.setEnabled(False)
        self.pause_record_btn.setEnabled(True)
        self.save_record_btn.setEnabled(False)
        self.record_status.setText("Recording: Active | Points: 0")
        self.record_status.setStyleSheet("color: #e83e8c; font-weight: bold;")
        # Clear graph
        self.voltage_plot.setData([], [])
        self.current_plot.setData([], [])
        self.power_plot.setData([], [])
    
    def _pause_recording(self):
        """Pause/stop recording"""
        self.recording = False
        self.record_btn.setEnabled(True)
        self.pause_record_btn.setEnabled(False)
        self.save_record_btn.setEnabled(len(self.recorded_data) > 0)
        self.record_status.setText(f"Recording: Paused | Points: {len(self.recorded_data)}")
        self.record_status.setStyleSheet("color: #fd7e14;")
    
    def _save_recording(self):
        """Save recorded data to CSV"""
        if not self.recorded_data:
            QMessageBox.warning(self, "No Data", "No recorded data to save")
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        default_name = f"MultimeterRecording_{timestamp}.csv"
        
        file, _ = QFileDialog.getSaveFileName(
            self, "Save Recording", default_name, "CSV Files (*.csv)"
        )
        if file:
            try:
                with open(file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Time(s)", "Voltage(V)", "Current(A)", "Resistance(Ω)", "Power(W)"])
                    for row in self.recorded_data:
                        writer.writerow(row)
                QMessageBox.information(self, "Success", f"Saved {len(self.recorded_data)} points to CSV")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
    
    def _update_record_graph(self):
        """Update the recording graph with latest data"""
        if not self.recorded_data:
            return
        
        times = [d[0] for d in self.recorded_data]
        voltages = [d[1] for d in self.recorded_data]
        currents = [d[2] for d in self.recorded_data]
        powers = [d[4] for d in self.recorded_data]
        
        self.voltage_plot.setData(times, voltages)
        self.current_plot.setData(times, currents)
        self.power_plot.setData(times, powers)


class SourceSettingsWidget(QGroupBox):
    """Source settings panel with DC/Pulse, V/I selection"""
    
    def __init__(self, parent=None):
        super().__init__("Source Settings", parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Type: DC / Pulse
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        
        self.dc_btn = ToggleButton("DC")
        self.dc_btn.set_selected(True)
        self.dc_btn.clicked.connect(lambda: self._set_type("DC"))
        type_layout.addWidget(self.dc_btn)
        
        self.pulse_btn = ToggleButton("Pulse")
        self.pulse_btn.clicked.connect(lambda: self._set_type("Pulse"))
        type_layout.addWidget(self.pulse_btn)
        
        type_layout.addStretch()
        layout.addLayout(type_layout)
        
        # Function: Voltage / Current
        func_layout = QHBoxLayout()
        func_layout.addWidget(QLabel("Function:"))
        
        self.volt_btn = ToggleButton("Voltage")
        self.volt_btn.set_selected(True)
        self.volt_btn.clicked.connect(lambda: self._set_function("Voltage"))
        func_layout.addWidget(self.volt_btn)
        
        self.curr_btn = ToggleButton("Current")
        self.curr_btn.clicked.connect(lambda: self._set_function("Current"))
        func_layout.addWidget(self.curr_btn)
        
        func_layout.addStretch()
        layout.addLayout(func_layout)
        
        # Mode
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Mode:"))
        self.mode = QComboBox()
        self.mode.addItems(["Linear Sweep", "List Sweep", "Log Sweep"])
        mode_layout.addWidget(self.mode)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # Range
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("Range:"))
        self.range = QComboBox()
        self.range.addItems(["Auto", "200 mV", "2 V", "20 V", "200 V"])
        range_layout.addWidget(self.range)
        range_layout.addStretch()
        layout.addLayout(range_layout)
        
        # Limit (Compliance)
        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("Limit:"))
        self.compliance = QDoubleSpinBox()
        self.compliance.setRange(0.001, 1.0)
        self.compliance.setDecimals(4)
        self.compliance.setValue(0.1)
        self.compliance.setSuffix(" A")
        limit_layout.addWidget(self.compliance)
        limit_layout.addStretch()
        layout.addLayout(limit_layout)
        
        self.source_type = "DC"
        self.function = "Voltage"
    
    def _set_type(self, type_name):
        self.source_type = type_name
        self.dc_btn.set_selected(type_name == "DC")
        self.pulse_btn.set_selected(type_name == "Pulse")
    
    def _set_function(self, func_name):
        self.function = func_name
        self.volt_btn.set_selected(func_name == "Voltage")
        self.curr_btn.set_selected(func_name == "Current")
        
        if func_name == "Voltage":
            self.compliance.setSuffix(" A")
            self.compliance.setRange(0.001, 1.0)
            self.compliance.setValue(0.1)
            self.range.clear()
            self.range.addItems(["Auto", "200 mV", "2 V", "20 V", "200 V"])
        else:
            self.compliance.setSuffix(" V")
            self.compliance.setRange(0.1, 200)
            self.compliance.setValue(20)
            self.range.clear()
            self.range.addItems(["Auto", "10 nA", "100 nA", "1 µA", "10 µA", "100 µA", "1 mA", "10 mA", "100 mA", "1 A"])


class InstrumentSettingsWidget(QGroupBox):
    """Instrument settings: Terminal, Sense, etc."""
    
    def __init__(self, parent=None):
        super().__init__("Instrument Settings", parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Terminal: Front / Rear
        term_layout = QHBoxLayout()
        term_layout.addWidget(QLabel("Terminals:"))
        
        self.front_btn = ToggleButton("Front")
        self.front_btn.clicked.connect(lambda: self._set_terminal("Front"))
        term_layout.addWidget(self.front_btn)
        
        self.rear_btn = ToggleButton("Rear")
        self.rear_btn.set_selected(True)
        self.rear_btn.clicked.connect(lambda: self._set_terminal("Rear"))
        term_layout.addWidget(self.rear_btn)
        
        term_layout.addStretch()
        layout.addLayout(term_layout)
        
        # Sense: 2-Wire / 4-Wire
        sense_layout = QHBoxLayout()
        sense_layout.addWidget(QLabel("Sense:"))
        
        self.sense_2w = ToggleButton("2-Wire")
        self.sense_2w.clicked.connect(lambda: self._set_sense("2-Wire"))
        sense_layout.addWidget(self.sense_2w)
        
        self.sense_4w = ToggleButton("4-Wire")
        self.sense_4w.set_selected(True)
        self.sense_4w.clicked.connect(lambda: self._set_sense("4-Wire"))
        sense_layout.addWidget(self.sense_4w)
        
        sense_layout.addStretch()
        layout.addLayout(sense_layout)
        
        # High Capacitance
        hicap_layout = QHBoxLayout()
        self.high_cap = QCheckBox("High Capacitance Mode")
        hicap_layout.addWidget(self.high_cap)
        hicap_layout.addStretch()
        layout.addLayout(hicap_layout)
        
        # Output Off State
        off_layout = QHBoxLayout()
        off_layout.addWidget(QLabel("Output Off:"))
        self.output_off_mode = QComboBox()
        self.output_off_mode.addItems(["Normal", "Zero", "High-Z", "Guard"])
        off_layout.addWidget(self.output_off_mode)
        off_layout.addStretch()
        layout.addLayout(off_layout)
        
        self.terminal = "Rear"
        self.sense = "4-Wire"
    
    def _set_terminal(self, term):
        self.terminal = term
        self.front_btn.set_selected(term == "Front")
        self.rear_btn.set_selected(term == "Rear")
    
    def _set_sense(self, sense):
        self.sense = sense
        self.sense_2w.set_selected(sense == "2-Wire")
        self.sense_4w.set_selected(sense == "4-Wire")


class MeasureSettingsWidget(QGroupBox):
    """Measurement settings"""
    
    def __init__(self, parent=None):
        super().__init__("Measure Settings", parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # What to measure - row 1
        meas_layout1 = QHBoxLayout()
        self.measure_v = QCheckBox("Voltage")
        self.measure_v.setChecked(True)
        meas_layout1.addWidget(self.measure_v)
        
        self.measure_i = QCheckBox("Current")
        self.measure_i.setChecked(True)
        meas_layout1.addWidget(self.measure_i)
        
        self.measure_r = QCheckBox("Resistance")
        meas_layout1.addWidget(self.measure_r)
        
        meas_layout1.addStretch()
        layout.addLayout(meas_layout1)
        
        # What to measure - row 2
        meas_layout2 = QHBoxLayout()
        self.measure_p = QCheckBox("Power")
        meas_layout2.addWidget(self.measure_p)
        
        meas_layout2.addStretch()
        layout.addLayout(meas_layout2)
        
        # Range
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("Range:"))
        self.measure_range = QComboBox()
        self.measure_range.addItems(["Auto", "10 nA", "100 nA", "1 µA", "10 µA", "100 µA", "1 mA", "10 mA", "100 mA", "1 A"])
        range_layout.addWidget(self.measure_range)
        range_layout.addStretch()
        layout.addLayout(range_layout)
        
        # Auto Zero
        az_layout = QHBoxLayout()
        az_layout.addWidget(QLabel("Auto Zero:"))
        self.auto_zero = QComboBox()
        self.auto_zero.addItems(["On", "Off", "Once"])
        az_layout.addWidget(self.auto_zero)
        az_layout.addStretch()
        layout.addLayout(az_layout)


class TimingSettingsWidget(QGroupBox):
    """Timing settings: NPLC, delay, points, repeat"""
    
    def __init__(self, parent=None):
        super().__init__("Timing Settings", parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QFormLayout(self)
        
        # Points
        self.points = QSpinBox()
        self.points.setRange(1, 10000000)
        self.points.setValue(51)
        layout.addRow("Points:", self.points)
        
        # Repeat
        self.repeat = QSpinBox()
        self.repeat.setRange(1, 1000)
        self.repeat.setValue(1)
        layout.addRow("Repeat:", self.repeat)
        
        # Delay
        delay_row = QHBoxLayout()
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 10)
        self.delay.setDecimals(4)
        self.delay.setValue(0.05)
        self.delay.setSuffix(" s")
        delay_row.addWidget(self.delay)
        self.auto_delay_check = QCheckBox("Auto-adjust to step size")
        self.auto_delay_check.setToolTip("When ticked, delay is computed so each point takes Step Size seconds")
        self.auto_delay_check.toggled.connect(self._on_auto_delay_toggled)
        delay_row.addWidget(self.auto_delay_check)
        layout.addRow("Delay:", delay_row)

        # Step Size (dt)
        self.step_size = QDoubleSpinBox()
        self.step_size.setRange(0.001, 60)
        self.step_size.setDecimals(4)
        self.step_size.setValue(1.0)
        self.step_size.setSuffix(" s")
        self.step_size.setToolTip("Desired time between consecutive sweep points (window + delay)")
        self.step_size.valueChanged.connect(self._recompute_auto_delay)
        layout.addRow("Step Size (dt):", self.step_size)

        # NPLC
        self.nplc = QDoubleSpinBox()
        self.nplc.setRange(0.01, 10)
        self.nplc.setDecimals(2)
        self.nplc.setValue(1.0)
        self.nplc.valueChanged.connect(self._update_window)
        layout.addRow("NPLC:", self.nplc)

        # Measure window (calculated)
        self.window_label = QLabel("20 ms")
        layout.addRow("Window:", self.window_label)

    def _update_window(self):
        nplc = self.nplc.value()
        window_ms = nplc * 20  # 50Hz power line
        self.window_label.setText(f"{window_ms:.1f} ms")
        self._recompute_auto_delay()

    def _on_auto_delay_toggled(self, checked: bool):
        self.delay.setReadOnly(checked)
        self.delay.setButtonSymbols(QAbstractSpinBox.NoButtons if checked else QAbstractSpinBox.UpDownArrows)
        if checked:
            self._recompute_auto_delay()

    def _recompute_auto_delay(self):
        if not getattr(self, "auto_delay_check", None) or not self.auto_delay_check.isChecked():
            return
        window_s = self.nplc.value() * 20e-3
        new_delay = max(0.0, self.step_size.value() - window_s)
        if new_delay > self.delay.maximum():
            new_delay = self.delay.maximum()
        self.delay.blockSignals(True)
        self.delay.setValue(new_delay)
        self.delay.blockSignals(False)


class ExperimentsSidebar(QGroupBox):
    """Sidebar listing saved experiments with action buttons + notes."""

    experiment_selected = pyqtSignal(str)
    save_requested = pyqtSignal(str)
    rename_requested = pyqtSignal(str, str)
    delete_requested = pyqtSignal(str)
    new_requested = pyqtSignal(str)
    clone_requested = pyqtSignal(str, str)
    notes_changed = pyqtSignal(str)

    def __init__(self, store: ExperimentStore, parent=None):
        super().__init__("Experiments", parent)
        self.store = store
        self._current_name: Optional[str] = None
        self._dirty = False
        self._suppress_select = False
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.current_label = QLabel("(Untitled)")
        self.current_label.setStyleSheet("font-weight: bold; color: #1a1a2e;")
        layout.addWidget(self.current_label)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget, stretch=1)

        btn_grid = QGridLayout()
        btn_grid.setSpacing(4)

        load_btn = QPushButton("Load")
        load_btn.setToolTip("Load the selected experiment (also: double-click an item in the list)")
        load_btn.clicked.connect(self._on_load_clicked)
        btn_grid.addWidget(load_btn, 0, 0)

        new_btn = QPushButton("New")
        new_btn.setToolTip("Create a new experiment in the list (prompts for a name)")
        new_btn.clicked.connect(self._on_new_clicked)
        btn_grid.addWidget(new_btn, 0, 1)

        save_btn = QPushButton("Save")
        save_btn.setToolTip("Save current state to the loaded experiment (or prompt for a name if none)")
        save_btn.clicked.connect(self._on_save_clicked)
        btn_grid.addWidget(save_btn, 1, 0)

        save_as_btn = QPushButton("Save As…")
        save_as_btn.setToolTip("Save current state as a new experiment")
        save_as_btn.clicked.connect(self._on_save_as_clicked)
        btn_grid.addWidget(save_as_btn, 1, 1)

        rename_btn = QPushButton("Rename")
        rename_btn.setToolTip("Rename the loaded experiment (or name an untitled one)")
        rename_btn.clicked.connect(self._on_rename_clicked)
        btn_grid.addWidget(rename_btn, 2, 0)

        clone_btn = QPushButton("Clone")
        clone_btn.setToolTip("Duplicate the selected experiment under a new name")
        clone_btn.clicked.connect(self._on_clone_clicked)
        btn_grid.addWidget(clone_btn, 2, 1)

        delete_btn = QPushButton("Delete")
        delete_btn.setToolTip("Delete the selected experiment (data CSVs are kept)")
        delete_btn.clicked.connect(self._on_delete_clicked)
        btn_grid.addWidget(delete_btn, 3, 0, 1, 2)

        layout.addLayout(btn_grid)

        layout.addWidget(QLabel("Notes:"))
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(120)
        self.notes.setPlaceholderText("Free-text notes for this experiment…")
        self.notes.textChanged.connect(lambda: self.notes_changed.emit(self.notes.toPlainText()))
        layout.addWidget(self.notes)

    def refresh(self):
        self._suppress_select = True
        self.list_widget.clear()
        for name in self.store.names():
            self.list_widget.addItem(name)
            if name == self._current_name:
                self.list_widget.setCurrentRow(self.list_widget.count() - 1)
        self._suppress_select = False
        self._update_label()

    def set_current(self, name: Optional[str], notes: str = ""):
        self._current_name = name
        self._dirty = False
        self._suppress_select = True
        self.list_widget.clearSelection()
        if name:
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).text() == name:
                    self.list_widget.setCurrentRow(i)
                    break
        self._suppress_select = False
        self.notes.blockSignals(True)
        self.notes.setPlainText(notes or "")
        self.notes.blockSignals(False)
        self._update_label()

    def mark_dirty(self, dirty: bool = True):
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self._update_label()

    def current_name(self) -> Optional[str]:
        return self._current_name

    def is_dirty(self) -> bool:
        return self._dirty

    def _update_label(self):
        name = self._current_name or "(Untitled)"
        dot = "● " if self._dirty else ""
        self.current_label.setText(f"{dot}{name}")

    def _selected_name(self) -> Optional[str]:
        items = self.list_widget.selectedItems()
        return items[0].text() if items else None

    def _on_new_clicked(self):
        existing = set(self.store.names())
        i = 1
        while f"Experiment {i}" in existing:
            i += 1
        default = f"Experiment {i}"
        name, ok = QInputDialog.getText(self, "New Experiment",
                                         "Name:", QLineEdit.Normal, default)
        name = (name or "").strip()
        if not ok or not name:
            return
        if name in existing:
            QMessageBox.warning(self, "New", f"'{name}' is already taken.")
            return
        self.new_requested.emit(name)

    def _on_load_clicked(self):
        name = self._selected_name()
        if not name:
            QMessageBox.information(self, "Load", "Select an experiment from the list first.")
            return
        if name == self._current_name and not self._dirty:
            return
        self.experiment_selected.emit(name)

    def _on_item_double_clicked(self, item):
        if item is None:
            return
        name = item.text()
        if name == self._current_name and not self._dirty:
            return
        self.experiment_selected.emit(name)

    def _on_save_clicked(self):
        if self._current_name:
            self.save_requested.emit(self._current_name)
        else:
            self._on_save_as_clicked()

    def _on_save_as_clicked(self):
        name, ok = QInputDialog.getText(self, "Save Experiment As",
                                         "Experiment name:", QLineEdit.Normal,
                                         self._current_name or "")
        name = (name or "").strip()
        if not ok or not name:
            return
        if name in self.store.names() and name != self._current_name:
            reply = QMessageBox.question(self, "Overwrite?",
                                          f"An experiment named '{name}' already exists. Overwrite?",
                                          QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self.save_requested.emit(name)

    def _on_rename_clicked(self):
        if not self._current_name:
            self._on_save_as_clicked()
            return
        new_name, ok = QInputDialog.getText(self, "Rename Experiment",
                                             "New name:", QLineEdit.Normal,
                                             self._current_name)
        new_name = (new_name or "").strip()
        if not ok or not new_name or new_name == self._current_name:
            return
        if new_name in self.store.names():
            QMessageBox.warning(self, "Rename", f"'{new_name}' is already taken.")
            return
        self.rename_requested.emit(self._current_name, new_name)

    def _on_clone_clicked(self):
        items = self.list_widget.selectedItems()
        source = items[0].text() if items else self._current_name
        if not source:
            QMessageBox.information(self, "Clone",
                                     "Select an experiment to clone, or save the current state first.")
            return
        default = f"{source} (copy)"
        existing = set(self.store.names())
        if default in existing:
            i = 2
            while f"{source} (copy {i})" in existing:
                i += 1
            default = f"{source} (copy {i})"
        new_name, ok = QInputDialog.getText(self, "Clone Experiment",
                                             "Name for the copy:", QLineEdit.Normal,
                                             default)
        new_name = (new_name or "").strip()
        if not ok or not new_name:
            return
        if new_name in existing:
            QMessageBox.warning(self, "Clone", f"'{new_name}' is already taken.")
            return
        self.clone_requested.emit(source, new_name)

    def _on_delete_clicked(self):
        name = self._selected_name() or self._current_name
        if not name:
            QMessageBox.information(self, "Delete", "Select an experiment to delete.")
            return
        reply = QMessageBox.question(self, "Delete experiment?",
                                      f"Delete '{name}'?\n(CSV data is kept.)",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.delete_requested.emit(name)


class SweepListWidget(QGroupBox):
    """Sweep list management with table"""

    # Signal emitted when sweep list changes (with count)
    list_changed = pyqtSignal(int)
    # Signal emitted when wave generator is requested
    wave_generator_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__("Sweep Values", parent)
        self._setup_ui()
        self.sweep_values = []
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["#", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMaximumHeight(200)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                color: #1a1a2e;
                gridline-color: #d1d5db;
                font-size: 13px;
                alternate-background-color: #f9fafb;
            }
            QTableWidget::item { color: #1a1a2e; }
            QHeaderView::section {
                background-color: #f3f4f6;
                color: #1a1a2e;
                font-weight: bold;
                font-size: 13px;
                padding: 6px;
                border: 1px solid #d1d5db;
            }
        """)
        layout.addWidget(self.table)

        # Linear sweep settings (form layout so labels stack above values when narrow)
        linear_form = QFormLayout()
        linear_form.setLabelAlignment(Qt.AlignLeft)
        linear_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.start_val = QDoubleSpinBox()
        self.start_val.setRange(-200, 200)
        self.start_val.setDecimals(4)
        self.start_val.setValue(0)
        linear_form.addRow("Start:", self.start_val)

        self.stop_val = QDoubleSpinBox()
        self.stop_val.setRange(-200, 200)
        self.stop_val.setDecimals(4)
        self.stop_val.setValue(5)
        linear_form.addRow("Stop:", self.stop_val)

        self.num_points = QSpinBox()
        self.num_points.setRange(2, 10000)
        self.num_points.setValue(51)
        linear_form.addRow("Points:", self.num_points)

        layout.addLayout(linear_form)
        
        # Buttons - Row 1: Generate
        btn_layout1 = QHBoxLayout()
        
        gen_btn = QPushButton("Linear")
        gen_btn.clicked.connect(self._generate_linear)
        btn_layout1.addWidget(gen_btn)
        
        log_btn = QPushButton("Log")
        log_btn.clicked.connect(self._generate_log)
        btn_layout1.addWidget(log_btn)
        
        layout.addLayout(btn_layout1)
        
        # Buttons - Row 2: Import/Export/Clear
        btn_layout2 = QHBoxLayout()
        
        import_btn = QPushButton("Import")
        import_btn.clicked.connect(self._import_csv)
        btn_layout2.addWidget(import_btn)
        
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._export_csv)
        btn_layout2.addWidget(export_btn)
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        btn_layout2.addWidget(clear_btn)
        
        layout.addLayout(btn_layout2)
        
        # Custom Signal Design button (fills the column so it never overflows)
        wave_btn = QPushButton("Custom Signal Design")
        wave_btn.setMinimumWidth(0)
        wave_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        wave_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8; color: white;
                font-family: 'Inter'; font-size: 14px;
                font-weight: bold; padding: 8px 10px;
            }
            QPushButton:hover { background-color: #138496; }
        """)
        wave_btn.clicked.connect(self.wave_generator_requested.emit)
        layout.addWidget(wave_btn)
    
    def _generate_linear(self):
        start = self.start_val.value()
        stop = self.stop_val.value()
        points = self.num_points.value()
        
        self.sweep_values = list(np.linspace(start, stop, points))
        self._update_table()
    
    def _generate_log(self):
        start = self.start_val.value()
        stop = self.stop_val.value()
        points = self.num_points.value()
        
        if start <= 0 or stop <= 0:
            QMessageBox.warning(self, "Error", "Log sweep requires positive start and stop values")
            return
        
        self.sweep_values = list(np.logspace(np.log10(start), np.log10(stop), points))
        self._update_table()
    
    def _import_csv(self):
        file, _ = QFileDialog.getOpenFileName(self, "Import CSV", "", "CSV Files (*.csv);;All Files (*)")
        if file:
            try:
                values = []
                with open(file, 'r') as f:
                    for line in f:
                        for val in line.strip().split(','):
                            try:
                                values.append(float(val.strip()))
                            except:
                                pass
                self.sweep_values = values
                self._update_table()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to import: {e}")
    
    def _export_csv(self):
        if not self.sweep_values:
            QMessageBox.warning(self, "No Data", "No values to export")
            return
        
        file, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if file:
            with open(file, 'w') as f:
                for v in self.sweep_values:
                    f.write(f"{v}\n")
    
    def _clear(self):
        self.sweep_values = []
        self._update_table()
    
    def _update_table(self):
        self.table.setRowCount(len(self.sweep_values))
        for i, val in enumerate(self.sweep_values):
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(f"{val:.6f}"))
        # Emit signal with new count
        self.list_changed.emit(len(self.sweep_values))
    
    def get_values(self) -> List[float]:
        return self.sweep_values


class DualAxisGraph(pg.PlotWidget):
    """Graph widget with dual Y-axis support"""
    
    COLORS = {
        "Voltage": "#16a34a",
        "Current": "#d97706",
        "Resistance": "#0891b2",
        "Power": "#c026d3"
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setBackground('#ffffff')
        self.showGrid(x=True, y=True, alpha=0.3)

        # Data storage
        self.data_points: List[MeasurementPoint] = []

        # Primary axis
        self.setLabel('left', 'Current', units='A', color='#d97706')
        self.setLabel('bottom', 'Voltage', units='V', color='#1a1a2e')
        
        # Secondary axis
        self.view_box2 = pg.ViewBox()
        self.plotItem.scene().addItem(self.view_box2)
        self.plotItem.getAxis('right').linkToView(self.view_box2)
        self.view_box2.setXLink(self.plotItem)
        self.plotItem.showAxis('right')
        
        # Curves
        self.curve1 = self.plot([], [], pen=pg.mkPen('#d97706', width=2), name='Y1')
        self.curve2 = pg.PlotDataItem([], [], pen=pg.mkPen('#0891b2', width=2), name='Y2')
        self.view_box2.addItem(self.curve2)
        
        # Sync view boxes
        self.plotItem.vb.sigResized.connect(self._update_views)
        
        self.x_axis = "Voltage"
        self.y1_axis = "Current"
        self.y2_axis = "None"
        
        # Legend
        self.addLegend()
    
    def _update_views(self):
        self.view_box2.setGeometry(self.plotItem.vb.sceneBoundingRect())
        self.view_box2.linkedViewChanged(self.plotItem.vb, self.view_box2.XAxis)
    
    def set_axes(self, x: str, y1: str, y2: str):
        self.x_axis = x
        self.y1_axis = y1
        self.y2_axis = y2
        
        # Update labels
        x_unit = {"Voltage": "V", "Current": "A", "Time": "s", "Index": ""}.get(x, "")
        y1_unit = {"Voltage": "V", "Current": "A", "Resistance": "Ω", "Power": "W"}.get(y1, "")
        y2_unit = {"Voltage": "V", "Current": "A", "Resistance": "Ω", "Power": "W"}.get(y2, "")
        
        self.setLabel('bottom', x, units=x_unit)
        if y1 != "None":
            self.setLabel('left', y1, units=y1_unit, color=self.COLORS.get(y1, "#fff"))
            self.curve1.setPen(pg.mkPen(self.COLORS.get(y1, "#fff"), width=2))
        if y2 != "None":
            self.plotItem.getAxis('right').setLabel(y2, units=y2_unit, color=self.COLORS.get(y2, "#fff"))
            self.curve2.setPen(pg.mkPen(self.COLORS.get(y2, "#fff"), width=2))
            self.plotItem.showAxis('right')
        else:
            self.plotItem.hideAxis('right')
        
        self._update_plot()
    
    def add_point(self, point: MeasurementPoint):
        self.data_points.append(point)
    
    def clear_data(self):
        self.data_points = []
        self.curve1.setData([], [])
        self.curve2.setData([], [])
    
    def _get_data(self, axis: str) -> List[float]:
        data = []
        for p in self.data_points:
            if axis == "Index":
                data.append(p.index)
            elif axis == "Time":
                data.append(p.timestamp)
            elif axis == "Voltage":
                data.append(p.voltage if p.voltage is not None else 0)
            elif axis == "Current":
                data.append(p.current if p.current is not None else 0)
            elif axis == "Resistance":
                if p.resistance and abs(p.resistance) < 1e12:
                    data.append(p.resistance)
                else:
                    data.append(float('nan'))
            elif axis == "Power":
                data.append(p.power if p.power is not None else 0)
        return data
    
    def _update_plot(self):
        if not self.data_points:
            return
        
        x_data = self._get_data(self.x_axis)
        
        if self.y1_axis != "None":
            y1_data = self._get_data(self.y1_axis)
            self.curve1.setData(x_data, y1_data)
        
        if self.y2_axis != "None":
            y2_data = self._get_data(self.y2_axis)
            self.curve2.setData(x_data, y2_data)
    
    def update_live(self):
        """Call this for live updates"""
        self._update_plot()
        self.enableAutoRange()
        self.view_box2.enableAutoRange()


class DataTableWidget(QTableWidget):
    """Data table with export capability"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels(['#', 'Computer Time', 'Elapsed (s)', 'Voltage (V)', 'Current (A)', 'Resistance (Ω)', 'Power (W)'])
        
        header = self.horizontalHeader()
        for i in range(7):
            header.setSectionResizeMode(i, QHeaderView.Stretch)
        
        self.setAlternatingRowColors(True)
        self.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f9fafb;
                color: #1a1a2e;
                gridline-color: #d1d5db;
                font-size: 13px;
            }
            QTableWidget::item { color: #1a1a2e; padding: 4px; }
            QHeaderView::section {
                background-color: #f3f4f6;
                color: #1a1a2e;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 5px;
                border: 1px solid #d1d5db;
            }
        """)
    
    def add_point(self, point: MeasurementPoint):
        row = self.rowCount()
        self.insertRow(row)
        
        self.setItem(row, 0, QTableWidgetItem(str(point.index)))
        self.setItem(row, 1, QTableWidgetItem(point.computer_time))
        self.setItem(row, 2, QTableWidgetItem(f"{point.timestamp:.3f}"))
        self.setItem(row, 3, QTableWidgetItem(f"{point.voltage:.9e}" if point.voltage else ""))
        self.setItem(row, 4, QTableWidgetItem(f"{point.current:.9e}" if point.current else ""))
        self.setItem(row, 5, QTableWidgetItem(f"{point.resistance:.4e}" if point.resistance and abs(point.resistance) < 1e12 else ""))
        self.setItem(row, 6, QTableWidgetItem(f"{point.power:.6e}" if point.power else ""))
        
        self.scrollToBottom()
    
    def clear_data(self):
        self.setRowCount(0)


class ConnectionDialog(QDialog):
    """Connection dialog with simulation options"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = parent
        self.setWindowTitle("Connect to Instrument")
        self.setMinimumSize(550, 450)
        self._setup_ui()
        self._refresh()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Real instrument section
        layout.addWidget(QLabel("Connect to Real Instrument:"))
        self.resource_list = QListWidget()
        self.resource_list.setStyleSheet("font-family: 'Inter'; font-size: 15px;")
        layout.addWidget(self.resource_list)
        
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        btn_layout.addWidget(refresh_btn)
        
        connect_btn = QPushButton("Connect")
        connect_btn.setStyleSheet("background-color: #28a745; color: white; font-family: 'Inter'; font-size: 14px; font-weight: bold; padding: 10px;")
        connect_btn.clicked.connect(self._connect)
        btn_layout.addWidget(connect_btn)
        layout.addLayout(btn_layout)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #d1d5db;")
        layout.addWidget(line)
        
        # Simulation section
        layout.addWidget(QLabel("Simulation Mode:"))
        
        sim_group = QGroupBox("Simulation Settings")
        sim_layout = QVBoxLayout(sim_group)
        
        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("Resistance:"))
        self.sim_resistance = QDoubleSpinBox()
        self.sim_resistance.setRange(1, 1e9)
        self.sim_resistance.setValue(1000)
        self.sim_resistance.setSuffix(" Ω")
        res_layout.addWidget(self.sim_resistance)
        res_layout.addStretch()
        sim_layout.addLayout(res_layout)
        
        # Presets
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Presets:"))
        for val, label in [(10, "10Ω"), (100, "100Ω"), (1000, "1kΩ"), (10000, "10kΩ"), (100000, "100kΩ")]:
            btn = QPushButton(label)
            btn.setMaximumWidth(60)
            btn.clicked.connect(lambda checked, v=val: self.sim_resistance.setValue(v))
            preset_layout.addWidget(btn)
        preset_layout.addStretch()
        sim_layout.addLayout(preset_layout)
        
        layout.addWidget(sim_group)
        
        simulate_btn = QPushButton("Start Simulation")
        simulate_btn.setStyleSheet("background-color: #1a1a2e; color: #ffffff; font-family: 'Inter'; font-weight: 600; padding: 8px 20px; font-size: 14px; border-radius: 6px; border: none;")
        simulate_btn.clicked.connect(self._simulate)
        layout.addWidget(simulate_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)
    
    def _refresh(self):
        self.resource_list.clear()
        resources = Keithley2450.list_available_instruments()
        for r in resources:
            self.resource_list.addItem(r)
            if "2450" in r or "05E6" in r.upper():
                self.resource_list.item(self.resource_list.count() - 1).setSelected(True)
    
    def _connect(self):
        items = self.resource_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "Select Resource", "Please select a VISA resource")
            return
        
        try:
            self.app.connect_instrument(items[0].text())
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", str(e))
    
    def _simulate(self):
        try:
            self.app.connect_instrument(None, simulate=True, 
                                        simulation_resistance=self.sim_resistance.value())
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Simulation Error", str(e))


class SafetyDialog(QDialog):
    """Safety limits configuration dialog"""
    
    def __init__(self, parent=None, limits: SafetyLimits = None):
        super().__init__(parent)
        self.limits = limits or SafetyLimits()
        self.setWindowTitle("Safety Settings")
        self.setMinimumWidth(400)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("SAFETY LIMITS - Protect your device!"))
        layout.addWidget(QLabel("These limits prevent damage to your DUT."))
        
        form = QFormLayout()
        
        self.max_voltage = QDoubleSpinBox()
        self.max_voltage.setRange(0.1, 210)
        self.max_voltage.setValue(self.limits.max_voltage)
        self.max_voltage.setSuffix(" V")
        form.addRow("Max Voltage:", self.max_voltage)
        
        self.min_voltage = QDoubleSpinBox()
        self.min_voltage.setRange(-210, 0)
        self.min_voltage.setValue(self.limits.min_voltage)
        self.min_voltage.setSuffix(" V")
        form.addRow("Min Voltage:", self.min_voltage)
        
        self.max_current = QDoubleSpinBox()
        self.max_current.setRange(0.001, 1.05)
        self.max_current.setDecimals(4)
        self.max_current.setValue(self.limits.max_current)
        self.max_current.setSuffix(" A")
        form.addRow("Max Current:", self.max_current)
        
        self.min_current = QDoubleSpinBox()
        self.min_current.setRange(-1.05, 0)
        self.min_current.setDecimals(4)
        self.min_current.setValue(self.limits.min_current)
        self.min_current.setSuffix(" A")
        form.addRow("Min Current:", self.min_current)
        
        self.power_limit = QDoubleSpinBox()
        self.power_limit.setRange(0.1, 22)
        self.power_limit.setValue(self.limits.power_limit)
        self.power_limit.setSuffix(" W")
        form.addRow("Max Power:", self.power_limit)
        
        layout.addLayout(form)
        
        btn_layout = QHBoxLayout()
        
        ok_btn = QPushButton("Apply")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def get_limits(self) -> SafetyLimits:
        return SafetyLimits(
            max_voltage=self.max_voltage.value(),
            min_voltage=self.min_voltage.value(),
            max_current=self.max_current.value(),
            min_current=self.min_current.value(),
            power_limit=self.power_limit.value()
        )


class LicenseDialog(QDialog):
    """License agreement dialog shown on first run"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{__app_name__} - License Agreement")
        self.setMinimumSize(600, 500)
        self.setModal(True)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel(f"<h2>{__app_name__}</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        layout.addWidget(QLabel("Please read and accept the following license agreement:"))
        
        # License text
        license_text = QTextEdit()
        license_text.setReadOnly(True)
        license_text.setPlainText(self._get_license_text())
        layout.addWidget(license_text)
        
        # Accept checkbox
        self.accept_check = QCheckBox("I have read and agree to the license terms")
        layout.addWidget(self.accept_check)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.accept_btn = QPushButton("Accept")
        self.accept_btn.setEnabled(False)
        self.accept_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.accept_btn)
        
        decline_btn = QPushButton("Decline")
        decline_btn.clicked.connect(self.reject)
        btn_layout.addWidget(decline_btn)
        
        layout.addLayout(btn_layout)
        
        # Connect checkbox to enable accept button
        self.accept_check.stateChanged.connect(
            lambda state: self.accept_btn.setEnabled(state == Qt.Checked)
        )
    
    def _get_license_text(self):
        import os
        # Try to load from resource file, fall back to embedded text
        license_paths = [
            os.path.join(os.path.dirname(__file__), 'resources', 'LICENSE.txt'),
            os.path.join(os.path.dirname(__file__), 'K2450Suite', 'resources', 'LICENSE.txt'),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'K2450Suite', 'resources', 'LICENSE.txt'),
        ]
        
        for path in license_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        return f.read()
                except:
                    pass
        
        # Embedded fallback license text
        return f"""K2450 CONTROL SUITE
SOFTWARE LICENSE AGREEMENT

Copyright (c) 2026 {__author__}, {__organization__}
All Rights Reserved.

IMPORTANT - READ CAREFULLY: This End-User License Agreement ("EULA") is a legal
agreement between you ("User") and {__author__} / {__organization__} ("Author") for the use of
{__app_name__} software ("Software").

By installing, copying, or otherwise using this Software, you agree to be bound
by the terms of this Agreement. If you do not agree to the terms of this Agreement,
do not install or use the Software.

1. GRANT OF LICENSE
The Author grants you a non-exclusive, non-transferable license to use this Software
for personal, educational, and research purposes.

2. RESTRICTIONS
You may NOT:
- Distribute, sell, lease, or rent the Software without written permission
- Modify, reverse engineer, decompile, or disassemble the Software
- Remove any proprietary notices or labels on the Software
- Use the Software for commercial purposes without a commercial license

3. INTELLECTUAL PROPERTY
The Software is protected by copyright laws. The Author retains all intellectual
property rights in the Software.

4. DISCLAIMER OF WARRANTIES
THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.

5. LIMITATION OF LIABILITY
IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY.

6. SAFETY WARNING
This software controls laboratory equipment capable of generating hazardous voltages
and currents. Users must have proper training in electrical safety.

By using {__app_name__}, you acknowledge that you have read this Agreement,
understand it, and agree to be bound by its terms and conditions."""


_WAVE_UNIT_MULT = {
    "sec": 1.0, "min": 60.0, "hour": 3600.0, "ms": 1e-3, "μs": 1e-6,
    "Ω": 1.0, "kΩ": 1e3, "MΩ": 1e6, "GΩ": 1e9,
    "W": 1.0, "mW": 1e-3, "µW": 1e-6,
    "V": 1.0, "mV": 1e-3,
    "A": 1.0, "mA": 1e-3, "µA": 1e-6, "nA": 1e-9,
}


class WaveToolDialog(QDialog):
    """Custom Signal Design Tool - Creates multi-segment waveforms for I-V sweeps"""

    def __init__(self, parent=None, get_resistance_fn=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Signal Design")
        self.setMinimumSize(520, 600)
        self.resize(1050, 800)
        self.waveform_values = []
        self.time_values = []
        self.segments = []
        self._current_segment_index = -1
        self._get_resistance_fn = get_resistance_fn
        self._live_r_timer = QTimer(self)
        self._live_r_timer.setInterval(500)
        self._live_r_timer.timeout.connect(self._pull_live_resistance)
        self._setup_ui()

    def _default_segment(self):
        return {
            "wave_type": "Sine", "avg_value": 20.0, "avg_unit": "W",
            "max_value": 30.0, "max_unit": "W", "period": 240.0,
            "period_unit": "sec", "cycles": 5, "step_size": 1.0, "step_unit": "sec",
        }

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("<h2>Custom Signal Design</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # --- Global Settings ---
        global_group = QGroupBox("Global Settings")
        global_form = QFormLayout()

        res_layout = QHBoxLayout()
        self.resistance = QDoubleSpinBox()
        self.resistance.setRange(0.1, 1e9)
        self.resistance.setValue(10)
        self.resistance.setDecimals(2)
        res_layout.addWidget(self.resistance)
        self.res_unit = QComboBox()
        self.res_unit.addItems(["Ω", "kΩ"])
        res_layout.addWidget(self.res_unit)
        self.measure_r_btn = QPushButton("Measure R")
        self.measure_r_btn.setToolTip("Read current R from the multimeter and fill the field")
        self.measure_r_btn.clicked.connect(self._measure_resistance_once)
        res_layout.addWidget(self.measure_r_btn)
        self.live_r_check = QCheckBox("Live R")
        self.live_r_check.setToolTip("Continuously update R from the multimeter (must be running)")
        self.live_r_check.toggled.connect(self._toggle_live_resistance)
        res_layout.addWidget(self.live_r_check)
        global_form.addRow("Resistance (R):", res_layout)

        self.design_mode = QComboBox()
        self.design_mode.addItems(["Power (W)", "Voltage (V)", "Current (A)"])
        global_form.addRow("Design By:", self.design_mode)

        self.export_mode = QComboBox()
        self.export_mode.addItems(["Voltage (V)", "Current (A)"])
        global_form.addRow("Export As:", self.export_mode)

        global_group.setLayout(global_form)
        layout.addWidget(global_group)

        # --- Segments Section (splitter so user can resize; reorients on narrow widths) ---
        self._segments_splitter = QSplitter(Qt.Horizontal)

        seg_list_panel = QWidget()
        seg_list_layout = QVBoxLayout(seg_list_panel)
        seg_list_layout.setContentsMargins(0, 0, 0, 0)
        seg_list_label = QLabel("<b>Segments</b>")
        seg_list_layout.addWidget(seg_list_label)
        self.segment_list = QListWidget()
        self.segment_list.currentRowChanged.connect(self._on_segment_selected)
        seg_list_layout.addWidget(self.segment_list)

        seg_btn_layout = QVBoxLayout()
        seg_btn_layout.setSpacing(4)
        for text, tooltip, handler in [
            ("Add segment", "Append a new segment after the current one", self._add_segment),
            ("Duplicate segment", "Copy the current segment and insert it after", self._duplicate_segment),
            ("Remove segment", "Delete the current segment", self._remove_segment),
            ("Move up", "Swap the current segment with the one above", self._move_segment_up),
            ("Move down", "Swap the current segment with the one below", self._move_segment_down),
        ]:
            btn = QPushButton(text)
            btn.setToolTip(tooltip)
            btn.clicked.connect(handler)
            seg_btn_layout.addWidget(btn)
        seg_list_layout.addLayout(seg_btn_layout)
        self._segments_splitter.addWidget(seg_list_panel)

        # Right: segment editor
        self.seg_editor_group = QGroupBox("Segment 1")
        seg_form = QFormLayout()

        self.wave_type = QComboBox()
        self.wave_type.addItems(["Sine", "Square", "Triangle", "Sawtooth", "Square-Sine", "Sine-Square"])
        self.wave_type.currentTextChanged.connect(self._update_current_segment_label)
        seg_form.addRow("Wave Type:", self.wave_type)

        avg_layout = QHBoxLayout()
        self.avg_value = QDoubleSpinBox()
        self.avg_value.setRange(-1000, 1000)
        self.avg_value.setValue(20)
        self.avg_value.setDecimals(4)
        avg_layout.addWidget(self.avg_value)
        self.avg_unit = QComboBox()
        self.avg_unit.addItems(["W", "mW", "V", "mV", "A", "mA"])
        avg_layout.addWidget(self.avg_unit)
        seg_form.addRow("Average Value:", avg_layout)

        max_layout = QHBoxLayout()
        self.max_value = QDoubleSpinBox()
        self.max_value.setRange(-1000, 1000)
        self.max_value.setValue(30)
        self.max_value.setDecimals(4)
        max_layout.addWidget(self.max_value)
        self.max_unit = QComboBox()
        self.max_unit.addItems(["W", "mW", "V", "mV", "A", "mA"])
        max_layout.addWidget(self.max_unit)
        seg_form.addRow("Max Value:", max_layout)

        period_layout = QHBoxLayout()
        self.period = QDoubleSpinBox()
        self.period.setRange(0.001, 100000)
        self.period.setValue(240)
        self.period.setDecimals(3)
        period_layout.addWidget(self.period)
        self.period_unit = QComboBox()
        self.period_unit.addItems(["sec", "min", "hour", "ms"])
        period_layout.addWidget(self.period_unit)
        seg_form.addRow("Period:", period_layout)

        self.cycles = QSpinBox()
        self.cycles.setRange(1, 1000)
        self.cycles.setValue(5)
        seg_form.addRow("Total Cycles:", self.cycles)

        step_layout = QHBoxLayout()
        self.step_size = QDoubleSpinBox()
        self.step_size.setRange(0.0001, 1000)
        self.step_size.setValue(1)
        self.step_size.setDecimals(4)
        step_layout.addWidget(self.step_size)
        self.step_unit = QComboBox()
        self.step_unit.addItems(["sec", "ms", "μs"])
        step_layout.addWidget(self.step_unit)
        seg_form.addRow("Step Size (dt):", step_layout)

        self.seg_editor_group.setLayout(seg_form)
        self._segments_splitter.addWidget(self.seg_editor_group)
        self._segments_splitter.setSizes([220, 600])
        self._segments_splitter.setStretchFactor(0, 0)
        self._segments_splitter.setStretchFactor(1, 1)
        layout.addWidget(self._segments_splitter)

        # Preview button
        preview_btn = QPushButton("Preview Waveform")
        preview_btn.setStyleSheet("background-color: #f3f4f6; color: #1a1a2e; border: 1px solid #d1d5db; font-family: 'Inter'; font-size: 15px; padding: 12px; font-weight: bold;")
        preview_btn.clicked.connect(self._preview)
        layout.addWidget(preview_btn)

        # Info label
        self.info_label = QLabel("Configure parameters and click Preview")
        self.info_label.setStyleSheet("color: #6b7280; font-style: italic;")
        layout.addWidget(self.info_label)

        # Graph Preview
        self.preview_graph = pg.PlotWidget()
        self.preview_graph.setBackground('#ffffff')
        self.preview_graph.setLabel('left', 'Output Value', color='#1a1a2e')
        self.preview_graph.setLabel('bottom', 'Time (s)', color='#1a1a2e')
        self.preview_graph.setTitle("Waveform Preview", color='#1a1a2e', size='14pt')
        self.preview_graph.showGrid(x=True, y=True, alpha=0.3)
        self.preview_graph.setMinimumHeight(200)
        layout.addWidget(self.preview_graph)

        # Buttons
        btn_layout = QHBoxLayout()

        generate_btn = QPushButton("Generate && Import to Sweep List")
        generate_btn.setStyleSheet("background-color: #1a1a2e; color: #ffffff; font-family: 'Inter'; font-size: 15px; padding: 12px; font-weight: bold;")
        generate_btn.clicked.connect(self._generate_and_accept)
        btn_layout.addWidget(generate_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        btn_layout.addWidget(export_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        # Add first default segment
        self._add_segment()

    # --- Segment management ---

    def _save_current_segment(self):
        if self._current_segment_index < 0 or self._current_segment_index >= len(self.segments):
            return
        seg = self.segments[self._current_segment_index]
        seg["wave_type"] = self.wave_type.currentText()
        seg["avg_value"] = self.avg_value.value()
        seg["avg_unit"] = self.avg_unit.currentText()
        seg["max_value"] = self.max_value.value()
        seg["max_unit"] = self.max_unit.currentText()
        seg["period"] = self.period.value()
        seg["period_unit"] = self.period_unit.currentText()
        seg["cycles"] = self.cycles.value()
        seg["step_size"] = self.step_size.value()
        seg["step_unit"] = self.step_unit.currentText()

    def _load_segment(self, index):
        seg = self.segments[index]
        self.wave_type.setCurrentText(seg["wave_type"])
        self.avg_value.setValue(seg["avg_value"])
        self.avg_unit.setCurrentText(seg["avg_unit"])
        self.max_value.setValue(seg["max_value"])
        self.max_unit.setCurrentText(seg["max_unit"])
        self.period.setValue(seg["period"])
        self.period_unit.setCurrentText(seg["period_unit"])
        self.cycles.setValue(seg["cycles"])
        self.step_size.setValue(seg["step_size"])
        self.step_unit.setCurrentText(seg["step_unit"])
        self.seg_editor_group.setTitle(f"Segment {index + 1}")

    def _on_segment_selected(self, row):
        if row < 0:
            return
        if self._current_segment_index >= 0:
            self._save_current_segment()
        self._current_segment_index = row
        self._load_segment(row)

    def _update_segment_list(self):
        self.segment_list.blockSignals(True)
        self.segment_list.clear()
        for i, seg in enumerate(self.segments):
            self.segment_list.addItem(f"Seg {i+1}: {seg['wave_type']}")
        self.segment_list.blockSignals(False)

    def _update_current_segment_label(self, text):
        if self._current_segment_index >= 0:
            item = self.segment_list.item(self._current_segment_index)
            if item:
                item.setText(f"Seg {self._current_segment_index + 1}: {text}")

    def _add_segment(self):
        if self._current_segment_index >= 0:
            self._save_current_segment()
        self.segments.append(self._default_segment())
        self._update_segment_list()
        self.segment_list.setCurrentRow(len(self.segments) - 1)

    def _remove_segment(self):
        if len(self.segments) <= 1:
            QMessageBox.warning(self, "Warning", "Must have at least one segment.")
            return
        idx = self._current_segment_index
        self._current_segment_index = -1
        self.segments.pop(idx)
        self._update_segment_list()
        new_idx = min(idx, len(self.segments) - 1)
        self.segment_list.setCurrentRow(new_idx)

    def _move_segment_up(self):
        idx = self._current_segment_index
        if idx <= 0:
            return
        self._save_current_segment()
        self.segments[idx], self.segments[idx-1] = self.segments[idx-1], self.segments[idx]
        self._update_segment_list()
        self._current_segment_index = -1
        self.segment_list.setCurrentRow(idx - 1)

    def _move_segment_down(self):
        idx = self._current_segment_index
        if idx >= len(self.segments) - 1:
            return
        self._save_current_segment()
        self.segments[idx], self.segments[idx+1] = self.segments[idx+1], self.segments[idx]
        self._update_segment_list()
        self._current_segment_index = -1
        self.segment_list.setCurrentRow(idx + 1)

    def _apply_measured_resistance(self, r_ohms: float):
        if self.res_unit.currentText() == "kΩ":
            self.resistance.setValue(r_ohms / 1000.0)
        else:
            self.resistance.setValue(r_ohms)

    def _measure_resistance_once(self):
        if not self._get_resistance_fn:
            QMessageBox.information(self, "Measure R", "No SMU is connected.")
            return
        r = self._get_resistance_fn()
        if r is None or not (1e-6 < abs(r) < 1e12):
            QMessageBox.warning(self, "Measure R",
                                "No valid resistance reading available.\n"
                                "Turn the SMU output ON so current is flowing through the DUT, "
                                "or run the Multimeter tab, then try again.")
            return
        self._apply_measured_resistance(r)

    def _toggle_live_resistance(self, checked: bool):
        self.resistance.setReadOnly(checked)
        if checked:
            if not self._get_resistance_fn:
                QMessageBox.information(self, "Live R", "No SMU is connected.")
                self.live_r_check.setChecked(False)
                return
            self._pull_live_resistance()
            self._live_r_timer.start()
        else:
            self._live_r_timer.stop()

    def _pull_live_resistance(self):
        if not self._get_resistance_fn:
            return
        r = self._get_resistance_fn()
        if r is not None and 1e-6 < abs(r) < 1e12:
            self._apply_measured_resistance(r)

    def _duplicate_segment(self):
        import copy
        self._save_current_segment()
        new_seg = copy.deepcopy(self.segments[self._current_segment_index])
        self.segments.insert(self._current_segment_index + 1, new_seg)
        self._update_segment_list()
        self.segment_list.setCurrentRow(self._current_segment_index + 1)

    # --- Waveform calculation ---

    def _get_unit_multiplier(self, unit: str) -> float:
        return _WAVE_UNIT_MULT.get(unit, 1.0)

    def _calculate_segment_waveform(self, seg, R, mode, export_target):
        """Calculate waveform for a single segment"""
        period_sec = seg["period"] * self._get_unit_multiplier(seg["period_unit"])
        dt = seg["step_size"] * self._get_unit_multiplier(seg["step_unit"])
        cycles = seg["cycles"]

        avg = seg["avg_value"] * self._get_unit_multiplier(seg["avg_unit"])
        max_val = seg["max_value"] * self._get_unit_multiplier(seg["max_unit"])
        amplitude = max_val - avg

        t = np.arange(0, cycles * period_sec, dt)
        f = 1.0 / period_sec

        wave_type = seg["wave_type"]
        if wave_type == "Sine":
            wave = avg + amplitude * np.sin(2 * np.pi * f * t)
        elif wave_type == "Square":
            wave = avg + amplitude * np.sign(np.sin(2 * np.pi * f * t))
        elif wave_type == "Triangle":
            wave = avg + amplitude * (2 * np.abs(2 * (t * f - np.floor(t * f + 0.5))) - 1)
        elif wave_type == "Sawtooth":
            wave = avg + amplitude * (2 * (t * f - np.floor(t * f + 0.5)))
        elif wave_type == "Square-Sine":
            phase = (t * f) % 1.0
            wave = np.where(phase < 0.5,
                avg + amplitude,
                avg + amplitude * np.cos(np.pi * (phase - 0.5) / 0.5))
        elif wave_type == "Sine-Square":
            phase = (t * f) % 1.0
            wave = np.where(phase < 0.5,
                avg - amplitude * np.cos(np.pi * phase / 0.5),
                avg + amplitude)

        if mode == "Power":
            if export_target == "Voltage":
                final_values = np.sqrt(np.maximum(wave * R, 0))
            else:
                final_values = np.sqrt(np.maximum(wave / R, 0))
        elif mode == "Voltage":
            if export_target == "Voltage":
                final_values = wave
            else:
                final_values = wave / R
        elif mode == "Current":
            if export_target == "Voltage":
                final_values = wave * R
            else:
                final_values = wave

        return t, final_values

    def _calculate_all_segments(self):
        """Calculate combined waveform from all segments"""
        try:
            self._save_current_segment()

            R = self.resistance.value() * self._get_unit_multiplier(self.res_unit.currentText())
            mode = self.design_mode.currentText().split(" ")[0]
            export_target = self.export_mode.currentText().split(" ")[0]

            all_t = []
            all_values = []
            time_offset = 0.0

            for seg in self.segments:
                t, values = self._calculate_segment_waveform(seg, R, mode, export_target)
                all_t.append(t + time_offset)
                all_values.append(values)
                if len(t) > 0:
                    dt = t[1] - t[0] if len(t) > 1 else seg["step_size"] * self._get_unit_multiplier(seg["step_unit"])
                    time_offset = all_t[-1][-1] + dt

            combined_t = np.concatenate(all_t)
            combined_values = np.concatenate(all_values)

            return combined_t, combined_values
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return None

    def _preview(self):
        """Preview the combined waveform"""
        result = self._calculate_all_segments()
        if result:
            combined_t, combined_values = result
            self.waveform_values = list(combined_values)
            self.time_values = list(combined_t)
            export_unit = "V" if "Voltage" in self.export_mode.currentText() else "A"

            n_segs = len(self.segments)
            self.info_label.setText(
                f"{n_segs} segment{'s' if n_segs > 1 else ''} | "
                f"{len(combined_values)} points | "
                f"Duration: {combined_t[-1]:.2f}s | "
                f"Output: {min(combined_values):.4f} to {max(combined_values):.4f} {export_unit}"
            )
            self.info_label.setStyleSheet("color: #1a1a2e; font-weight: bold;")

            # Plot combined waveform with segment boundary markers
            self.preview_graph.clear()
            self.preview_graph.plot(self.time_values, self.waveform_values, pen=pg.mkPen('#16a34a', width=2))
            self.preview_graph.setLabel('left', f'Output ({export_unit})')

            # Add dashed vertical lines at segment boundaries
            if n_segs > 1:
                time_offset = 0.0
                for i, seg in enumerate(self.segments[:-1]):
                    period_sec = seg["period"] * self._get_unit_multiplier(seg["period_unit"])
                    dt = seg["step_size"] * self._get_unit_multiplier(seg["step_unit"])
                    seg_duration = seg["cycles"] * period_sec
                    time_offset += seg_duration
                    boundary_line = pg.InfiniteLine(pos=time_offset, angle=90,
                        pen=pg.mkPen('#ff6b6b', width=1, style=Qt.DashLine))
                    self.preview_graph.addItem(boundary_line)

    def _generate_and_accept(self):
        """Generate waveform and accept dialog"""
        self._preview()
        if self.waveform_values:
            self.accept()

    def _export_csv(self):
        """Export waveform to CSV file"""
        self._preview()
        if not self.waveform_values:
            return

        file, _ = QFileDialog.getSaveFileName(self, "Export Waveform", "", "CSV Files (*.csv)")
        if file:
            try:
                with open(file, 'w', newline='') as f:
                    writer = csv.writer(f)
                    for v in self.waveform_values:
                        writer.writerow([v])
                QMessageBox.information(self, "Success", f"Exported {len(self.waveform_values)} values to CSV")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def get_waveform_values(self) -> List[float]:
        """Return the generated waveform values"""
        return self.waveform_values

    def dump_state(self) -> dict:
        """Serialize the dialog's current global settings + segments for persistence."""
        if self._current_segment_index >= 0:
            self._save_current_segment()
        return {
            "resistance": self.resistance.value(),
            "res_unit": self.res_unit.currentText(),
            "design_mode": self.design_mode.currentText(),
            "export_mode": self.export_mode.currentText(),
            "segments": [dict(s) for s in self.segments],
            "current_segment_index": self._current_segment_index,
            "live_r_linked": self.live_r_check.isChecked(),
        }

    def load_state(self, state: dict):
        """Restore a previously-dumped state."""
        if not state:
            return
        if "resistance" in state:
            self.resistance.setValue(state["resistance"])
        if state.get("res_unit"):
            self.res_unit.setCurrentText(state["res_unit"])
        if state.get("design_mode"):
            self.design_mode.setCurrentText(state["design_mode"])
        if state.get("export_mode"):
            self.export_mode.setCurrentText(state["export_mode"])
        segs = state.get("segments")
        if segs:
            self.segments = [dict(s) for s in segs]
            self._current_segment_index = -1
            self._update_segment_list()
            target_idx = state.get("current_segment_index", 0)
            if 0 <= target_idx < len(self.segments):
                self.segment_list.setCurrentRow(target_idx)
            else:
                self.segment_list.setCurrentRow(0)
        if state.get("live_r_linked"):
            self.live_r_check.setChecked(True)

    @staticmethod
    def compute_values_from_config(config: dict, R_override: Optional[float] = None) -> List[float]:
        """Recompute the full value list from a saved dump_state config."""
        segments = config.get("segments", [])
        if not segments:
            return []
        if R_override is not None:
            R = float(R_override)
        else:
            R = (config.get("resistance", 10.0)
                 * _WAVE_UNIT_MULT.get(config.get("res_unit", "Ω"), 1.0))
        mode = config.get("design_mode", "Power (W)").split(" ")[0]
        export_target = config.get("export_mode", "Voltage (V)").split(" ")[0]

        out: List[float] = []
        for seg in segments:
            period_sec = seg["period"] * _WAVE_UNIT_MULT.get(seg["period_unit"], 1.0)
            dt = seg["step_size"] * _WAVE_UNIT_MULT.get(seg["step_unit"], 1.0)
            cycles = seg["cycles"]
            avg = seg["avg_value"] * _WAVE_UNIT_MULT.get(seg["avg_unit"], 1.0)
            max_val = seg["max_value"] * _WAVE_UNIT_MULT.get(seg["max_unit"], 1.0)
            amplitude = max_val - avg
            t = np.arange(0, cycles * period_sec, dt)
            f = 1.0 / period_sec if period_sec > 0 else 0.0
            wt = seg.get("wave_type", "Sine")
            if wt == "Sine":
                wave = avg + amplitude * np.sin(2 * np.pi * f * t)
            elif wt == "Square":
                wave = avg + amplitude * np.sign(np.sin(2 * np.pi * f * t))
            elif wt == "Triangle":
                wave = avg + amplitude * (2 * np.abs(2 * (t * f - np.floor(t * f + 0.5))) - 1)
            elif wt == "Sawtooth":
                wave = avg + amplitude * (2 * (t * f - np.floor(t * f + 0.5)))
            elif wt == "Square-Sine":
                phase = (t * f) % 1.0
                wave = np.where(phase < 0.5, avg + amplitude,
                                avg + amplitude * np.cos(np.pi * (phase - 0.5) / 0.5))
            elif wt == "Sine-Square":
                phase = (t * f) % 1.0
                wave = np.where(phase < 0.5, avg - amplitude * np.cos(np.pi * phase / 0.5),
                                avg + amplitude)
            else:
                wave = np.full_like(t, avg)
            if mode == "Power":
                final = np.sqrt(np.maximum(wave * R, 0)) if export_target == "Voltage" else np.sqrt(np.maximum(wave / R, 0))
            elif mode == "Voltage":
                final = wave if export_target == "Voltage" else wave / R
            elif mode == "Current":
                final = wave * R if export_target == "Voltage" else wave
            else:
                final = wave
            out.extend(final.tolist())
        return out

    def resizeEvent(self, event):
        super().resizeEvent(event)
        splitter = getattr(self, "_segments_splitter", None)
        if splitter is None:
            return
        target = Qt.Vertical if self.width() < 750 else Qt.Horizontal
        if splitter.orientation() != target:
            splitter.setOrientation(target)
            if target == Qt.Vertical:
                splitter.setSizes([220, 400])
            else:
                splitter.setSizes([220, max(400, self.width() - 280)])

    def closeEvent(self, event):
        self._live_r_timer.stop()
        super().closeEvent(event)


class Keithley2450App(QMainWindow):
    """Main application window with all features"""
    
    measurement_update = pyqtSignal(object)
    
    def __init__(self):
        super().__init__()
        
        self.smu: Optional[Keithley2450] = None
        self.safety_limits = SafetyLimits()
        self.measurement_data: List[MeasurementPoint] = []
        self.running = False
        self.abort_flag = False
        
        # Run tracking
        self.run_number = 0
        self.run_start_datetime = None  # When current run started
        self.auto_save_enabled = True
        self.auto_save_path = os.path.join(os.path.expanduser("~"), "Documents", "K2450_Data")

        # Experiments: named bundles of settings + sweep list + wave config + notes
        self.experiment_store = ExperimentStore()
        self._current_experiment_name: Optional[str] = None
        self._current_experiment_notes: str = ""
        self._current_wave_config: Optional[dict] = None
        self._suppress_dirty = False

        # Live CSV streaming
        self._live_csv_file = None
        self._live_csv_writer = None
        self._live_csv_path = None

        # Application settings
        self.settings = QSettings(__organization__, __app_name__)

        self.setWindowTitle(f"{__app_name__} - I-V Characterizer")
        self.setMinimumSize(560, 480)
        self.resize(1200, 800)
        
        # Check license agreement on first run
        if not self._check_license_agreement():
            sys.exit(0)
        
        self._create_menu()
        self._setup_ui()
        self._setup_signals()
    
    def _create_menu(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        export_action = QAction("Export Data...", self)
        export_action.triggered.connect(self.export_csv)
        file_menu.addAction(export_action)
        
        import_action = QAction("Import Sweep List...", self)
        import_action.triggered.connect(self._import_sweep_list)
        file_menu.addAction(import_action)
        
        file_menu.addSeparator()
        
        save_config = QAction("Save Configuration...", self)
        save_config.triggered.connect(self._save_config)
        file_menu.addAction(save_config)
        
        load_config = QAction("Load Configuration...", self)
        load_config.triggered.connect(self._load_config)
        file_menu.addAction(load_config)
        
        file_menu.addSeparator()
        
        # Auto-save settings
        self.auto_save_action = QAction("Auto-Save Enabled", self)
        self.auto_save_action.setCheckable(True)
        self.auto_save_action.setChecked(self.auto_save_enabled)
        self.auto_save_action.toggled.connect(self._toggle_auto_save)
        file_menu.addAction(self.auto_save_action)
        
        auto_save_path_action = QAction("Set Auto-Save Folder...", self)
        auto_save_path_action.triggered.connect(self._set_auto_save_path)
        file_menu.addAction(auto_save_path_action)
        
        open_save_folder = QAction("Open Auto-Save Folder", self)
        open_save_folder.triggered.connect(self._open_auto_save_folder)
        file_menu.addAction(open_save_folder)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        
        wave_tool_action = QAction("Custom Signal Design...", self)
        wave_tool_action.triggered.connect(self._show_wave_tool)
        tools_menu.addAction(wave_tool_action)
        
        # Instrument menu
        inst_menu = menubar.addMenu("Instrument")
        
        connect_action = QAction("Connect...", self)
        connect_action.triggered.connect(self._show_connection_dialog)
        inst_menu.addAction(connect_action)
        
        disconnect_action = QAction("Disconnect", self)
        disconnect_action.triggered.connect(self._disconnect)
        inst_menu.addAction(disconnect_action)
        
        inst_menu.addSeparator()
        
        reset_action = QAction("Reset", self)
        reset_action.triggered.connect(self._reset_instrument)
        inst_menu.addAction(reset_action)
        
        safety_action = QAction("Safety Settings...", self)
        safety_action.triggered.connect(self._show_safety_dialog)
        inst_menu.addAction(safety_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")

        update_action = QAction("Check for Updates…", self)
        update_action.triggered.connect(self._check_for_updates)
        help_menu.addAction(update_action)
        help_menu.addSeparator()

        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 10)
        
        # Header bar
        header = QFrame()
        header.setFixedHeight(44)
        header.setStyleSheet("""
            QFrame {
                background-color: #1a1a2e;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 5, 20, 5)

        header_title = QLabel(__app_name__)
        header_title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; font-family: 'Inter'; background: transparent;")
        header_layout.addWidget(header_title)
        header_layout.addStretch()

        version_label = QLabel(f"v{__version__} Created by {__author__} with claude code")
        version_label.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 11px; font-family: 'Inter'; background: transparent;")
        header_layout.addWidget(version_label)
        
        layout.addWidget(header)
        
        # Content area with padding
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 15, 20, 10)

        # Top toolbar
        toolbar = QHBoxLayout()

        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self._show_connection_dialog)
        toolbar.addWidget(connect_btn)
        
        self.connection_label = QLabel("Disconnected")
        self.connection_label.setStyleSheet("color: #6b7280; font-family: 'Inter'; font-weight: bold; font-size: 15px;")
        toolbar.addWidget(self.connection_label)
        
        toolbar.addStretch()
        
        self.output_btn = QPushButton("OUT: OFF")
        self.output_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff; color: #1a1a2e;
                font-family: 'Inter'; font-size: 14px; font-weight: 600;
                padding: 8px 16px; border-radius: 6px; border: 1px solid #d1d5db;
            }
            QPushButton:hover { background-color: #f3f4f6; }
        """)
        self.output_btn.clicked.connect(self._toggle_output)
        toolbar.addWidget(self.output_btn)

        self.start_btn = QPushButton("START SWEEP")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a1a2e; color: #ffffff;
                font-family: 'Inter'; font-size: 14px; font-weight: bold;
                padding: 8px 20px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #374151; }
            QPushButton:disabled { background-color: #e5e7eb; color: #9ca3af; }
        """)
        self.start_btn.clicked.connect(self.start_sweep)
        toolbar.addWidget(self.start_btn)

        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; color: #ffffff;
                font-family: 'Inter'; font-size: 14px; font-weight: bold;
                padding: 8px 20px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #b91c1c; }
            QPushButton:disabled { background-color: #e5e7eb; color: #9ca3af; }
        """)
        self.stop_btn.clicked.connect(self.stop_sweep)
        self.stop_btn.setEnabled(False)
        toolbar.addWidget(self.stop_btn)

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self.export_csv)
        toolbar.addWidget(self.export_btn)

        # Buttons that only make sense on the I-V Sweep tab
        self._sweep_only_widgets = [self.start_btn, self.stop_btn, self.export_btn]

        content_layout.addLayout(toolbar)

        # Main tabs
        tabs = QTabWidget()
        self.main_tabs = tabs
        tabs.currentChanged.connect(self._on_main_tab_changed)

        # Tab 1: Multimeter (wrapped in a scroll area so it never clips)
        self.multimeter_panel = MultimeterPanel(self)
        mm_scroll = QScrollArea()
        mm_scroll.setWidgetResizable(True)
        mm_scroll.setFrameShape(QFrame.NoFrame)
        mm_scroll.setWidget(self.multimeter_panel)
        tabs.addTab(mm_scroll, "Multimeter")

        # Tab 2: I-V Sweep
        sweep_tab = QWidget()
        sweep_outer = QVBoxLayout(sweep_tab)
        sweep_outer.setContentsMargins(0, 0, 0, 0)

        # Horizontal splitter: experiments sidebar (left) | three sub-tabs (right)
        iv_outer_splitter = QSplitter(Qt.Horizontal)

        self.experiments_sidebar = ExperimentsSidebar(self.experiment_store)
        self.experiments_sidebar.experiment_selected.connect(self._load_experiment)
        self.experiments_sidebar.save_requested.connect(self._save_experiment)
        self.experiments_sidebar.rename_requested.connect(self._rename_experiment)
        self.experiments_sidebar.delete_requested.connect(self._delete_experiment)
        self.experiments_sidebar.new_requested.connect(self._new_experiment)
        self.experiments_sidebar.clone_requested.connect(self._clone_experiment)
        self.experiments_sidebar.notes_changed.connect(self._on_notes_changed)
        iv_outer_splitter.addWidget(self.experiments_sidebar)

        # Three sub-tabs inside I-V Sweep: Settings / Sweep Values / Graph
        iv_sub_tabs = QTabWidget()

        # --- Sub-tab 1: Settings ---
        settings_panel = QWidget()
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setSpacing(10)

        self.source_settings = SourceSettingsWidget()
        settings_layout.addWidget(self.source_settings)

        self.inst_settings = InstrumentSettingsWidget()
        settings_layout.addWidget(self.inst_settings)

        self.measure_settings = MeasureSettingsWidget()
        settings_layout.addWidget(self.measure_settings)

        self.timing_settings = TimingSettingsWidget()
        settings_layout.addWidget(self.timing_settings)

        settings_layout.addStretch()

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.NoFrame)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        settings_scroll.setWidget(settings_panel)
        iv_sub_tabs.addTab(settings_scroll, "Settings")

        # --- Sub-tab 2: Sweep Values ---
        self.sweep_list = SweepListWidget()
        self.sweep_list.wave_generator_requested.connect(self._show_wave_tool)

        sweep_scroll = QScrollArea()
        sweep_scroll.setWidgetResizable(True)
        sweep_scroll.setFrameShape(QFrame.NoFrame)
        sweep_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sweep_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sweep_scroll.setWidget(self.sweep_list)
        iv_sub_tabs.addTab(sweep_scroll, "Sweep Values")

        # --- Sub-tab 3: Graph ---
        graph_tab = QWidget()
        graph_tab_layout = QVBoxLayout(graph_tab)
        graph_tab_layout.setContentsMargins(0, 0, 0, 0)

        axis_bar = QWidget()
        axis_layout = QHBoxLayout(axis_bar)
        axis_layout.setContentsMargins(0, 0, 0, 0)

        axis_layout.addWidget(QLabel("X:"))
        self.x_axis = QComboBox()
        self.x_axis.addItems(["Voltage", "Current", "Time", "Index"])
        self.x_axis.currentTextChanged.connect(self._update_graph_axes)
        axis_layout.addWidget(self.x_axis)

        axis_layout.addWidget(QLabel("Y1 (Left):"))
        self.y1_axis = QComboBox()
        self.y1_axis.addItems(["Current", "Voltage", "Resistance", "Power", "None"])
        self.y1_axis.currentTextChanged.connect(self._update_graph_axes)
        axis_layout.addWidget(self.y1_axis)

        axis_layout.addWidget(QLabel("Y2 (Right):"))
        self.y2_axis = QComboBox()
        self.y2_axis.addItems(["None", "Voltage", "Current", "Resistance", "Power"])
        self.y2_axis.currentTextChanged.connect(self._update_graph_axes)
        axis_layout.addWidget(self.y2_axis)

        axis_layout.addWidget(QLabel("Presets:"))
        for preset, (x, y1, y2) in [("I-V", ("Voltage", "Current", "None")),
                                     ("I-t", ("Time", "Current", "None")),
                                     ("V,P-t", ("Time", "Voltage", "Power")),
                                     ("I,R-t", ("Time", "Current", "Resistance"))]:
            btn = QPushButton(preset)
            btn.setMaximumWidth(80)
            btn.clicked.connect(lambda checked, x=x, y1=y1, y2=y2: self._set_graph_preset(x, y1, y2))
            axis_layout.addWidget(btn)

        axis_layout.addStretch()

        self.live_update_cb = QCheckBox("Live Update")
        self.live_update_cb.setChecked(True)
        axis_layout.addWidget(self.live_update_cb)

        graph_tab_layout.addWidget(axis_bar)

        # Graph + table share a vertical splitter so the user can decide the ratio
        graph_table_splitter = QSplitter(Qt.Vertical)

        self.graph = DualAxisGraph()
        self.graph.setMinimumSize(0, 0)
        graph_table_splitter.addWidget(self.graph)

        self.table = DataTableWidget()
        self.table.setMinimumSize(0, 0)
        graph_table_splitter.addWidget(self.table)

        graph_table_splitter.setSizes([500, 300])
        graph_table_splitter.setCollapsible(0, True)
        graph_table_splitter.setCollapsible(1, True)
        graph_tab_layout.addWidget(graph_table_splitter)

        iv_sub_tabs.addTab(graph_tab, "Graph")

        iv_outer_splitter.addWidget(iv_sub_tabs)
        iv_outer_splitter.setSizes([240, 1000])
        iv_outer_splitter.setStretchFactor(0, 0)
        iv_outer_splitter.setStretchFactor(1, 1)
        iv_outer_splitter.setCollapsible(0, True)
        iv_outer_splitter.setCollapsible(1, False)
        sweep_outer.addWidget(iv_outer_splitter)

        tabs.addTab(sweep_tab, "I-V Sweep")

        content_layout.addWidget(tabs)
        layout.addWidget(content)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        
        # Progress info label
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("font-family: 'Inter'; color: #9ca3af;")
        self.status.addPermanentWidget(self.progress_label)
        
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setFormat("%v / %m")
        self.status.addPermanentWidget(self.progress)
        self.status.showMessage("Ready")
        
        # Sweep timing tracking
        self.sweep_start_time = 0
        self.total_sweep_points = 0
    
    def _setup_signals(self):
        self.measurement_update.connect(self._on_measurement_update)
        # Connect sweep list changes to update timing points
        self.sweep_list.list_changed.connect(self._on_sweep_list_changed)
        self._wire_dirty_tracking()
        self._on_main_tab_changed(self.main_tabs.currentIndex())

    def _on_main_tab_changed(self, index: int):
        is_sweep_tab = self.main_tabs.tabText(index) == "I-V Sweep"
        for w in self._sweep_only_widgets:
            w.setVisible(is_sweep_tab)

    def _on_sweep_list_changed(self, count: int):
        """Update timing points when sweep list changes"""
        if count > 0:
            self.timing_settings.points.setValue(count)
        self._mark_dirty()

    # === Experiments ===

    def _wire_dirty_tracking(self):
        ss = self.source_settings
        ms = self.measure_settings
        ts = self.timing_settings
        slist = self.sweep_list
        inst = self.inst_settings

        def hook(widget, signal_name):
            sig = getattr(widget, signal_name, None)
            if sig is not None:
                sig.connect(self._mark_dirty)

        for cb in [ss.mode, ss.range, ms.measure_range, ms.auto_zero,
                   inst.output_off_mode]:
            hook(cb, "currentTextChanged")
        for sb in [ss.compliance, ts.points, ts.repeat, ts.delay, ts.step_size, ts.nplc,
                   slist.start_val, slist.stop_val, slist.num_points]:
            hook(sb, "valueChanged")
        hook(ms.measure_v, "toggled")
        hook(ms.measure_i, "toggled")
        hook(ms.measure_r, "toggled")
        hook(ms.measure_p, "toggled")
        hook(ts.auto_delay_check, "toggled")
        hook(inst.high_cap, "toggled")

    def _mark_dirty(self, *args):
        if self._suppress_dirty:
            return
        self.experiments_sidebar.mark_dirty(True)

    def _capture_state(self) -> dict:
        ss = self.source_settings
        ms = self.measure_settings
        ts = self.timing_settings
        slist = self.sweep_list
        inst = self.inst_settings
        return {
            "source": {
                "type": ss.source_type,
                "function": ss.function,
                "mode": ss.mode.currentText(),
                "compliance": ss.compliance.value(),
            },
            "instrument": {
                "terminal": inst.terminal,
                "sense": inst.sense,
                "high_cap": inst.high_cap.isChecked(),
                "output_off": inst.output_off_mode.currentText(),
            },
            "measure": {
                "v": ms.measure_v.isChecked(),
                "i": ms.measure_i.isChecked(),
                "r": ms.measure_r.isChecked(),
                "p": ms.measure_p.isChecked(),
                "auto_zero": ms.auto_zero.currentText(),
            },
            "timing": {
                "points": ts.points.value(),
                "repeat": ts.repeat.value(),
                "delay": ts.delay.value(),
                "step_size": ts.step_size.value(),
                "auto_delay": ts.auto_delay_check.isChecked(),
                "nplc": ts.nplc.value(),
            },
            "sweep": {
                "values": list(slist.sweep_values),
                "start": slist.start_val.value(),
                "stop": slist.stop_val.value(),
                "num_points": slist.num_points.value(),
            },
            "wave_config": self._current_wave_config,
            "notes": self._current_experiment_notes,
        }

    def _apply_state(self, exp: dict):
        self._suppress_dirty = True
        try:
            ss = self.source_settings
            ms = self.measure_settings
            ts = self.timing_settings
            slist = self.sweep_list
            inst = self.inst_settings

            src = exp.get("source", {})
            if src.get("type"):
                ss._set_type(src["type"])
            if src.get("function"):
                ss._set_function(src["function"])
            if src.get("mode"):
                ss.mode.setCurrentText(src["mode"])
            if "compliance" in src:
                ss.compliance.setValue(src["compliance"])

            instd = exp.get("instrument", {})
            if instd.get("terminal"):
                inst._set_terminal(instd["terminal"])
            if instd.get("sense"):
                inst._set_sense(instd["sense"])
            if "high_cap" in instd:
                inst.high_cap.setChecked(bool(instd["high_cap"]))
            if instd.get("output_off"):
                inst.output_off_mode.setCurrentText(instd["output_off"])

            md = exp.get("measure", {})
            ms.measure_v.setChecked(bool(md.get("v", True)))
            ms.measure_i.setChecked(bool(md.get("i", True)))
            ms.measure_r.setChecked(bool(md.get("r", False)))
            ms.measure_p.setChecked(bool(md.get("p", False)))
            if md.get("auto_zero"):
                ms.auto_zero.setCurrentText(md["auto_zero"])

            td = exp.get("timing", {})
            if "points" in td: ts.points.setValue(td["points"])
            if "repeat" in td: ts.repeat.setValue(td["repeat"])
            if "delay" in td: ts.delay.setValue(td["delay"])
            if "step_size" in td: ts.step_size.setValue(td["step_size"])
            if "nplc" in td: ts.nplc.setValue(td["nplc"])
            if "auto_delay" in td: ts.auto_delay_check.setChecked(bool(td["auto_delay"]))

            sd = exp.get("sweep", {})
            if "start" in sd: slist.start_val.setValue(sd["start"])
            if "stop" in sd: slist.stop_val.setValue(sd["stop"])
            if "num_points" in sd: slist.num_points.setValue(sd["num_points"])
            if "values" in sd:
                slist.sweep_values = list(sd["values"])
                slist._update_table()

            self._current_wave_config = exp.get("wave_config")
            if getattr(self, "_wave_dialog", None) is not None and self._current_wave_config:
                self._wave_dialog.load_state(self._current_wave_config)
        finally:
            self._suppress_dirty = False

    def _load_experiment(self, name: str):
        if self.experiments_sidebar.is_dirty():
            reply = QMessageBox.question(self, "Unsaved changes",
                                          "Discard unsaved changes to the current experiment?",
                                          QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                self.experiments_sidebar.set_current(self._current_experiment_name,
                                                     self._current_experiment_notes)
                return
        exp = self.experiment_store.get(name)
        if not exp:
            return
        self._apply_state(exp)
        self._current_experiment_name = name
        self._current_experiment_notes = exp.get("notes", "")
        self.experiments_sidebar.set_current(name, self._current_experiment_notes)
        self.status.showMessage(f"Loaded experiment: {name}")

    def _save_experiment(self, name: str):
        payload = self._capture_state()
        payload["notes"] = self._current_experiment_notes
        self.experiment_store.save(name, payload)
        self._current_experiment_name = name
        self.experiments_sidebar.refresh()
        self.experiments_sidebar.set_current(name, self._current_experiment_notes)
        self.status.showMessage(f"Saved experiment: {name}")

    def _rename_experiment(self, old: str, new: str):
        self.experiment_store.rename(old, new)
        self._current_experiment_name = new
        self.experiments_sidebar.refresh()
        self.experiments_sidebar.set_current(new, self._current_experiment_notes)
        self.status.showMessage(f"Renamed: {old} → {new}")

    def _delete_experiment(self, name: str):
        self.experiment_store.delete(name)
        if self._current_experiment_name == name:
            self._current_experiment_name = None
            self._current_experiment_notes = ""
        self.experiments_sidebar.refresh()
        self.experiments_sidebar.set_current(self._current_experiment_name,
                                              self._current_experiment_notes)
        self.status.showMessage(f"Deleted experiment: {name}")

    def _new_experiment(self, name: str):
        self._current_experiment_notes = ""
        self._save_experiment(name)

    def _clone_experiment(self, source: str, new_name: str):
        record = self.experiment_store.get(source)
        if record is None:
            record = self._capture_state()
            record["notes"] = self._current_experiment_notes
        else:
            record = dict(record)
        for k in ("name", "created_at", "modified_at"):
            record.pop(k, None)
        self.experiment_store.save(new_name, record)
        self.experiments_sidebar.refresh()
        self.experiments_sidebar.set_current(self._current_experiment_name,
                                              self._current_experiment_notes)
        self.status.showMessage(f"Cloned '{source}' → '{new_name}'")

    def _on_notes_changed(self, text: str):
        self._current_experiment_notes = text
        self._mark_dirty()
    
    def _set_graph_preset(self, x, y1, y2):
        self.x_axis.setCurrentText(x)
        self.y1_axis.setCurrentText(y1)
        self.y2_axis.setCurrentText(y2)
    
    def _update_graph_axes(self):
        self.graph.set_axes(
            self.x_axis.currentText(),
            self.y1_axis.currentText(),
            self.y2_axis.currentText()
        )
    
    def _show_connection_dialog(self):
        dialog = ConnectionDialog(self)
        dialog.exec_()
    
    def _disconnect(self):
        if self.smu:
            self.smu.disconnect()
            self.smu = None
        self.connection_label.setText("Disconnected")
        self.connection_label.setStyleSheet("color: #6b7280; font-weight: bold; font-size: 15px;")
        self._update_output_button()
        self.status.showMessage("Disconnected")
    
    def _reset_instrument(self):
        if self.smu:
            self.smu.reset()
            self._update_output_button()
            self.status.showMessage("Instrument reset")

    def _toggle_output(self):
        """Toggle the SMU output on/off."""
        if not self.smu or not getattr(self.smu, "_connected", False):
            QMessageBox.warning(self, "Not Connected", "Please connect to instrument first")
            return
        try:
            if self.smu.output_enabled():
                self.smu.output_off()
            else:
                self.smu.output_on()
            self._update_output_button()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _update_output_button(self):
        """Update OUT button text/style based on instrument state."""
        if not getattr(self, "output_btn", None):
            return
        on = False
        try:
            on = bool(self.smu and getattr(self.smu, "_connected", False) and self.smu.output_enabled())
        except Exception:
            on = False
        if on:
            self.output_btn.setText("OUT: ON")
            self.output_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1a1a2e; color: #ffffff;
                    font-family: 'Inter'; font-size: 14px; font-weight: 600;
                    padding: 8px 16px; border-radius: 6px; border: none;
                }
                QPushButton:hover { background-color: #374151; }
            """)
        else:
            self.output_btn.setText("OUT: OFF")
            self.output_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff; color: #1a1a2e;
                    font-family: 'Inter'; font-size: 14px; font-weight: 600;
                    padding: 8px 16px; border-radius: 6px; border: 1px solid #d1d5db;
                }
                QPushButton:hover { background-color: #f3f4f6; }
            """)
    
    def _show_safety_dialog(self):
        dialog = SafetyDialog(self, self.safety_limits)
        if dialog.exec_() == QDialog.Accepted:
            self.safety_limits = dialog.get_limits()
            self.status.showMessage(f"Safety limits updated: ±{self.safety_limits.max_voltage}V, ±{self.safety_limits.max_current}A")
    
    def _check_license_agreement(self) -> bool:
        """Check if license was accepted, show dialog if not"""
        license_accepted = self.settings.value("license_accepted", False, type=bool)
        license_version = self.settings.value("license_version", "", type=str)
        
        # Check if license was accepted for current version
        if license_accepted and license_version == __version__:
            return True
        
        # Show license dialog
        dialog = LicenseDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.settings.setValue("license_accepted", True)
            self.settings.setValue("license_version", __version__)
            return True
        
        return False
    
    def _check_for_updates(self):
        from updater import check_for_updates
        check_for_updates(__version__, self)

    def _show_about(self):
        about_text = f"""
        <h2>{__app_name__}</h2>
        <p><b>Version:</b> {__version__}</p>
        <p><b>Author:</b> {__author__}</p>
        <p><b>Organization:</b> {__organization__}</p>
        <p>{__copyright__}</p>
        <hr>
        <p>Professional Keithley 2450 SMU Control and I-V Characterization Software</p>
        <p><b>Features:</b></p>
        <ul>
        <li>Live multimeter mode with digital displays</li>
        <li>I-V sweep characterization (Linear, List, Log)</li>
        <li>DC/Pulse mode, Front/Rear terminals</li>
        <li>2-Wire/4-Wire sensing</li>
        <li>Dual Y-axis graphing with presets</li>
        <li>Full safety protection</li>
        <li>Configuration save/load</li>
        </ul>
        <hr>
        <p><small>Built with PyQt5 + pyqtgraph</small></p>
        """
        QMessageBox.about(self, f"About {__app_name__}", about_text)
    
    def _toggle_auto_save(self, enabled):
        """Toggle auto-save on/off"""
        self.auto_save_enabled = enabled
        self.status.showMessage(f"Auto-save {'enabled' if enabled else 'disabled'}")
    
    def _set_auto_save_path(self):
        """Set the auto-save folder path"""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Auto-Save Folder", 
            self.auto_save_path
        )
        if folder:
            self.auto_save_path = folder
            self.status.showMessage(f"Auto-save folder: {folder}")
    
    def _open_auto_save_folder(self):
        """Open the auto-save folder in file explorer"""
        if not os.path.exists(self.auto_save_path):
            os.makedirs(self.auto_save_path, exist_ok=True)
        if sys.platform == 'darwin':
            os.system(f'open "{self.auto_save_path}"')
        elif sys.platform == 'win32':
            os.startfile(self.auto_save_path)
        else:
            os.system(f'xdg-open "{self.auto_save_path}"')
    
    def _oneshot_resistance(self) -> Optional[float]:
        if not self.smu or not getattr(self.smu, "_connected", False):
            return None
        try:
            if not self.smu.output_enabled():
                return None
            v = self.smu.measure_voltage()
            i = self.smu.measure_current()
            if v is None or i is None or abs(i) < 1e-12:
                return None
            return v / i
        except Exception:
            return None

    def _get_live_resistance(self) -> Optional[float]:
        panel = getattr(self, "multimeter_panel", None)
        if panel is not None and getattr(panel, "running", False) and panel.last_resistance is not None:
            return panel.last_resistance
        r = self._oneshot_resistance()
        if r is not None:
            return r
        return panel.last_resistance if panel is not None else None

    def _show_wave_tool(self):
        """Show the Custom Signal Design tool dialog"""
        if getattr(self, "_wave_dialog", None) is None:
            self._wave_dialog = WaveToolDialog(self, get_resistance_fn=self._get_live_resistance)
            if self._current_wave_config:
                self._wave_dialog.load_state(self._current_wave_config)
        dialog = self._wave_dialog
        if dialog.exec_() == QDialog.Accepted:
            wave_values = dialog.get_waveform_values()
            if wave_values:
                self.sweep_list.sweep_values = wave_values
                self.sweep_list._update_table()
                self.status.showMessage(f"Imported {len(wave_values)} points from Custom Signal Design")
        # Remember the dialog state so we can persist it with the experiment
        self._current_wave_config = dialog.dump_state()
        self._mark_dirty()
    
    def _import_sweep_list(self):
        self.sweep_list._import_csv()
    
    def _save_config(self):
        file, _ = QFileDialog.getSaveFileName(self, "Save Configuration", "", "JSON Files (*.json)")
        if file:
            config = {
                "source": {
                    "type": self.source_settings.source_type,
                    "function": self.source_settings.function,
                    "mode": self.source_settings.mode.currentText(),
                    "compliance": self.source_settings.compliance.value()
                },
                "instrument": {
                    "terminal": self.inst_settings.terminal,
                    "sense": self.inst_settings.sense,
                    "high_cap": self.inst_settings.high_cap.isChecked(),
                    "output_off": self.inst_settings.output_off_mode.currentText()
                },
                "timing": {
                    "points": self.timing_settings.points.value(),
                    "repeat": self.timing_settings.repeat.value(),
                    "delay": self.timing_settings.delay.value(),
                    "nplc": self.timing_settings.nplc.value()
                },
                "safety": {
                    "max_voltage": self.safety_limits.max_voltage,
                    "min_voltage": self.safety_limits.min_voltage,
                    "max_current": self.safety_limits.max_current,
                    "min_current": self.safety_limits.min_current,
                    "power_limit": self.safety_limits.power_limit
                }
            }
            with open(file, 'w') as f:
                json.dump(config, f, indent=2)
            self.status.showMessage(f"Configuration saved to {file}")
    
    def _load_config(self):
        file, _ = QFileDialog.getOpenFileName(self, "Load Configuration", "", "JSON Files (*.json)")
        if file:
            with open(file, 'r') as f:
                config = json.load(f)
            
            if "source" in config:
                self.source_settings._set_type(config["source"].get("type", "DC"))
                self.source_settings._set_function(config["source"].get("function", "Voltage"))
                self.source_settings.mode.setCurrentText(config["source"].get("mode", "List Sweep"))
                self.source_settings.compliance.setValue(config["source"].get("compliance", 0.1))
            
            if "instrument" in config:
                self.inst_settings._set_terminal(config["instrument"].get("terminal", "Rear"))
                self.inst_settings._set_sense(config["instrument"].get("sense", "4-Wire"))
                self.inst_settings.high_cap.setChecked(config["instrument"].get("high_cap", False))
                self.inst_settings.output_off_mode.setCurrentText(config["instrument"].get("output_off", "Normal"))
            
            if "timing" in config:
                self.timing_settings.points.setValue(config["timing"].get("points", 51))
                self.timing_settings.repeat.setValue(config["timing"].get("repeat", 1))
                self.timing_settings.delay.setValue(config["timing"].get("delay", 0.05))
                self.timing_settings.nplc.setValue(config["timing"].get("nplc", 1.0))
            
            if "safety" in config:
                self.safety_limits = SafetyLimits(
                    max_voltage=config["safety"].get("max_voltage", 200),
                    min_voltage=config["safety"].get("min_voltage", -200),
                    max_current=config["safety"].get("max_current", 1.0),
                    min_current=config["safety"].get("min_current", -1.0),
                    power_limit=config["safety"].get("power_limit", 22)
                )
            
            self.status.showMessage(f"Configuration loaded from {file}")
    
    def connect_instrument(self, resource: Optional[str], simulate: bool = False,
                          simulation_resistance: float = 1000.0):
        self.smu = Keithley2450(
            resource_name=resource,
            safety_limits=self.safety_limits,
            simulate=simulate,
            simulation_resistance=simulation_resistance
        )
        self.smu.connect()
        
        if simulate:
            res_str = f"{simulation_resistance:.0f}Ω" if simulation_resistance < 1000 else f"{simulation_resistance/1000:.0f}kΩ"
            self.connection_label.setText(f"SIM ({res_str})")
            self.connection_label.setStyleSheet("color: #6b7280; font-weight: bold;")
        else:
            self.connection_label.setText("Connected")
            self.connection_label.setStyleSheet("color: #16a34a; font-weight: bold;")

        self._update_output_button()
        self.status.showMessage("Connected to instrument")
    
    def start_sweep(self):
        if not self.smu:
            QMessageBox.warning(self, "Not Connected", "Please connect to instrument first")
            return
        
        # Get sweep values
        mode = self.source_settings.mode.currentText()
        
        if mode == "List Sweep":
            # If the list came from a Custom Signal Design with Live R linked,
            # re-derive the values now using the current resistance.
            if (self._current_wave_config
                    and self._current_wave_config.get("live_r_linked")):
                r = self._get_live_resistance()
                if r is not None and 1e-6 < abs(r) < 1e12:
                    new_values = WaveToolDialog.compute_values_from_config(
                        self._current_wave_config, r
                    )
                    if new_values:
                        self.sweep_list.sweep_values = new_values
                        self.sweep_list._update_table()
                        self.status.showMessage(
                            f"Wave list re-derived with live R = {r:.2f} Ω"
                        )
                else:
                    QMessageBox.warning(
                        self,
                        "Live R unavailable",
                        "Live R was linked to the Custom Signal Design but no "
                        "valid R reading is available right now.\n\n"
                        "Turn the SMU output ON, or run the Multimeter tab, "
                        "and start the sweep again. Falling back to the "
                        "values already in the sweep list for this run."
                    )
            sweep_values = self.sweep_list.get_values()
            if not sweep_values:
                QMessageBox.warning(self, "No Values", "No sweep values defined. Generate or import a list.")
                return
        elif mode == "Linear Sweep":
            start = self.sweep_list.start_val.value()
            stop = self.sweep_list.stop_val.value()
            points = self.sweep_list.num_points.value()
            sweep_values = list(np.linspace(start, stop, points))
        elif mode == "Log Sweep":
            start = self.sweep_list.start_val.value()
            stop = self.sweep_list.stop_val.value()
            points = self.sweep_list.num_points.value()
            if start <= 0 or stop <= 0:
                QMessageBox.warning(self, "Error", "Log sweep requires positive values")
                return
            sweep_values = list(np.logspace(np.log10(start), np.log10(stop), points))
        else:
            sweep_values = [self.sweep_list.start_val.value()]
        
        # Safety validation
        function = self.source_settings.function
        compliance = self.source_settings.compliance.value()
        
        try:
            if function == "Voltage":
                for i, v in enumerate(sweep_values):
                    if not (self.safety_limits.min_voltage <= v <= self.safety_limits.max_voltage):
                        raise ValueError(f"Point {i+1}: Voltage {v}V outside safety limits")
                    if abs(v * compliance) > self.safety_limits.power_limit:
                        raise ValueError(f"Point {i+1}: Power {abs(v*compliance):.1f}W exceeds {self.safety_limits.power_limit}W limit")
            else:
                for i, c in enumerate(sweep_values):
                    if not (self.safety_limits.min_current <= c <= self.safety_limits.max_current):
                        raise ValueError(f"Point {i+1}: Current {c}A outside safety limits")
        except ValueError as e:
            QMessageBox.critical(self, "Safety Error", str(e))
            return
        
        # Clear previous data
        self.measurement_data.clear()
        self.graph.clear_data()
        self.table.clear_data()
        
        # Start sweep
        self.running = True
        self.abort_flag = False
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        total = len(sweep_values) * self.timing_settings.repeat.value()
        self.total_sweep_points = total
        self.sweep_start_time = time.time()
        self.run_number += 1
        self.run_start_datetime = datetime.now()
        self.progress.setMaximum(total)
        self.progress.setValue(0)
        self.progress_label.setText(f"0 / {total} | Est: --:--")

        # Open live CSV file for streaming
        try:
            save_dir = self._experiment_save_dir()
            os.makedirs(save_dir, exist_ok=True)
            filename = self._generate_filename()
            self._live_csv_path = os.path.join(save_dir, filename)
            self._live_csv_file = open(self._live_csv_path, 'w', newline='')
            self._live_csv_writer = csv.writer(self._live_csv_file)
            for row in self._build_csv_metadata_rows(sweep_values):
                self._live_csv_writer.writerow(row)
            self._live_csv_writer.writerow(['Index', 'Computer_Time', 'Elapsed(s)', 'Voltage(V)', 'Current(A)', 'Resistance(Ohm)', 'Power(W)'])
            self._live_csv_file.flush()
            self.status.showMessage(f"Saving to: {filename}")
        except Exception as e:
            print(f"Live CSV open error: {e}")
            self._live_csv_file = None
            self._live_csv_writer = None

        thread = threading.Thread(target=self._run_sweep, args=(sweep_values,))
        thread.daemon = True
        thread.start()
    
    def _run_sweep(self, sweep_values: List[float]):
        try:
            function = self.source_settings.function
            compliance = self.source_settings.compliance.value()
            delay = self.timing_settings.delay.value()
            nplc = self.timing_settings.nplc.value()
            repeat = self.timing_settings.repeat.value()
            auto_step = self.timing_settings.auto_delay_check.isChecked()
            step_size = self.timing_settings.step_size.value()

            # Configure
            if function == "Voltage":
                self.smu.set_source_voltage(sweep_values[0], compliance_current=compliance)
            else:
                self.smu.set_source_current(sweep_values[0], compliance_voltage=compliance)
            
            self.smu._write(f"SENS:CURR:NPLC {nplc}")
            self.smu._write(f"SENS:VOLT:NPLC {nplc}")
            
            # Apply instrument settings
            terminal = self.inst_settings.terminal
            self.smu.set_terminal(terminal.upper())
            
            sense = self.inst_settings.sense
            if sense == "4-Wire":
                self.smu._write("SENS:CURR:RSEN ON")
                self.smu._write("SENS:VOLT:RSEN ON")
            else:
                self.smu._write("SENS:CURR:RSEN OFF")
                self.smu._write("SENS:VOLT:RSEN OFF")
            
            # High capacitance mode
            if self.inst_settings.high_cap.isChecked():
                self.smu._write("SOUR:VOLT:HCAP ON")
            else:
                self.smu._write("SOUR:VOLT:HCAP OFF")
            
            # Auto Zero
            az_mode = self.measure_settings.auto_zero.currentText()
            az_map = {"On": "ON", "Off": "OFF", "Once": "ONCE"}
            self.smu._write(f"SENS:AZER {az_map.get(az_mode, 'ON')}")
            
            self.smu.output_on()
            
            point_num = 0
            start_time = time.time()
            
            for rep in range(repeat):
                if self.abort_flag:
                    break
                
                for source_val in sweep_values:
                    if self.abort_flag:
                        break

                    point_num += 1

                    if auto_step:
                        target_offset = (point_num - 1) * step_size
                        wait = target_offset - (time.time() - start_time)
                        if wait > 0:
                            time.sleep(wait)

                    # Set source (with safety)
                    if function == "Voltage":
                        self.smu.set_voltage(source_val)
                    else:
                        self.smu.set_current(source_val)

                    # Settle the SMU before measuring. Without this the DAC
                    # and any range/auto-zero transients leak into V/I and
                    # produce garbage values (incl. negative R at boundaries).
                    time.sleep(delay)

                    # Simulate NPLC integration time + bus overhead in sim
                    # mode. In auto_step mode the tick alignment already
                    # paces the loop, so we don't double-count it there.
                    if not auto_step and self.smu.simulate:
                        nplc_time = nplc * 0.020
                        overhead = 0.060
                        time.sleep(nplc_time + overhead)

                    elapsed = time.time() - start_time
                    
                    # Measure
                    voltage = None
                    current = None
                    resistance = None
                    power = None
                    
                    if self.measure_settings.measure_v.isChecked():
                        self.smu._write("SENS:FUNC 'VOLT'")
                        voltage = float(self.smu._query("READ?"))
                    
                    if self.measure_settings.measure_i.isChecked():
                        self.smu._write("SENS:FUNC 'CURR'")
                        current = float(self.smu._query("READ?"))
                    
                    if self.measure_settings.measure_r.isChecked() and voltage and current:
                        if abs(current) > 1e-12:
                            resistance = voltage / current
                    
                    if self.measure_settings.measure_p.isChecked() and voltage and current:
                        power = abs(voltage * current)
                    
                    # Get absolute computer time for this measurement
                    computer_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    
                    point = MeasurementPoint(
                        index=point_num,
                        timestamp=elapsed,
                        source_value=source_val,
                        computer_time=computer_time,
                        voltage=voltage,
                        current=current,
                        resistance=resistance,
                        power=power
                    )
                    self.measurement_data.append(point)
                    
                    self.measurement_update.emit(point)
            
        except Exception as e:
            print(f"Sweep error: {e}")
        
        finally:
            self.running = False
            if self.smu:
                self.smu.output_off()
    
    def _on_measurement_update(self, point: MeasurementPoint):
        self.table.add_point(point)
        self.graph.add_point(point)
        
        if self.live_update_cb.isChecked():
            self.graph.update_live()
        
        self.progress.setValue(point.index)
        
        # Calculate remaining time estimate
        elapsed = time.time() - self.sweep_start_time
        elapsed_str = self._fmt_duration(elapsed)
        if point.index > 0 and self.total_sweep_points > point.index:
            time_per_point = elapsed / point.index
            remaining_points = self.total_sweep_points - point.index
            remaining_sec = remaining_points * time_per_point
            eta_str = self._fmt_duration(remaining_sec)
            finish_str = (datetime.now() + timedelta(seconds=remaining_sec)).strftime("%H:%M:%S")
            self.progress_label.setText(
                f"{point.index} / {self.total_sweep_points}  ·  {elapsed_str} elapsed  ·  "
                f"{eta_str} left  ·  finish {finish_str}"
            )
        else:
            self.progress_label.setText(
                f"{point.index} / {self.total_sweep_points}  ·  {elapsed_str} elapsed"
            )
        
        v_str = f"{point.voltage:.6f}V" if point.voltage else ""
        i_str = f"{point.current:.4e}A" if point.current else ""
        self.status.showMessage(f"Point {point.index}: {point.source_value:.4f} → {v_str} {i_str}")

        # Write row to live CSV
        if self._live_csv_writer:
            try:
                self._live_csv_writer.writerow([
                    point.index,
                    point.computer_time,
                    f"{point.timestamp:.6f}",
                    f"{point.voltage:.9e}" if point.voltage else "",
                    f"{point.current:.9e}" if point.current else "",
                    f"{point.resistance:.9e}" if point.resistance else "",
                    f"{point.power:.9e}" if point.power else ""
                ])
                self._live_csv_file.flush()
            except Exception as e:
                print(f"Live CSV write error: {e}")

        if not self.running:
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.graph.update_live()  # Final update
            total_time = time.time() - self.sweep_start_time
            self.progress_label.setText(
                f"Done: {self.total_sweep_points} pts in {self._fmt_duration(total_time)}"
            )
            self.status.showMessage("Sweep completed")
            
            # Close live CSV file
            if self._live_csv_file:
                try:
                    self._live_csv_file.close()
                except Exception:
                    pass
                filename = os.path.basename(self._live_csv_path) if self._live_csv_path else "unknown"
                self.status.showMessage(f"Saved: {filename} ({len(self.measurement_data)} points)")
                self._live_csv_file = None
                self._live_csv_writer = None
                self._live_csv_path = None
            elif self.auto_save_enabled and self.measurement_data:
                self._auto_save_csv()
    
    def stop_sweep(self):
        self.abort_flag = True
        if self.smu:
            self.smu.output_off()
        self.status.showMessage("Stopping...")
    
    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        s = max(0, int(seconds))
        h, rem = divmod(s, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _build_csv_metadata_rows(self, sweep_values=None) -> List[List[str]]:
        """Build the metadata header rows written at the top of every saved sweep CSV."""
        ss = self.source_settings
        inst = self.inst_settings
        ms = self.measure_settings
        ts = self.timing_settings
        rows: List[List[str]] = []
        rows.append([f"# Run {self.run_number}"])
        if self.run_start_datetime:
            rows.append([f"# Started: {self.run_start_datetime.strftime('%Y-%m-%d %H:%M:%S')}"])
        rows.append([f"# Experiment: {self._current_experiment_name or '(Untitled)'}"])
        if self._current_experiment_notes:
            note = self._current_experiment_notes.strip().replace('\n', ' | ')
            rows.append([f"# Notes: {note}"])
        try:
            ident = self.smu.get_identification() if self.smu else ""
        except Exception:
            ident = ""
        if ident:
            rows.append([f"# Instrument: {ident.strip()}"])
        rows.append([f"# Mode: {'SIMULATION' if (self.smu and getattr(self.smu, 'simulate', False)) else 'HARDWARE'}"])
        rows.append([f"# Source: function={ss.function} mode={ss.mode.currentText()} range={ss.range.currentText()} compliance={ss.compliance.value()}"])
        terminal = getattr(inst, 'terminal', '?')
        hicap = inst.high_cap.isChecked() if hasattr(inst, 'high_cap') else False
        rows.append([f"# Instrument: sense={inst.sense} terminal={terminal} high_cap={hicap} output_off={inst.output_off_mode.currentText() if hasattr(inst,'output_off_mode') else '-'}"])
        measured = [name for name, cb in [("V", ms.measure_v), ("I", ms.measure_i), ("R", ms.measure_r), ("P", ms.measure_p)] if cb.isChecked()]
        rows.append([f"# Measure: {','.join(measured) or '-'}  range={ms.measure_range.currentText() if hasattr(ms,'measure_range') else '-'}  auto_zero={ms.auto_zero.currentText() if hasattr(ms,'auto_zero') else '-'}"])
        rows.append([f"# Timing: points={ts.points.value()} repeat={ts.repeat.value()} delay={ts.delay.value()}s nplc={ts.nplc.value()} step_size={ts.step_size.value()}s auto_delay={ts.auto_delay_check.isChecked()}"])
        if sweep_values is not None and len(sweep_values) > 0:
            vmin = min(sweep_values)
            vmax = max(sweep_values)
            rows.append([f"# Sweep: n={len(sweep_values)} range=[{vmin:.6g}, {vmax:.6g}] total_points={self.total_sweep_points}"])
        rows.append([])
        return rows

    def _safe_experiment_token(self) -> str:
        name = self._current_experiment_name or "Untitled"
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)

    def _experiment_save_dir(self) -> str:
        return os.path.join(self.auto_save_path, self._safe_experiment_token())

    def _generate_filename(self) -> str:
        """Generate auto filename: ExperimentName_Date_Time or Run#_Date_Time."""
        if self.run_start_datetime:
            date_str = self.run_start_datetime.strftime("%Y-%m-%d")
            time_str = self.run_start_datetime.strftime("%H-%M-%S")
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
            time_str = datetime.now().strftime("%H-%M-%S")
        token = self._safe_experiment_token()
        if self._current_experiment_name:
            return f"{token}_{date_str}_{time_str}.csv"
        return f"Run{self.run_number}_{date_str}_{time_str}.csv"

    def _auto_save_csv(self):
        """Auto-save CSV to configured directory"""
        try:
            save_dir = self._experiment_save_dir()
            os.makedirs(save_dir, exist_ok=True)
            filename = self._generate_filename()
            filepath = os.path.join(save_dir, filename)
            self._write_csv(filepath)
            self.status.showMessage(f"Auto-saved: {filename}")
        except Exception as e:
            print(f"Auto-save error: {e}")
            self.status.showMessage(f"Auto-save failed: {e}")
    
    def _write_csv(self, filepath: str):
        """Write measurement data to CSV file"""
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            sweep_values = [p.source_value for p in self.measurement_data] if self.measurement_data else None
            for row in self._build_csv_metadata_rows(sweep_values):
                writer.writerow(row)
            writer.writerow(['Index', 'Computer_Time', 'Elapsed(s)', 'Voltage(V)', 'Current(A)', 'Resistance(Ohm)', 'Power(W)'])
            for p in self.measurement_data:
                writer.writerow([
                    p.index,
                    p.computer_time,
                    f"{p.timestamp:.6f}",
                    f"{p.voltage:.9e}" if p.voltage else "",
                    f"{p.current:.9e}" if p.current else "",
                    f"{p.resistance:.9e}" if p.resistance else "",
                    f"{p.power:.9e}" if p.power else ""
                ])
    
    def export_csv(self):
        if not self.measurement_data:
            QMessageBox.warning(self, "No Data", "No data to export")
            return
        
        # Generate suggested filename
        suggested_name = self._generate_filename()
        
        file, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", 
            os.path.join(self.auto_save_path, suggested_name),
            "CSV Files (*.csv)"
        )
        if file:
            try:
                self._write_csv(file)
                self.status.showMessage(f"Exported to {file}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self):
        w = self.width()
        h = self.height()

        ratio = min(w / 1300.0, h / 900.0)
        scale = max(0.65, min(1.00, ratio))
        scale = round(scale * 20) / 20
        if abs(scale - getattr(self, "_current_ui_scale", -1)) >= 0.025:
            self._current_ui_scale = scale
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(build_global_stylesheet(scale))
                f = QFont("Inter", max(9, round(15 * scale)))
                app.setFont(f)

    def closeEvent(self, event):
        self.multimeter_panel.stop_live()
        if self.smu:
            try:
                self.smu.output_off()
            except Exception:
                pass
            self.smu.disconnect()
        event.accept()


# Global stylesheet for light theme
_GLOBAL_STYLESHEET_TEMPLATE = """
    QMainWindow, QWidget {
        background-color: #ffffff;
        color: #1a1a2e;
    }
    QLabel {
        color: #1a1a2e;
        font-size: __FONT_14__;
    }
    QPushButton {
        font-size: __FONT_14__;
        color: #1a1a2e;
        background-color: #f3f4f6;
        border: 1px solid #d1d5db;
        padding: 6px 14px;
        border-radius: 5px;
        font-weight: 500;
    }
    QPushButton:hover {
        background-color: #e5e7eb;
        border-color: #9ca3af;
    }
    QPushButton:disabled {
        background-color: #f3f4f6;
        color: #9ca3af;
        border-color: #e5e7eb;
    }
    QCheckBox, QRadioButton {
        font-size: __FONT_14__;
        color: #1a1a2e;
        font-weight: 500;
    }
    QCheckBox:disabled, QRadioButton:disabled {
        color: #9ca3af;
    }
    QGroupBox {
        font-size: __FONT_14__;
        font-weight: bold;
        color: #1a1a2e;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        margin-top: 16px;
        padding: 16px;
        padding-top: 14px;
        background-color: transparent;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 8px;
        color: #1a1a2e;
        background-color: #ffffff;
        font-size: __FONT_14__;
        font-weight: bold;
    }
    QTableWidget, QListWidget {
        font-size: __FONT_13__;
        color: #1a1a2e;
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        alternate-background-color: #f9fafb;
    }
    QTableWidget::item, QListWidget::item {
        color: #1a1a2e;
    }
    QTableWidget::item:selected, QListWidget::item:selected {
        background-color: #dbeafe;
        color: #1a1a2e;
    }
    QHeaderView::section {
        background-color: #f3f4f6;
        color: #1a1a2e;
        font-weight: bold;
        font-size: __FONT_13__;
        padding: 8px;
        border: 1px solid #d1d5db;
    }
    QToolTip {
        font-size: __FONT_13__;
        background-color: #1a1a2e;
        color: #ffffff;
        border: 1px solid #1a1a2e;
        padding: 6px;
    }
    QMenuBar {
        font-size: __FONT_14__;
        background-color: #f3f4f6;
        color: #1a1a2e;
        border-bottom: 1px solid #d1d5db;
    }
    QMenuBar::item {
        color: #1a1a2e;
    }
    QMenuBar::item:selected {
        background-color: #e5e7eb;
    }
    QMenu {
        font-size: __FONT_14__;
        background-color: #ffffff;
        color: #1a1a2e;
        border: 1px solid #d1d5db;
    }
    QMenu::item {
        color: #1a1a2e;
        padding: 6px 20px;
    }
    QMenu::item:selected {
        background-color: #dbeafe;
        color: #1a1a2e;
    }
    QTabWidget::pane {
        border: 1px solid #d1d5db;
        background-color: #ffffff;
        border-top: none;
    }
    QTabBar::tab {
        font-size: __FONT_14__;
        padding: 10px 24px;
        background-color: #f3f4f6;
        color: #6b7280;
        border: 1px solid #d1d5db;
        border-bottom: none;
        margin-right: 2px;
        font-weight: 500;
    }
    QTabBar::tab:selected {
        background-color: #ffffff;
        color: #1a1a2e;
        font-weight: bold;
        border-bottom: 2px solid #1a1a2e;
        border-color: #d1d5db;
    }
    QTabBar::tab:hover {
        background-color: #e5e7eb;
        color: #1a1a2e;
    }
    QComboBox {
        font-size: __FONT_14__;
        color: #1a1a2e;
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        padding: 6px 10px;
        border-radius: 5px;
    }
    QComboBox:hover {
        border-color: #6b7280;
    }
    QComboBox:disabled {
        background-color: #f3f4f6;
        color: #9ca3af;
    }
    QComboBox QAbstractItemView {
        background-color: #ffffff;
        color: #1a1a2e;
        selection-background-color: #dbeafe;
        selection-color: #1a1a2e;
    }
    QSpinBox, QDoubleSpinBox {
        font-size: __FONT_14__;
        color: #1a1a2e;
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        padding: 4px 6px;
        padding-right: 22px;
        border-radius: 5px;
    }
    QSpinBox:hover, QDoubleSpinBox:hover {
        border-color: #6b7280;
    }
    QSpinBox:disabled, QDoubleSpinBox:disabled {
        background-color: #f3f4f6;
        color: #9ca3af;
    }
    /* Spinbox up/down buttons: only style the area, let Fusion paint the arrows */
    QSpinBox::up-button, QDoubleSpinBox::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button,
    QComboBox::drop-down {
        background-color: transparent;
        border: none;
    }
    QTextEdit, QLineEdit {
        font-size: __FONT_13__;
        color: #1a1a2e;
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 4px;
        padding: 4px 6px;
    }
    QScrollBar:vertical {
        background-color: #f3f4f6;
        width: 12px;
        border-radius: 6px;
    }
    QScrollBar::handle:vertical {
        background-color: #d1d5db;
        border-radius: 6px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #9ca3af;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        background-color: #f3f4f6;
        height: 12px;
        border-radius: 6px;
    }
    QScrollBar::handle:horizontal {
        background-color: #d1d5db;
        border-radius: 6px;
        min-width: 30px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #9ca3af;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    QStatusBar {
        background-color: #f3f4f6;
        color: #4b5563;
        border-top: 1px solid #d1d5db;
    }
    QProgressBar {
        border: 1px solid #d1d5db;
        border-radius: 4px;
        background-color: #ffffff;
        text-align: center;
        color: #1a1a2e;
        font-weight: bold;
    }
    QProgressBar::chunk {
        background-color: #1a1a2e;
        border-radius: 3px;
    }
    QSplitter::handle {
        background-color: #e5e7eb;
    }
    QSplitter::handle:hover {
        background-color: #d1d5db;
    }
"""


def build_global_stylesheet(scale: float = 1.0) -> str:
    """Render the global stylesheet with all font sizes scaled by `scale`."""
    def px(base: int) -> str:
        return f"{max(8, round(base * scale))}px"
    return (_GLOBAL_STYLESHEET_TEMPLATE
            .replace("__FONT_14__", px(14))
            .replace("__FONT_13__", px(13)))


# Backwards-compat alias: existing callers (launcher) import GLOBAL_STYLESHEET.
GLOBAL_STYLESHEET = build_global_stylesheet(1.0)


def main():
    app = QApplication(sys.argv)
    app.setPalette(LightPalette())
    app.setStyle('Fusion')

    app.setStyleSheet(build_global_stylesheet(1.0))

    # Set Inter font AFTER stylesheet — on macOS, setStyleSheet() resets app font
    app.setFont(QFont("Inter", 15))

    window = Keithley2450App()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
