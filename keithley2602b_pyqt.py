"""
Keithley 2602B Dual-Channel SourceMeter Control Application
PyQt5 + pyqtgraph version with ALL features

Features:
- Modern dark theme UI with green/amber accents and pyqtgraph plotting
- Dual independent channels (smua/smub) with channel toggle
- Live multimeter mode with large digital displays
- Full I-V sweep characterization (Linear, List, Log)
- 2/4-Wire sensing
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
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QTabWidget, QGroupBox, QLabel, QPushButton,
    QComboBox, QLineEdit, QCheckBox, QSpinBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QFrame, QMessageBox, QFileDialog, QDialog, QListWidget,
    QProgressBar, QStatusBar, QTextEdit, QSizePolicy, QMenuBar,
    QMenu, QAction, QFormLayout, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QSettings
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon

import pyqtgraph as pg

# Import our driver
from keithley2602b_driver import (
    Keithley2602B, SafetyLimits, Keithley2602BError,
    SourceFunction, MeasureFunction, SenseMode
)

# Configure pyqtgraph
pg.setConfigOptions(antialias=True, background='#1a1a2e', foreground='#e5e7eb')

# Version info
__version__ = "1.0.0"
__app_name__ = "K2602B Control Suite"
__author__ = "Omer Vered"
__organization__ = "Ben-Gurion University of the Negev (BGU)"
__copyright__ = "Copyright 2026 Omer Vered, BGU"


@dataclass
class MeasurementPoint:
    """Single measurement data point"""
    index: int
    timestamp: float
    source_value: float
    channel: str = "a"
    computer_time: str = ""
    voltage: Optional[float] = None
    current: Optional[float] = None
    resistance: Optional[float] = None
    power: Optional[float] = None


class LightPalette(QPalette):
    """Dark theme color palette with green/amber accents"""
    def __init__(self):
        super().__init__()
        self.setColor(QPalette.Window, QColor(26, 26, 46))             # #1a1a2e
        self.setColor(QPalette.WindowText, QColor(229, 231, 235))      # #e5e7eb
        self.setColor(QPalette.Base, QColor(22, 33, 62))               # #16213e
        self.setColor(QPalette.AlternateBase, QColor(30, 42, 69))      # #1e2a45
        self.setColor(QPalette.ToolTipBase, QColor(20, 83, 45))        # #14532d
        self.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
        self.setColor(QPalette.Text, QColor(229, 231, 235))            # #e5e7eb
        self.setColor(QPalette.Button, QColor(20, 83, 45))             # #14532d
        self.setColor(QPalette.ButtonText, QColor(34, 197, 94))        # #22c55e
        self.setColor(QPalette.BrightText, QColor(239, 68, 68))        # #ef4444
        self.setColor(QPalette.Link, QColor(34, 197, 94))              # #22c55e
        self.setColor(QPalette.Highlight, QColor(34, 197, 94))         # #22c55e
        self.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.setColor(QPalette.Disabled, QPalette.WindowText, QColor(75, 85, 99))   # #4b5563
        self.setColor(QPalette.Disabled, QPalette.Text, QColor(75, 85, 99))         # #4b5563
        self.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(75, 85, 99))   # #4b5563


class ToggleButton(QPushButton):
    """Toggle button with selected/unselected state - green accent"""
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
                    background-color: #22c55e;
                    color: white;
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
                    background-color: #14532d;
                    color: #22c55e;
                    border: 1px solid #16a34a;
                    padding: 6px 16px;
                    font-weight: 500;
                    font-size: 14px;
                    border-radius: 5px;
                }
                QPushButton:hover { background-color: #16a34a; border-color: #16a34a; }
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
            text = f"{value*1e6:.{self.decimals}f} \u00b5{self.unit}"
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
    """Live multimeter mode panel with channel support"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = parent
        self.running = False
        self.recording = False
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_reading)
        self.reading_count = 0
        self.record_start_time = None
        self.recorded_data = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # Title
        title = QLabel("LIVE MULTIMETER")
        title.setFont(QFont("Inter", 24, QFont.Bold))
        title.setStyleSheet("color: #22c55e;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Channel indicator
        ch_layout = QHBoxLayout()
        ch_layout.addStretch()
        self.channel_indicator = QLabel("Channel A")
        self.channel_indicator.setStyleSheet("color: #22c55e; font-size: 18px; font-weight: bold;")
        ch_layout.addWidget(self.channel_indicator)
        ch_layout.addStretch()
        layout.addLayout(ch_layout)

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
        self.source_value.setRange(-40, 40)
        self.source_value.setDecimals(4)
        self.source_value.setValue(0)
        self.source_value.setSuffix(" V")
        settings.addWidget(self.source_value)

        settings.addWidget(QLabel("Limit:"))
        self.compliance = QDoubleSpinBox()
        self.compliance.setRange(0.001, 3.0)
        self.compliance.setDecimals(4)
        self.compliance.setValue(0.1)
        self.compliance.setSuffix(" A")
        settings.addWidget(self.compliance)

        settings.addStretch()
        layout.addLayout(settings)

        # Instrument settings row
        inst_row = QHBoxLayout()

        inst_row.addWidget(QLabel("Sense:"))
        self.sense_2w = ToggleButton("2-Wire")
        self.sense_2w.set_selected(True)
        self.sense_2w.clicked.connect(lambda: self._set_sense("2-Wire"))
        inst_row.addWidget(self.sense_2w)

        self.sense_4w = ToggleButton("4-Wire")
        self.sense_4w.clicked.connect(lambda: self._set_sense("4-Wire"))
        inst_row.addWidget(self.sense_4w)
        self.sense = "2-Wire"

        inst_row.addStretch()
        layout.addLayout(inst_row)

        # Digital displays
        displays = QGridLayout()

        v_group = QGroupBox("Voltage")
        v_layout = QVBoxLayout(v_group)
        self.voltage_display = DigitalDisplay("V", 6)
        self.voltage_display.set_color("#22c55e")
        v_layout.addWidget(self.voltage_display)
        displays.addWidget(v_group, 0, 0)

        i_group = QGroupBox("Current")
        i_layout = QVBoxLayout(i_group)
        self.current_display = DigitalDisplay("A", 6)
        self.current_display.set_color("#d97706")
        i_layout.addWidget(self.current_display)
        displays.addWidget(i_group, 0, 1)

        r_group = QGroupBox("Resistance")
        r_layout = QVBoxLayout(r_group)
        self.resistance_display = DigitalDisplay("\u03a9", 4)
        self.resistance_display.set_color("#0891b2")
        r_layout.addWidget(self.resistance_display)
        displays.addWidget(r_group, 1, 0)

        p_group = QGroupBox("Power")
        p_layout = QVBoxLayout(p_group)
        self.power_display = DigitalDisplay("W", 6)
        self.power_display.set_color("#c026d3")
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

        self.start_btn = QPushButton("\u25b6 START")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745; color: white;
                font-family: 'Inter'; font-size: 22px; font-weight: bold;
                padding: 18px 45px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #218838; }
        """)
        self.start_btn.clicked.connect(self.start_live)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("\u25a0 STOP")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545; color: white;
                font-family: 'Inter'; font-size: 22px; font-weight: bold;
                padding: 18px 45px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #c82333; }
            QPushButton:disabled { background-color: #374151; color: #4b5563; }
        """)
        self.stop_btn.clicked.connect(self.stop_live)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        layout.addLayout(btn_layout)

        # Recording buttons
        record_layout = QHBoxLayout()

        self.record_btn = QPushButton("\u23fa RECORD")
        self.record_btn.setStyleSheet("""
            QPushButton {
                background-color: #e83e8c; color: white;
                font-family: 'Inter'; font-size: 20px; font-weight: bold;
                padding: 14px 35px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #d63384; }
            QPushButton:disabled { background-color: #374151; color: #4b5563; }
        """)
        self.record_btn.clicked.connect(self._start_recording)
        self.record_btn.setEnabled(False)
        record_layout.addWidget(self.record_btn)

        self.pause_record_btn = QPushButton("\u23f8 PAUSE")
        self.pause_record_btn.setStyleSheet("""
            QPushButton {
                background-color: #fd7e14; color: white;
                font-family: 'Inter'; font-size: 20px; font-weight: bold;
                padding: 14px 35px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #e67312; }
            QPushButton:disabled { background-color: #374151; color: #4b5563; }
        """)
        self.pause_record_btn.clicked.connect(self._pause_recording)
        self.pause_record_btn.setEnabled(False)
        record_layout.addWidget(self.pause_record_btn)

        self.save_record_btn = QPushButton("\U0001f4be SAVE CSV")
        self.save_record_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8; color: white;
                font-family: 'Inter'; font-size: 20px; font-weight: bold;
                padding: 14px 35px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #138496; }
            QPushButton:disabled { background-color: #374151; color: #4b5563; }
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
        self.record_graph.setBackground('#1a1a2e')
        self.record_graph.setLabel('left', 'Value', color='#e5e7eb')
        self.record_graph.setLabel('bottom', 'Time (s)', color='#e5e7eb')
        self.record_graph.setTitle("Recording Graph", color='#e5e7eb', size='14pt')
        self.record_graph.addLegend()
        self.record_graph.showGrid(x=True, y=True, alpha=0.2)
        self.record_graph.setMinimumHeight(200)

        self.voltage_plot = self.record_graph.plot([], [], pen=pg.mkPen('#16a34a', width=2), name='Voltage (V)')
        self.current_plot = self.record_graph.plot([], [], pen=pg.mkPen('#d97706', width=2), name='Current (A)')
        self.power_plot = self.record_graph.plot([], [], pen=pg.mkPen('#c026d3', width=2), name='Power (W)')

        layout.addWidget(self.record_graph)

        layout.addStretch()

    def _update_source_units(self, source_type):
        if source_type == "Voltage":
            self.source_value.setSuffix(" V")
            self.source_value.setRange(-40, 40)
            self.compliance.setSuffix(" A")
            self.compliance.setRange(0.001, 3.0)
            self.compliance.setValue(0.1)
        else:
            self.source_value.setSuffix(" A")
            self.source_value.setRange(-3, 3)
            self.compliance.setSuffix(" V")
            self.compliance.setRange(0.1, 40)
            self.compliance.setValue(20)

    def _update_rate_changed(self):
        rates = [1000, 200, 100, 50]
        if self.running:
            self.timer.setInterval(rates[self.update_rate.currentIndex()])

    def _set_sense(self, sense):
        self.sense = sense
        self.sense_2w.set_selected(sense == "2-Wire")
        self.sense_4w.set_selected(sense == "4-Wire")

    def update_channel_display(self):
        """Update channel indicator based on app's current channel"""
        ch = self.app.current_channel.upper()
        self.channel_indicator.setText(f"Channel {ch}")

    def start_live(self):
        if not self.app.smu or not self.app.smu._connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to instrument first")
            return

        try:
            source_val = self.source_value.value()
            compliance = self.compliance.value()
            ch = self.app.current_channel

            if self.source_type.currentText() == "Voltage":
                self.app.smu.set_source_voltage(source_val, compliance_current=compliance, channel=ch)
            else:
                self.app.smu.set_source_current(source_val, compliance_voltage=compliance, channel=ch)

            self.app.smu.output_on(ch)

            self.running = True
            self.reading_count = 0
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.record_btn.setEnabled(True)

            rates = [1000, 200, 100, 50]
            self.timer.start(rates[self.update_rate.currentIndex()])

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def stop_live(self):
        self.timer.stop()
        self.running = False

        if self.app.smu:
            try:
                self.app.smu.output_off(self.app.current_channel)
            except:
                pass

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

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
            ch = self.app.current_channel
            smu = self.app.smu

            measure = self.measure_type.currentText()

            if measure in ["Voltage", "Resistance", "All"]:
                voltage = smu.measure_voltage(ch)

            if measure in ["Current", "Resistance", "All"]:
                current = smu.measure_current(ch)

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

            self.reading_count += 1
            self.readings_label.setText(f"Readings: {self.reading_count}")

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
        self.recording = True
        self.record_start_time = time.time()
        self.recorded_data = []
        self.record_btn.setEnabled(False)
        self.pause_record_btn.setEnabled(True)
        self.save_record_btn.setEnabled(False)
        self.record_status.setText("Recording: Active | Points: 0")
        self.record_status.setStyleSheet("color: #e83e8c; font-weight: bold;")
        self.voltage_plot.setData([], [])
        self.current_plot.setData([], [])
        self.power_plot.setData([], [])

    def _pause_recording(self):
        self.recording = False
        self.record_btn.setEnabled(True)
        self.pause_record_btn.setEnabled(False)
        self.save_record_btn.setEnabled(len(self.recorded_data) > 0)
        self.record_status.setText(f"Recording: Paused | Points: {len(self.recorded_data)}")
        self.record_status.setStyleSheet("color: #fd7e14;")

    def _save_recording(self):
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
                    writer.writerow(["Time(s)", "Voltage(V)", "Current(A)", "Resistance(\u03a9)", "Power(W)"])
                    for row in self.recorded_data:
                        writer.writerow(row)
                QMessageBox.information(self, "Success", f"Saved {len(self.recorded_data)} points to CSV")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _update_record_graph(self):
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
    """Source settings panel — no DC/Pulse for 2602B"""

    def __init__(self, parent=None):
        super().__init__("Source Settings", parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

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
        self.range.addItems(["Auto", "100 mV", "1 V", "6 V", "40 V"])
        range_layout.addWidget(self.range)
        range_layout.addStretch()
        layout.addLayout(range_layout)

        # Limit (Compliance)
        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("Limit:"))
        self.compliance = QDoubleSpinBox()
        self.compliance.setRange(0.001, 3.0)
        self.compliance.setDecimals(4)
        self.compliance.setValue(0.1)
        self.compliance.setSuffix(" A")
        limit_layout.addWidget(self.compliance)
        limit_layout.addStretch()
        layout.addLayout(limit_layout)

        self.function = "Voltage"

    def _set_function(self, func_name):
        self.function = func_name
        self.volt_btn.set_selected(func_name == "Voltage")
        self.curr_btn.set_selected(func_name == "Current")

        if func_name == "Voltage":
            self.compliance.setSuffix(" A")
            self.compliance.setRange(0.001, 3.0)
            self.compliance.setValue(0.1)
            self.range.clear()
            self.range.addItems(["Auto", "100 mV", "1 V", "6 V", "40 V"])
        else:
            self.compliance.setSuffix(" V")
            self.compliance.setRange(0.1, 40)
            self.compliance.setValue(20)
            self.range.clear()
            self.range.addItems(["Auto", "100 nA", "1 \u00b5A", "10 \u00b5A", "100 \u00b5A", "1 mA", "10 mA", "100 mA", "1 A", "3 A"])


class InstrumentSettingsWidget(QGroupBox):
    """Instrument settings: Sense mode (no terminal for 2602B)"""

    def __init__(self, parent=None):
        super().__init__("Instrument Settings", parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Sense: 2-Wire / 4-Wire
        sense_layout = QHBoxLayout()
        sense_layout.addWidget(QLabel("Sense:"))

        self.sense_2w = ToggleButton("2-Wire")
        self.sense_2w.set_selected(True)
        self.sense_2w.clicked.connect(lambda: self._set_sense("2-Wire"))
        sense_layout.addWidget(self.sense_2w)

        self.sense_4w = ToggleButton("4-Wire")
        self.sense_4w.clicked.connect(lambda: self._set_sense("4-Wire"))
        sense_layout.addWidget(self.sense_4w)

        sense_layout.addStretch()
        layout.addLayout(sense_layout)

        # Output Off State
        off_layout = QHBoxLayout()
        off_layout.addWidget(QLabel("Output Off:"))
        self.output_off_mode = QComboBox()
        self.output_off_mode.addItems(["Normal", "Zero", "High-Z"])
        off_layout.addWidget(self.output_off_mode)
        off_layout.addStretch()
        layout.addLayout(off_layout)

        self.sense = "2-Wire"

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
        self.measure_range.addItems(["Auto", "100 nA", "1 \u00b5A", "10 \u00b5A", "100 \u00b5A", "1 mA", "10 mA", "100 mA", "1 A", "3 A"])
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

        self.points = QSpinBox()
        self.points.setRange(1, 100000)
        self.points.setValue(51)
        layout.addRow("Points:", self.points)

        self.repeat = QSpinBox()
        self.repeat.setRange(1, 1000)
        self.repeat.setValue(1)
        layout.addRow("Repeat:", self.repeat)

        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 10)
        self.delay.setDecimals(4)
        self.delay.setValue(0.05)
        self.delay.setSuffix(" s")
        layout.addRow("Delay:", self.delay)

        self.nplc = QDoubleSpinBox()
        self.nplc.setRange(0.001, 25)
        self.nplc.setDecimals(3)
        self.nplc.setValue(1.0)
        self.nplc.valueChanged.connect(self._update_window)
        layout.addRow("NPLC:", self.nplc)

        self.window_label = QLabel("20 ms")
        layout.addRow("Window:", self.window_label)

    def _update_window(self):
        nplc = self.nplc.value()
        window_ms = nplc * 20
        self.window_label.setText(f"{window_ms:.1f} ms")


class SweepListWidget(QGroupBox):
    """Sweep list management with table"""

    list_changed = pyqtSignal(int)
    wave_generator_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Sweep Values", parent)
        self._setup_ui()
        self.sweep_values = []

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["#", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMaximumHeight(200)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e2a45;
                color: #e5e7eb;
                gridline-color: #374151;
                font-size: 13px;
            }
            QTableWidget::item { color: #e5e7eb; }
            QHeaderView::section {
                background-color: #14532d;
                color: #22c55e;
                font-weight: bold;
                font-size: 13px;
                padding: 6px;
                border: 1px solid #374151;
            }
        """)
        layout.addWidget(self.table)

        # Linear sweep settings
        linear_layout = QHBoxLayout()
        linear_layout.addWidget(QLabel("Start:"))
        self.start_val = QDoubleSpinBox()
        self.start_val.setRange(-40, 40)
        self.start_val.setDecimals(4)
        self.start_val.setValue(0)
        linear_layout.addWidget(self.start_val)

        linear_layout.addWidget(QLabel("Stop:"))
        self.stop_val = QDoubleSpinBox()
        self.stop_val.setRange(-40, 40)
        self.stop_val.setDecimals(4)
        self.stop_val.setValue(5)
        linear_layout.addWidget(self.stop_val)

        linear_layout.addWidget(QLabel("Points:"))
        self.num_points = QSpinBox()
        self.num_points.setRange(2, 10000)
        self.num_points.setValue(51)
        linear_layout.addWidget(self.num_points)

        layout.addLayout(linear_layout)

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

        # Wave Generator button
        wave_layout = QHBoxLayout()
        wave_btn = QPushButton("\U0001f30a Wave Generator")
        wave_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8; color: white;
                font-family: 'Inter'; font-size: 15px;
                font-weight: bold; padding: 10px 20px;
            }
            QPushButton:hover { background-color: #138496; }
        """)
        wave_btn.clicked.connect(self.wave_generator_requested.emit)
        wave_layout.addWidget(wave_btn)
        wave_layout.addStretch()
        layout.addLayout(wave_layout)

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

        self.setBackground('#1a1a2e')
        self.showGrid(x=True, y=True, alpha=0.2)

        self.data_points: List[MeasurementPoint] = []

        self.setLabel('left', 'Current', units='A', color='#d97706')
        self.setLabel('bottom', 'Voltage', units='V')

        self.view_box2 = pg.ViewBox()
        self.plotItem.scene().addItem(self.view_box2)
        self.plotItem.getAxis('right').linkToView(self.view_box2)
        self.view_box2.setXLink(self.plotItem)
        self.plotItem.showAxis('right')

        self.curve1 = self.plot([], [], pen=pg.mkPen('#d97706', width=2), name='Y1')
        self.curve2 = pg.PlotDataItem([], [], pen=pg.mkPen('#0891b2', width=2), name='Y2')
        self.view_box2.addItem(self.curve2)

        self.plotItem.vb.sigResized.connect(self._update_views)

        self.x_axis = "Voltage"
        self.y1_axis = "Current"
        self.y2_axis = "None"

        self.addLegend()

    def _update_views(self):
        self.view_box2.setGeometry(self.plotItem.vb.sceneBoundingRect())
        self.view_box2.linkedViewChanged(self.plotItem.vb, self.view_box2.XAxis)

    def set_axes(self, x: str, y1: str, y2: str):
        self.x_axis = x
        self.y1_axis = y1
        self.y2_axis = y2

        x_unit = {"Voltage": "V", "Current": "A", "Time": "s", "Index": ""}.get(x, "")
        y1_unit = {"Voltage": "V", "Current": "A", "Resistance": "\u03a9", "Power": "W"}.get(y1, "")
        y2_unit = {"Voltage": "V", "Current": "A", "Resistance": "\u03a9", "Power": "W"}.get(y2, "")

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
        self._update_plot()
        self.enableAutoRange()
        self.view_box2.enableAutoRange()


class DataTableWidget(QTableWidget):
    """Data table with Channel column and export capability"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(8)
        self.setHorizontalHeaderLabels(['#', 'Channel', 'Computer Time', 'Elapsed (s)', 'Voltage (V)', 'Current (A)', 'Resistance (\u03a9)', 'Power (W)'])

        header = self.horizontalHeader()
        for i in range(8):
            header.setSectionResizeMode(i, QHeaderView.Stretch)

        self.setAlternatingRowColors(True)
        self.setStyleSheet("""
            QTableWidget {
                background-color: #1e2a45;
                alternate-background-color: #16213e;
                color: #e5e7eb;
                gridline-color: #374151;
                font-size: 13px;
            }
            QTableWidget::item { color: #e5e7eb; padding: 4px; }
            QHeaderView::section {
                background-color: #14532d;
                color: #22c55e;
                font-weight: bold;
                font-size: 13px;
                padding: 8px 5px;
                border: 1px solid #374151;
            }
        """)

    def add_point(self, point: MeasurementPoint):
        row = self.rowCount()
        self.insertRow(row)

        self.setItem(row, 0, QTableWidgetItem(str(point.index)))
        self.setItem(row, 1, QTableWidgetItem(point.channel.upper()))
        self.setItem(row, 2, QTableWidgetItem(point.computer_time))
        self.setItem(row, 3, QTableWidgetItem(f"{point.timestamp:.3f}"))
        self.setItem(row, 4, QTableWidgetItem(f"{point.voltage:.9e}" if point.voltage else ""))
        self.setItem(row, 5, QTableWidgetItem(f"{point.current:.9e}" if point.current else ""))
        self.setItem(row, 6, QTableWidgetItem(f"{point.resistance:.4e}" if point.resistance and abs(point.resistance) < 1e12 else ""))
        self.setItem(row, 7, QTableWidgetItem(f"{point.power:.6e}" if point.power else ""))

        self.scrollToBottom()

    def clear_data(self):
        self.setRowCount(0)


class ConnectionDialog(QDialog):
    """Connection dialog with simulation options"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = parent
        self.setWindowTitle("Connect to Keithley 2602B")
        self.setMinimumSize(550, 450)
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

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

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #f59e0b;")
        layout.addWidget(line)

        layout.addWidget(QLabel("Simulation Mode:"))

        sim_group = QGroupBox("Simulation Settings")
        sim_layout = QVBoxLayout(sim_group)

        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("Resistance:"))
        self.sim_resistance = QDoubleSpinBox()
        self.sim_resistance.setRange(1, 1e9)
        self.sim_resistance.setValue(1000)
        self.sim_resistance.setSuffix(" \u03a9")
        res_layout.addWidget(self.sim_resistance)
        res_layout.addStretch()
        sim_layout.addLayout(res_layout)

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Presets:"))
        for val, label in [(10, "10\u03a9"), (100, "100\u03a9"), (1000, "1k\u03a9"), (10000, "10k\u03a9"), (100000, "100k\u03a9")]:
            btn = QPushButton(label)
            btn.setMaximumWidth(60)
            btn.clicked.connect(lambda checked, v=val: self.sim_resistance.setValue(v))
            preset_layout.addWidget(btn)
        preset_layout.addStretch()
        sim_layout.addLayout(preset_layout)

        layout.addWidget(sim_group)

        simulate_btn = QPushButton("\U0001f3ae Start Simulation")
        simulate_btn.setStyleSheet("background-color: #17a2b8; color: white; font-family: 'Inter'; font-weight: bold; padding: 14px; font-size: 18px;")
        simulate_btn.clicked.connect(self._simulate)
        layout.addWidget(simulate_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _refresh(self):
        self.resource_list.clear()
        resources = Keithley2602B.list_available_instruments()
        for r in resources:
            self.resource_list.addItem(r)
            if "2602" in r or "05E6" in r.upper():
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

        layout.addWidget(QLabel("\u26a0\ufe0f SAFETY LIMITS - Protect your device!"))
        layout.addWidget(QLabel("These limits prevent damage to your DUT."))

        form = QFormLayout()

        self.max_voltage = QDoubleSpinBox()
        self.max_voltage.setRange(0.1, 40)
        self.max_voltage.setValue(self.limits.max_voltage)
        self.max_voltage.setSuffix(" V")
        form.addRow("Max Voltage:", self.max_voltage)

        self.min_voltage = QDoubleSpinBox()
        self.min_voltage.setRange(-40, 0)
        self.min_voltage.setValue(self.limits.min_voltage)
        self.min_voltage.setSuffix(" V")
        form.addRow("Min Voltage:", self.min_voltage)

        self.max_current = QDoubleSpinBox()
        self.max_current.setRange(0.001, 3.0)
        self.max_current.setDecimals(4)
        self.max_current.setValue(self.limits.max_current)
        self.max_current.setSuffix(" A")
        form.addRow("Max Current:", self.max_current)

        self.min_current = QDoubleSpinBox()
        self.min_current.setRange(-3.0, 0)
        self.min_current.setDecimals(4)
        self.min_current.setValue(self.limits.min_current)
        self.min_current.setSuffix(" A")
        form.addRow("Min Current:", self.min_current)

        self.power_limit = QDoubleSpinBox()
        self.power_limit.setRange(0.1, 40.4)
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

        title = QLabel(f"<h2>{__app_name__}</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        layout.addWidget(QLabel("Please read and accept the following license agreement:"))

        license_text = QTextEdit()
        license_text.setReadOnly(True)
        license_text.setPlainText(self._get_license_text())
        layout.addWidget(license_text)

        self.accept_check = QCheckBox("I have read and agree to the license terms")
        layout.addWidget(self.accept_check)

        btn_layout = QHBoxLayout()
        self.accept_btn = QPushButton("Accept")
        self.accept_btn.setEnabled(False)
        self.accept_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.accept_btn)

        decline_btn = QPushButton("Decline")
        decline_btn.clicked.connect(self.reject)
        btn_layout.addWidget(decline_btn)

        layout.addLayout(btn_layout)

        self.accept_check.stateChanged.connect(
            lambda state: self.accept_btn.setEnabled(state == Qt.Checked)
        )

    def _get_license_text(self):
        return f"""{__app_name__}
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


class WaveToolDialog(QDialog):
    """Wave Generator Tool - Creates waveforms for I-V sweeps"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wave Generator Tool")
        self.setMinimumSize(900, 750)
        self.waveform_values = []
        self.time_values = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("<h2>Heat Wave Generator</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()

        res_layout = QHBoxLayout()
        self.resistance = QDoubleSpinBox()
        self.resistance.setRange(0.1, 1e9)
        self.resistance.setValue(10)
        self.resistance.setDecimals(2)
        res_layout.addWidget(self.resistance)
        self.res_unit = QComboBox()
        self.res_unit.addItems(["\u03a9", "k\u03a9"])
        res_layout.addWidget(self.res_unit)
        form.addRow("Resistance (R):", res_layout)

        self.design_mode = QComboBox()
        self.design_mode.addItems(["Power (W)", "Voltage (V)", "Current (A)"])
        form.addRow("Design By:", self.design_mode)

        avg_layout = QHBoxLayout()
        self.avg_value = QDoubleSpinBox()
        self.avg_value.setRange(-1000, 1000)
        self.avg_value.setValue(20)
        self.avg_value.setDecimals(4)
        avg_layout.addWidget(self.avg_value)
        self.avg_unit = QComboBox()
        self.avg_unit.addItems(["W", "mW", "V", "mV", "A", "mA"])
        avg_layout.addWidget(self.avg_unit)
        form.addRow("Average Value:", avg_layout)

        max_layout = QHBoxLayout()
        self.max_value = QDoubleSpinBox()
        self.max_value.setRange(-1000, 1000)
        self.max_value.setValue(30)
        self.max_value.setDecimals(4)
        max_layout.addWidget(self.max_value)
        self.max_unit = QComboBox()
        self.max_unit.addItems(["W", "mW", "V", "mV", "A", "mA"])
        max_layout.addWidget(self.max_unit)
        form.addRow("Max Value:", max_layout)

        self.wave_type = QComboBox()
        self.wave_type.addItems(["Sine", "Square", "Triangle", "Sawtooth"])
        form.addRow("Wave Type:", self.wave_type)

        period_layout = QHBoxLayout()
        self.period = QDoubleSpinBox()
        self.period.setRange(0.001, 100000)
        self.period.setValue(240)
        self.period.setDecimals(3)
        period_layout.addWidget(self.period)
        self.period_unit = QComboBox()
        self.period_unit.addItems(["sec", "min", "hour", "ms"])
        period_layout.addWidget(self.period_unit)
        form.addRow("Period:", period_layout)

        self.cycles = QSpinBox()
        self.cycles.setRange(1, 1000)
        self.cycles.setValue(5)
        form.addRow("Total Cycles:", self.cycles)

        step_layout = QHBoxLayout()
        self.step_size = QDoubleSpinBox()
        self.step_size.setRange(0.0001, 1000)
        self.step_size.setValue(1)
        self.step_size.setDecimals(4)
        step_layout.addWidget(self.step_size)
        self.step_unit = QComboBox()
        self.step_unit.addItems(["sec", "ms", "\u03bcs"])
        step_layout.addWidget(self.step_unit)
        form.addRow("Step Size (dt):", step_layout)

        self.export_mode = QComboBox()
        self.export_mode.addItems(["Voltage (V)", "Current (A)"])
        form.addRow("Export As:", self.export_mode)

        layout.addLayout(form)

        preview_btn = QPushButton("Preview Waveform")
        preview_btn.setStyleSheet("background-color: #17a2b8; color: white; font-family: 'Inter'; font-size: 15px; padding: 12px; font-weight: bold;")
        preview_btn.clicked.connect(self._preview)
        layout.addWidget(preview_btn)

        self.info_label = QLabel("Configure parameters and click Preview")
        self.info_label.setStyleSheet("color: #9ca3af; font-style: italic;")
        layout.addWidget(self.info_label)

        self.preview_graph = pg.PlotWidget()
        self.preview_graph.setBackground('#1a1a2e')
        self.preview_graph.setLabel('left', 'Output Value', color='#e5e7eb')
        self.preview_graph.setLabel('bottom', 'Time (s)', color='#e5e7eb')
        self.preview_graph.setTitle("Waveform Preview", color='#e5e7eb', size='14pt')
        self.preview_graph.showGrid(x=True, y=True, alpha=0.2)
        self.preview_graph.setMinimumHeight(200)
        self.waveform_plot = self.preview_graph.plot([], [], pen=pg.mkPen('#16a34a', width=2))
        layout.addWidget(self.preview_graph)

        btn_layout = QHBoxLayout()
        generate_btn = QPushButton("Generate && Import to Sweep List")
        generate_btn.setStyleSheet("background-color: #28a745; color: white; font-family: 'Inter'; font-size: 15px; padding: 12px; font-weight: bold;")
        generate_btn.clicked.connect(self._generate_and_accept)
        btn_layout.addWidget(generate_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        btn_layout.addWidget(export_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _get_unit_multiplier(self, unit: str) -> float:
        units = {
            "sec": 1.0, "min": 60.0, "hour": 3600.0, "ms": 1e-3, "\u03bcs": 1e-6,
            "\u03a9": 1.0, "k\u03a9": 1e3,
            "W": 1.0, "mW": 1e-3,
            "V": 1.0, "mV": 1e-3,
            "A": 1.0, "mA": 1e-3
        }
        return units.get(unit, 1.0)

    def _calculate_waveform(self):
        try:
            R = self.resistance.value() * self._get_unit_multiplier(self.res_unit.currentText())
            period_sec = self.period.value() * self._get_unit_multiplier(self.period_unit.currentText())
            dt = self.step_size.value() * self._get_unit_multiplier(self.step_unit.currentText())
            cycles = self.cycles.value()
            mode = self.design_mode.currentText().split(" ")[0]
            avg_mult = self._get_unit_multiplier(self.avg_unit.currentText())
            max_mult = self._get_unit_multiplier(self.max_unit.currentText())
            avg = self.avg_value.value() * avg_mult
            max_val = self.max_value.value() * max_mult
            amplitude = max_val - avg
            t = np.arange(0, cycles * period_sec, dt)
            f = 1.0 / period_sec

            wave_type = self.wave_type.currentText()
            if wave_type == "Sine":
                wave = avg + amplitude * np.sin(2 * np.pi * f * t)
            elif wave_type == "Square":
                wave = avg + amplitude * np.sign(np.sin(2 * np.pi * f * t))
            elif wave_type == "Triangle":
                wave = avg + amplitude * (2 * np.abs(2 * (t * f - np.floor(t * f + 0.5))) - 1)
            elif wave_type == "Sawtooth":
                wave = avg + amplitude * (2 * (t * f - np.floor(t * f + 0.5)))

            export_target = self.export_mode.currentText().split(" ")[0]

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

            return t, wave, final_values, f
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return None

    def _preview(self):
        result = self._calculate_waveform()
        if result:
            t, wave, final_values, f = result
            self.waveform_values = list(final_values)
            self.time_values = list(t)
            export_unit = "V" if "Voltage" in self.export_mode.currentText() else "A"
            self.info_label.setText(
                f"Generated {len(final_values)} points | "
                f"Frequency: {f:.6f} Hz | "
                f"Duration: {t[-1]:.2f}s | "
                f"Output: {min(final_values):.4f} to {max(final_values):.4f} {export_unit}"
            )
            self.info_label.setStyleSheet("color: #22c55e; font-weight: bold;")
            self.waveform_plot.setData(self.time_values, self.waveform_values)
            self.preview_graph.setLabel('left', f'Output ({export_unit})')

    def _generate_and_accept(self):
        self._preview()
        if self.waveform_values:
            self.accept()

    def _export_csv(self):
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
        return self.waveform_values


class Keithley2602BApp(QMainWindow):
    """Main application window — Dual-channel 2602B control"""

    measurement_update = pyqtSignal(object)

    def __init__(self):
        super().__init__()

        self.smu: Optional[Keithley2602B] = None
        self.safety_limits = SafetyLimits()
        self.measurement_data: List[MeasurementPoint] = []
        self.current_channel = "a"
        self.running = False
        self.abort_flag = False

        self.run_number = 0
        self.run_start_datetime = None
        self.auto_save_enabled = True
        self.auto_save_path = os.path.join(os.path.expanduser("~"), "Documents", "K2602B_Data")

        self.settings = QSettings(__organization__, __app_name__)

        self.setWindowTitle(f"{__app_name__} - Dual-Channel I-V Characterizer")
        self.setMinimumSize(1000, 700)

        if not self._check_license_agreement():
            sys.exit(0)

        self._create_menu()
        self._setup_ui()
        self._setup_signals()

    def _set_channel(self, channel: str):
        """Switch the active channel"""
        self.current_channel = channel
        self.channel_a_btn.set_selected(channel == "a")
        self.channel_b_btn.set_selected(channel == "b")
        self.multimeter_panel.update_channel_display()
        self.status.showMessage(f"Active channel: {channel.upper()}")

    def _toggle_output(self, channel: str):
        """Toggle output on/off for a specific channel"""
        if not self.smu or not self.smu._connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to instrument first")
            return

        try:
            if self.smu.output_enabled(channel):
                self.smu.output_off(channel)
                self._update_output_buttons()
            else:
                self.smu.output_on(channel)
                self._update_output_buttons()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _update_output_buttons(self):
        """Update output button labels and styles"""
        if self.smu:
            for ch, btn in [("a", self.output_a_btn), ("b", self.output_b_btn)]:
                if self.smu.output_enabled(ch):
                    btn.setText(f"OUT {ch.upper()}: ON")
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #dc2626; color: white;
                            font-family: 'Inter'; font-size: 13px; font-weight: bold;
                            padding: 6px 12px; border-radius: 5px;
                        }
                        QPushButton:hover { background-color: #b91c1c; }
                    """)
                else:
                    btn.setText(f"OUT {ch.upper()}: OFF")
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #14532d; color: #22c55e;
                            font-family: 'Inter'; font-size: 13px; font-weight: bold;
                            padding: 6px 12px; border-radius: 5px; border: 1px solid #16a34a;
                        }
                        QPushButton:hover { background-color: #16a34a; }
                    """)

    def _create_menu(self):
        menubar = self.menuBar()

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

        tools_menu = menubar.addMenu("Tools")
        wave_tool_action = QAction("Wave Generator...", self)
        wave_tool_action.triggered.connect(self._show_wave_tool)
        tools_menu.addAction(wave_tool_action)

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

        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 10)

        # Gradient header bar — green to lime to amber
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #16a34a, stop:0.5 #65a30d, stop:1 #d97706);
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 5, 20, 5)

        header_title = QLabel(__app_name__)
        header_title.setStyleSheet("color: white; font-size: 22px; font-weight: bold; font-family: 'Inter'; background: transparent;")
        header_layout.addWidget(header_title)
        header_layout.addStretch()

        version_label = QLabel(f"v{__version__} | Omer Vered, Hayun Group, BGU")
        version_label.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 12px; font-family: 'Inter'; background: transparent;")
        header_layout.addWidget(version_label)

        layout.addWidget(header)

        # Content area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(15, 10, 15, 0)

        # Top toolbar
        toolbar = QHBoxLayout()

        connect_btn = QPushButton("\U0001f50c Connect")
        connect_btn.clicked.connect(self._show_connection_dialog)
        toolbar.addWidget(connect_btn)

        self.connection_label = QLabel("Disconnected")
        self.connection_label.setStyleSheet("color: #dc2626; font-family: 'Inter'; font-weight: bold; font-size: 15px;")
        toolbar.addWidget(self.connection_label)

        toolbar.addStretch()

        # Channel selector
        ch_label = QLabel("Channel:")
        ch_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        toolbar.addWidget(ch_label)

        self.channel_a_btn = ToggleButton("Ch A")
        self.channel_a_btn.set_selected(True)
        self.channel_a_btn.clicked.connect(lambda: self._set_channel("a"))
        toolbar.addWidget(self.channel_a_btn)

        self.channel_b_btn = ToggleButton("Ch B")
        self.channel_b_btn.clicked.connect(lambda: self._set_channel("b"))
        toolbar.addWidget(self.channel_b_btn)

        # Per-channel output buttons
        self.output_a_btn = QPushButton("OUT A: OFF")
        self.output_a_btn.setStyleSheet("""
            QPushButton {
                background-color: #14532d; color: #22c55e;
                font-family: 'Inter'; font-size: 13px; font-weight: bold;
                padding: 6px 12px; border-radius: 5px; border: 1px solid #16a34a;
            }
            QPushButton:hover { background-color: #16a34a; }
        """)
        self.output_a_btn.clicked.connect(lambda: self._toggle_output("a"))
        toolbar.addWidget(self.output_a_btn)

        self.output_b_btn = QPushButton("OUT B: OFF")
        self.output_b_btn.setStyleSheet("""
            QPushButton {
                background-color: #14532d; color: #22c55e;
                font-family: 'Inter'; font-size: 13px; font-weight: bold;
                padding: 6px 12px; border-radius: 5px; border: 1px solid #16a34a;
            }
            QPushButton:hover { background-color: #16a34a; }
        """)
        self.output_b_btn.clicked.connect(lambda: self._toggle_output("b"))
        toolbar.addWidget(self.output_b_btn)

        toolbar.addStretch()

        self.start_btn = QPushButton("\u25b6 START SWEEP")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745; color: white;
                font-family: 'Inter'; font-size: 18px; font-weight: bold;
                padding: 12px 35px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #218838; }
            QPushButton:disabled { background-color: #374151; color: #4b5563; }
        """)
        self.start_btn.clicked.connect(self.start_sweep)
        toolbar.addWidget(self.start_btn)

        self.stop_btn = QPushButton("\u25a0 STOP")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545; color: white;
                font-family: 'Inter'; font-size: 18px; font-weight: bold;
                padding: 12px 35px; border-radius: 5px;
            }
            QPushButton:hover { background-color: #c82333; }
            QPushButton:disabled { background-color: #374151; color: #4b5563; }
        """)
        self.stop_btn.clicked.connect(self.stop_sweep)
        self.stop_btn.setEnabled(False)
        toolbar.addWidget(self.stop_btn)

        export_btn = QPushButton("\U0001f4be Export CSV")
        export_btn.clicked.connect(self.export_csv)
        toolbar.addWidget(export_btn)

        content_layout.addLayout(toolbar)

        # Main tabs
        tabs = QTabWidget()

        # Tab 1: Multimeter
        self.multimeter_panel = MultimeterPanel(self)
        tabs.addTab(self.multimeter_panel, "\U0001f52c Multimeter")

        # Tab 2: I-V Sweep
        sweep_tab = QWidget()
        sweep_outer = QVBoxLayout(sweep_tab)
        sweep_outer.setContentsMargins(0, 0, 0, 0)

        # Use QSplitter for responsive 3-column layout
        sweep_splitter = QSplitter(Qt.Horizontal)

        # Left panel: Settings
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(200)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)

        self.source_settings = SourceSettingsWidget()
        left_layout.addWidget(self.source_settings)

        self.inst_settings = InstrumentSettingsWidget()
        left_layout.addWidget(self.inst_settings)

        self.measure_settings = MeasureSettingsWidget()
        left_layout.addWidget(self.measure_settings)

        self.timing_settings = TimingSettingsWidget()
        left_layout.addWidget(self.timing_settings)

        left_layout.addStretch()
        left_scroll.setWidget(left_panel)
        sweep_splitter.addWidget(left_scroll)

        # Middle panel: Sweep list
        self.sweep_list = SweepListWidget()
        self.sweep_list.setMinimumWidth(200)
        self.sweep_list.wave_generator_requested.connect(self._show_wave_tool)
        sweep_splitter.addWidget(self.sweep_list)

        # Right panel: Graph and Table
        right_splitter = QSplitter(Qt.Vertical)

        graph_widget = QWidget()
        graph_layout = QVBoxLayout(graph_widget)
        graph_layout.setContentsMargins(0, 0, 0, 0)

        axis_layout = QHBoxLayout()

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
            btn.setMinimumWidth(55)
            btn.setMaximumWidth(70)
            btn.clicked.connect(lambda checked, x=x, y1=y1, y2=y2: self._set_graph_preset(x, y1, y2))
            axis_layout.addWidget(btn)

        axis_layout.addStretch()

        self.live_update_cb = QCheckBox("Live Update")
        self.live_update_cb.setChecked(True)
        axis_layout.addWidget(self.live_update_cb)

        graph_layout.addLayout(axis_layout)

        self.graph = DualAxisGraph()
        graph_layout.addWidget(self.graph)

        right_splitter.addWidget(graph_widget)

        self.table = DataTableWidget()
        right_splitter.addWidget(self.table)

        right_splitter.setSizes([500, 300])
        sweep_splitter.addWidget(right_splitter)

        sweep_splitter.setSizes([250, 250, 750])
        sweep_splitter.setStretchFactor(0, 1)
        sweep_splitter.setStretchFactor(1, 1)
        sweep_splitter.setStretchFactor(2, 3)
        sweep_outer.addWidget(sweep_splitter)

        tabs.addTab(sweep_tab, "\U0001f4ca I-V Sweep")

        content_layout.addWidget(tabs)
        layout.addWidget(content)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("font-family: 'Inter'; color: #9ca3af;")
        self.status.addPermanentWidget(self.progress_label)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(200)
        self.progress.setFormat("%v / %m")
        self.status.addPermanentWidget(self.progress)
        self.status.showMessage("Ready")

        self.sweep_start_time = 0
        self.total_sweep_points = 0

    def _setup_signals(self):
        self.measurement_update.connect(self._on_measurement_update)
        self.sweep_list.list_changed.connect(self._on_sweep_list_changed)

    def _on_sweep_list_changed(self, count: int):
        if count > 0:
            self.timing_settings.points.setValue(count)

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
        self.connection_label.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 15px;")
        self._update_output_buttons()
        self.status.showMessage("Disconnected")

    def _reset_instrument(self):
        if self.smu:
            self.smu.reset()
            self._update_output_buttons()
            self.status.showMessage("Instrument reset")

    def _show_safety_dialog(self):
        dialog = SafetyDialog(self, self.safety_limits)
        if dialog.exec_() == QDialog.Accepted:
            self.safety_limits = dialog.get_limits()
            self.status.showMessage(f"Safety limits updated: \u00b1{self.safety_limits.max_voltage}V, \u00b1{self.safety_limits.max_current}A")

    def _check_license_agreement(self) -> bool:
        license_accepted = self.settings.value("license_accepted", False, type=bool)
        license_version = self.settings.value("license_version", "", type=str)
        if license_accepted and license_version == __version__:
            return True
        dialog = LicenseDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.settings.setValue("license_accepted", True)
            self.settings.setValue("license_version", __version__)
            return True
        return False

    def _show_about(self):
        about_text = f"""
        <h2>{__app_name__}</h2>
        <p><b>Version:</b> {__version__}</p>
        <p><b>Author:</b> {__author__}</p>
        <p><b>Organization:</b> {__organization__}</p>
        <p>{__copyright__}</p>
        <hr>
        <p>Professional Keithley 2602B Dual-Channel SMU Control and I-V Characterization Software</p>
        <p><b>Features:</b></p>
        <ul>
        <li>Dual independent channels (A & B)</li>
        <li>Live multimeter mode with digital displays</li>
        <li>I-V sweep characterization (Linear, List, Log)</li>
        <li>2-Wire/4-Wire sensing</li>
        <li>Dual Y-axis graphing with presets</li>
        <li>Full safety protection</li>
        <li>Configuration save/load</li>
        </ul>
        <hr>
        <p><small>Built with PyQt5 + pyqtgraph | TSP command interface</small></p>
        """
        QMessageBox.about(self, f"About {__app_name__}", about_text)

    def _toggle_auto_save(self, enabled):
        self.auto_save_enabled = enabled
        self.status.showMessage(f"Auto-save {'enabled' if enabled else 'disabled'}")

    def _set_auto_save_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Auto-Save Folder", self.auto_save_path)
        if folder:
            self.auto_save_path = folder
            self.status.showMessage(f"Auto-save folder: {folder}")

    def _open_auto_save_folder(self):
        if not os.path.exists(self.auto_save_path):
            os.makedirs(self.auto_save_path, exist_ok=True)
        if sys.platform == 'darwin':
            os.system(f'open "{self.auto_save_path}"')
        elif sys.platform == 'win32':
            os.startfile(self.auto_save_path)
        else:
            os.system(f'xdg-open "{self.auto_save_path}"')

    def _show_wave_tool(self):
        dialog = WaveToolDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            wave_values = dialog.get_waveform_values()
            if wave_values:
                self.sweep_list.sweep_values = wave_values
                self.sweep_list._update_table()
                self.status.showMessage(f"Imported {len(wave_values)} points from Wave Generator")

    def _import_sweep_list(self):
        self.sweep_list._import_csv()

    def _save_config(self):
        file, _ = QFileDialog.getSaveFileName(self, "Save Configuration", "", "JSON Files (*.json)")
        if file:
            config = {
                "source": {
                    "function": self.source_settings.function,
                    "mode": self.source_settings.mode.currentText(),
                    "compliance": self.source_settings.compliance.value()
                },
                "instrument": {
                    "sense": self.inst_settings.sense,
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
                self.source_settings._set_function(config["source"].get("function", "Voltage"))
                self.source_settings.mode.setCurrentText(config["source"].get("mode", "List Sweep"))
                self.source_settings.compliance.setValue(config["source"].get("compliance", 0.1))

            if "instrument" in config:
                self.inst_settings._set_sense(config["instrument"].get("sense", "2-Wire"))
                self.inst_settings.output_off_mode.setCurrentText(config["instrument"].get("output_off", "Normal"))

            if "timing" in config:
                self.timing_settings.points.setValue(config["timing"].get("points", 51))
                self.timing_settings.repeat.setValue(config["timing"].get("repeat", 1))
                self.timing_settings.delay.setValue(config["timing"].get("delay", 0.05))
                self.timing_settings.nplc.setValue(config["timing"].get("nplc", 1.0))

            if "safety" in config:
                self.safety_limits = SafetyLimits(
                    max_voltage=config["safety"].get("max_voltage", 40),
                    min_voltage=config["safety"].get("min_voltage", -40),
                    max_current=config["safety"].get("max_current", 3.0),
                    min_current=config["safety"].get("min_current", -3.0),
                    power_limit=config["safety"].get("power_limit", 40.4)
                )

            self.status.showMessage(f"Configuration loaded from {file}")

    def connect_instrument(self, resource: Optional[str], simulate: bool = False,
                          simulation_resistance: float = 1000.0):
        self.smu = Keithley2602B(
            resource_name=resource,
            safety_limits=self.safety_limits,
            simulate=simulate,
            simulation_resistance=simulation_resistance
        )
        self.smu.connect()

        if simulate:
            res_str = f"{simulation_resistance:.0f}\u03a9" if simulation_resistance < 1000 else f"{simulation_resistance/1000:.0f}k\u03a9"
            self.connection_label.setText(f"SIM ({res_str})")
            self.connection_label.setStyleSheet("color: #17a2b8; font-weight: bold;")
        else:
            self.connection_label.setText("Connected")
            self.connection_label.setStyleSheet("color: #22c55e; font-weight: bold;")

        self._update_output_buttons()
        self.status.showMessage("Connected to instrument")

    def start_sweep(self):
        if not self.smu:
            QMessageBox.warning(self, "Not Connected", "Please connect to instrument first")
            return

        mode = self.source_settings.mode.currentText()
        ch = self.current_channel

        if mode == "List Sweep":
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

        thread = threading.Thread(target=self._run_sweep, args=(sweep_values, ch))
        thread.daemon = True
        thread.start()

    def _run_sweep(self, sweep_values: List[float], channel: str):
        try:
            function = self.source_settings.function
            compliance = self.source_settings.compliance.value()
            delay = self.timing_settings.delay.value()
            nplc = self.timing_settings.nplc.value()
            repeat = self.timing_settings.repeat.value()

            # Configure source
            if function == "Voltage":
                self.smu.set_source_voltage(sweep_values[0], compliance_current=compliance, channel=channel)
            else:
                self.smu.set_source_current(sweep_values[0], compliance_voltage=compliance, channel=channel)

            # Set NPLC
            self.smu.set_nplc(nplc, channel)

            # Apply sense mode
            sense = self.inst_settings.sense
            if sense == "4-Wire":
                self.smu.set_sense_mode(SenseMode.FOUR_WIRE, channel)
            else:
                self.smu.set_sense_mode(SenseMode.TWO_WIRE, channel)

            self.smu.output_on(channel)
            # Update output buttons from main thread
            self.measurement_update.emit(None)  # Will be handled

            point_num = 0
            start_time = time.time()

            for rep in range(repeat):
                if self.abort_flag:
                    break

                for source_val in sweep_values:
                    if self.abort_flag:
                        break

                    point_num += 1
                    elapsed = time.time() - start_time

                    # Set source
                    if function == "Voltage":
                        self.smu.set_voltage(source_val, channel)
                    else:
                        self.smu.set_current(source_val, channel)

                    time.sleep(delay)

                    # Simulate NPLC time in simulation mode
                    if self.smu.simulate:
                        nplc_time = nplc * 0.020
                        overhead = 0.060
                        time.sleep(nplc_time + overhead)

                    # Measure
                    voltage = None
                    current = None
                    resistance = None
                    power = None

                    if self.measure_settings.measure_v.isChecked():
                        voltage = self.smu.measure_voltage(channel)

                    if self.measure_settings.measure_i.isChecked():
                        current = self.smu.measure_current(channel)

                    if self.measure_settings.measure_r.isChecked() and voltage and current:
                        if abs(current) > 1e-12:
                            resistance = voltage / current

                    if self.measure_settings.measure_p.isChecked() and voltage and current:
                        power = abs(voltage * current)

                    computer_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                    point = MeasurementPoint(
                        index=point_num,
                        timestamp=elapsed,
                        source_value=source_val,
                        channel=channel,
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
                self.smu.output_off(channel)

    def _on_measurement_update(self, point):
        if point is None:
            # Output state update request
            self._update_output_buttons()
            return

        self.table.add_point(point)
        self.graph.add_point(point)

        if self.live_update_cb.isChecked():
            self.graph.update_live()

        self.progress.setValue(point.index)

        elapsed = time.time() - self.sweep_start_time
        if point.index > 0 and self.total_sweep_points > point.index:
            time_per_point = elapsed / point.index
            remaining_points = self.total_sweep_points - point.index
            remaining_sec = remaining_points * time_per_point
            mins, secs = divmod(int(remaining_sec), 60)
            self.progress_label.setText(f"{point.index} / {self.total_sweep_points} | Est: {mins:02d}:{secs:02d}")
        else:
            self.progress_label.setText(f"{point.index} / {self.total_sweep_points}")

        v_str = f"{point.voltage:.6f}V" if point.voltage else ""
        i_str = f"{point.current:.4e}A" if point.current else ""
        self.status.showMessage(f"Ch {point.channel.upper()} | Point {point.index}: {point.source_value:.4f} \u2192 {v_str} {i_str}")

        if not self.running:
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.graph.update_live()
            self._update_output_buttons()
            total_time = time.time() - self.sweep_start_time
            mins, secs = divmod(int(total_time), 60)
            self.progress_label.setText(f"Done: {self.total_sweep_points} pts in {mins:02d}:{secs:02d}")
            self.status.showMessage("Sweep completed")

            if self.auto_save_enabled and self.measurement_data:
                self._auto_save_csv()

    def stop_sweep(self):
        self.abort_flag = True
        if self.smu:
            self.smu.output_off(self.current_channel)
        self._update_output_buttons()
        self.status.showMessage("Stopping...")

    def _generate_filename(self) -> str:
        if self.run_start_datetime:
            date_str = self.run_start_datetime.strftime("%Y-%m-%d")
            time_str = self.run_start_datetime.strftime("%H-%M-%S")
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
            time_str = datetime.now().strftime("%H-%M-%S")
        return f"Run{self.run_number}_{date_str}_{time_str}.csv"

    def _auto_save_csv(self):
        try:
            os.makedirs(self.auto_save_path, exist_ok=True)
            filename = self._generate_filename()
            filepath = os.path.join(self.auto_save_path, filename)
            self._write_csv(filepath)
            self.status.showMessage(f"Auto-saved: {filename}")
        except Exception as e:
            print(f"Auto-save error: {e}")
            self.status.showMessage(f"Auto-save failed: {e}")

    def _write_csv(self, filepath: str):
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([f'# Run {self.run_number}'])
            if self.run_start_datetime:
                writer.writerow([f'# Started: {self.run_start_datetime.strftime("%Y-%m-%d %H:%M:%S")}'])
            writer.writerow([f'# Points: {len(self.measurement_data)}'])
            writer.writerow([])
            writer.writerow(['Index', 'Channel', 'Computer_Time', 'Elapsed(s)', 'Voltage(V)', 'Current(A)', 'Resistance(Ohm)', 'Power(W)'])
            for p in self.measurement_data:
                writer.writerow([
                    p.index,
                    p.channel.upper(),
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

    def closeEvent(self, event):
        self.multimeter_panel.stop_live()
        if self.smu:
            try:
                self.smu.output_off("a")
                self.smu.output_off("b")
            except:
                pass
            self.smu.disconnect()
        event.accept()


# Global stylesheet for dark theme with green/amber accents
GLOBAL_STYLESHEET = """
    * {
        font-family: 'Inter', sans-serif;
        color: #e5e7eb;
    }
    QMainWindow, QWidget {
        background-color: #1a1a2e;
        color: #e5e7eb;
    }
    QLabel {
        font-size: 14px;
        color: #e5e7eb;
        font-weight: 500;
    }
    QPushButton {
        font-size: 14px;
        color: #22c55e;
        background-color: #14532d;
        border: 1px solid #16a34a;
        padding: 6px 14px;
        border-radius: 5px;
        font-weight: 500;
    }
    QPushButton:hover {
        background-color: #16a34a;
        border-color: #22c55e;
    }
    QPushButton:disabled {
        background-color: #374151;
        color: #4b5563;
        border-color: #374151;
    }
    QCheckBox, QRadioButton {
        font-size: 14px;
        color: #e5e7eb;
        font-weight: 500;
    }
    QCheckBox:disabled, QRadioButton:disabled {
        color: #4b5563;
    }
    QGroupBox {
        font-size: 16px;
        font-weight: bold;
        color: #e5e7eb;
        border: 2px solid #374151;
        border-radius: 8px;
        margin-top: 16px;
        padding-top: 12px;
        background-color: transparent;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 10px;
        color: #22c55e;
        background-color: #1a1a2e;
        font-size: 18px;
        font-weight: bold;
    }
    QTableWidget, QListWidget {
        font-size: 13px;
        color: #e5e7eb;
        background-color: #1e2a45;
        border: 1px solid #374151;
    }
    QTableWidget::item, QListWidget::item {
        color: #e5e7eb;
    }
    QHeaderView::section {
        background-color: #14532d;
        color: #22c55e;
        font-weight: bold;
        padding: 8px;
        border: 1px solid #374151;
    }
    QToolTip {
        font-size: 13px;
        background-color: #14532d;
        color: #ffffff;
        border: 1px solid #22c55e;
        padding: 6px;
    }
    QMenuBar {
        font-size: 14px;
        background-color: #1a1a2e;
        color: #e5e7eb;
        border-bottom: 1px solid #374151;
    }
    QMenuBar::item {
        color: #e5e7eb;
    }
    QMenuBar::item:selected {
        background-color: #1f3460;
    }
    QMenu {
        font-size: 14px;
        background-color: #16213e;
        color: #e5e7eb;
        border: 1px solid #374151;
    }
    QMenu::item {
        color: #e5e7eb;
        padding: 6px 20px;
    }
    QMenu::item:selected {
        background-color: #22c55e;
        color: #ffffff;
    }
    QTabWidget::pane {
        border: 1px solid #374151;
        background-color: #1a1a2e;
    }
    QTabBar::tab {
        font-size: 15px;
        padding: 12px 20px;
        background-color: #78350f;
        color: #f59e0b;
        border: 1px solid #374151;
        border-bottom: none;
        margin-right: 2px;
        font-weight: 500;
    }
    QTabBar::tab:selected {
        background-color: #1a1a2e;
        color: #22c55e;
        font-weight: bold;
        border-color: #374151;
    }
    QTabBar::tab:hover {
        background-color: #1f3460;
    }
    QComboBox {
        font-size: 14px;
        color: #e5e7eb;
        background-color: #1e2a45;
        border: 1px solid rgba(245, 158, 11, 0.38);
        padding: 6px 10px;
        border-radius: 5px;
    }
    QComboBox:hover {
        border-color: #f59e0b;
    }
    QComboBox:disabled {
        background-color: #16213e;
        color: #4b5563;
    }
    QComboBox QAbstractItemView {
        background-color: #16213e;
        color: #e5e7eb;
        selection-background-color: #22c55e;
        selection-color: #ffffff;
    }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 25px;
        border-left: 1px solid rgba(245, 158, 11, 0.38);
        border-top-right-radius: 4px;
        border-bottom-right-radius: 4px;
        background-color: #16213e;
    }
    QComboBox::drop-down:hover {
        background-color: #1f3460;
    }
    QComboBox::down-arrow {
        width: 12px;
        height: 12px;
        border: none;
        border-left: 3px solid transparent;
        border-right: 3px solid transparent;
        border-top: 5px solid #e5e7eb;
        margin-top: 2px;
    }
    QSpinBox, QDoubleSpinBox {
        font-size: 14px;
        color: #e5e7eb;
        background-color: #1e2a45;
        border: 1px solid rgba(245, 158, 11, 0.38);
        padding: 6px 8px;
        padding-right: 24px;
        border-radius: 5px;
        min-width: 60px;
    }
    QSpinBox:hover, QDoubleSpinBox:hover {
        border-color: #f59e0b;
    }
    QSpinBox:disabled, QDoubleSpinBox:disabled {
        background-color: #16213e;
        color: #4b5563;
    }
    QSpinBox::up-button, QDoubleSpinBox::up-button {
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 22px;
        border-left: 1px solid rgba(245, 158, 11, 0.38);
        border-bottom: 1px solid rgba(245, 158, 11, 0.38);
        border-top-right-radius: 4px;
        background-color: #16213e;
    }
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
        background-color: #1f3460;
    }
    QSpinBox::down-button, QDoubleSpinBox::down-button {
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 22px;
        border-left: 1px solid rgba(245, 158, 11, 0.38);
        border-bottom-right-radius: 4px;
        background-color: #16213e;
    }
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
        background-color: #1f3460;
    }
    QScrollBar:vertical {
        background-color: #16213e;
        width: 12px;
        border-radius: 6px;
    }
    QScrollBar::handle:vertical {
        background-color: #374151;
        border-radius: 6px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #4b5563;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        background-color: #16213e;
        height: 12px;
        border-radius: 6px;
    }
    QScrollBar::handle:horizontal {
        background-color: #374151;
        border-radius: 6px;
        min-width: 30px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #4b5563;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    QStatusBar {
        background-color: #1a1a2e;
        color: #22c55e;
        border-top: 1px solid #374151;
    }
    QProgressBar {
        border: 1px solid #374151;
        border-radius: 4px;
        background-color: #14532d;
        text-align: center;
        color: #e5e7eb;
        font-weight: bold;
    }
    QProgressBar::chunk {
        background-color: #22c55e;
        border-radius: 3px;
    }
"""


def main():
    app = QApplication(sys.argv)
    app.setPalette(LightPalette())
    app.setStyle('Fusion')

    font = QFont("Inter", 13)
    app.setFont(font)

    app.setStyleSheet(GLOBAL_STYLESHEET)

    window = Keithley2602BApp()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
