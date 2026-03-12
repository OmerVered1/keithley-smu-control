"""
Keithley 2450 I-V Characterizer Control Program
================================================
Full-featured GUI control application matching KickStart functionality.
Includes List Sweep, DC/Pulse modes, and comprehensive measurement settings.

Author: Control Program
Date: 2026
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import csv
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import queue

# Import matplotlib for plotting
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt
import numpy as np

# Import our driver
from keithley2450_driver import (
    Keithley2450, 
    SafetyLimits, 
    MeasurementResult,
    SourceFunction,
    MeasureFunction,
    SenseMode,
    Keithley2450Error
)


class SourceMode(Enum):
    """Source modes"""
    LINEAR_SWEEP = "Linear Sweep"
    LIST_SWEEP = "List Sweep"
    LOG_SWEEP = "Log Sweep"
    CONSTANT = "Constant"


class SourceType(Enum):
    """Source types"""
    DC = "DC"
    PULSE = "Pulse"


class OutputOffMode(Enum):
    """Output off behavior"""
    NORMAL = "Normal"
    ZERO = "Zero"
    HIGH_Z = "High-Z"
    GUARD = "Guard"


@dataclass
class SweepSettings:
    """Sweep configuration"""
    mode: SourceMode = SourceMode.LINEAR_SWEEP
    source_type: SourceType = SourceType.DC
    function: SourceFunction = SourceFunction.VOLTAGE
    
    # Linear sweep
    start: float = 0.0
    stop: float = 5.0
    points: int = 50
    
    # List sweep
    voltage_list: List[float] = field(default_factory=list)
    
    # Common
    compliance: float = 1.0
    range_mode: str = "Auto"
    
    # Timing
    source_delay: float = 0.05  # seconds
    measure_delay: float = 0.0  # seconds
    
    # Repeat
    repeat: int = 1


@dataclass 
class MeasureSettings:
    """Measurement configuration"""
    measure_voltage: bool = True
    measure_current: bool = True
    measure_power: bool = True
    measure_resistance: bool = True
    
    range_mode: str = "Auto"
    minimum_range: str = "10 nA"
    auto_zero: str = "On"
    nplc: float = 1.0
    measure_window: float = 0.020  # 20 ms


@dataclass
class InstrumentSettings:
    """Instrument configuration"""
    terminals: str = "Rear"  # Front or Rear
    sense_mode: str = "4-Wire"  # 2-Wire or 4-Wire
    high_capacitance: bool = False
    output_off_mode: str = "Normal"


@dataclass
class MeasurementDataPoint:
    """Single measurement data point"""
    index: int
    timestamp: float
    source_value: float
    voltage: Optional[float] = None
    current: Optional[float] = None
    resistance: Optional[float] = None
    power: Optional[float] = None


class ModernStyle:
    """Modern color scheme matching KickStart"""
    # Colors - KickStart style (light theme)
    BG_MAIN = "#f0f0f0"
    BG_PANEL = "#ffffff"
    BG_HEADER = "#003366"  # Dark blue header
    BG_SELECTED = "#4a90d9"  # Blue selection
    BG_INPUT = "#ffffff"
    
    TEXT_PRIMARY = "#000000"
    TEXT_SECONDARY = "#666666"
    TEXT_HEADER = "#ffffff"
    TEXT_DISABLED = "#999999"
    
    ACCENT_BLUE = "#003366"
    ACCENT_GREEN = "#28a745"
    ACCENT_RED = "#dc3545"
    ACCENT_YELLOW = "#ffc107"
    ACCENT_ORANGE = "#fd7e14"
    
    BUTTON_BG = "#003366"
    BUTTON_FG = "#ffffff"
    
    # Output state colors
    OUTPUT_ON = "#28a745"
    OUTPUT_OFF = "#dc3545"
    
    # Fonts
    FONT_TITLE = ("Segoe UI", 12, "bold")
    FONT_HEADER = ("Segoe UI", 10, "bold")
    FONT_NORMAL = ("Segoe UI", 9)
    FONT_SMALL = ("Segoe UI", 8)
    FONT_MONO = ("Consolas", 10)
    FONT_LARGE_READING = ("Consolas", 20, "bold")
    FONT_MEDIUM_READING = ("Consolas", 14)


class InstrumentPanel(ttk.LabelFrame):
    """Left panel showing instrument info and controls"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="", padding=5)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Instrument header with checkbox
        header_frame = tk.Frame(self, bg=ModernStyle.BG_HEADER)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.inst_enabled = tk.BooleanVar(value=True)
        self.inst_check = tk.Checkbutton(header_frame, variable=self.inst_enabled,
                                         bg=ModernStyle.BG_HEADER, fg=ModernStyle.TEXT_HEADER,
                                         selectcolor=ModernStyle.BG_HEADER,
                                         activebackground=ModernStyle.BG_HEADER)
        self.inst_check.pack(side=tk.LEFT, padx=5)
        
        self.inst_name = tk.Label(header_frame, text="SMU-1", 
                                  bg=ModernStyle.BG_HEADER, fg=ModernStyle.TEXT_HEADER,
                                  font=ModernStyle.FONT_HEADER)
        self.inst_name.pack(side=tk.LEFT)
        
        # Instrument info
        info_frame = tk.Frame(self, bg=ModernStyle.BG_HEADER)
        info_frame.pack(fill=tk.X)
        
        self.info_labels = []
        info_texts = ["DC Voltage", "List Sweep", "0.0", "Limit: 0.5 A", "Measure: V, A, Ω, W"]
        for text in info_texts:
            lbl = tk.Label(info_frame, text=text, bg=ModernStyle.BG_HEADER, 
                          fg=ModernStyle.TEXT_HEADER, font=ModernStyle.FONT_SMALL,
                          anchor=tk.W)
            lbl.pack(fill=tk.X, padx=10)
            self.info_labels.append(lbl)
        
        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.add_btn = tk.Button(btn_frame, text="Add\nInstrument",
                                bg=ModernStyle.BUTTON_BG, fg=ModernStyle.BUTTON_FG,
                                font=ModernStyle.FONT_SMALL,
                                command=self._add_instrument)
        self.add_btn.pack(fill=tk.X, pady=2)
        
        self.remove_btn = tk.Button(btn_frame, text="Remove/Swap\nInstrument",
                                   bg=ModernStyle.BUTTON_BG, fg=ModernStyle.BUTTON_FG,
                                   font=ModernStyle.FONT_SMALL,
                                   command=self._remove_instrument)
        self.remove_btn.pack(fill=tk.X, pady=2)
    
    def update_info(self, function: str, mode: str, value: float, limit: float, measures: str):
        """Update instrument info display"""
        self.info_labels[0].config(text=function)
        self.info_labels[1].config(text=mode)
        self.info_labels[2].config(text=f"{value:.6f}")
        self.info_labels[3].config(text=f"Limit: {limit} A")
        self.info_labels[4].config(text=f"Measure: {measures}")
    
    def _add_instrument(self):
        """Add new instrument"""
        resources = Keithley2450.list_available_instruments()
        if not resources:
            messagebox.showinfo("No Instruments", "No VISA instruments found")
            return
        
        # Show connection dialog
        self.app.show_connection_dialog()
    
    def _remove_instrument(self):
        """Remove/swap instrument"""
        if self.app.smu:
            if messagebox.askyesno("Disconnect", "Disconnect from current instrument?"):
                self.app.disconnect_instrument()


class SourcePanel(ttk.LabelFrame):
    """Source configuration panel"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="Source", padding=10)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Type selection (DC / Pulse)
        type_frame = ttk.Frame(self)
        type_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(type_frame, text="Type").pack(side=tk.LEFT, padx=(0, 10))
        
        self.source_type_var = tk.StringVar(value="DC")
        self.dc_btn = tk.Button(type_frame, text="DC", width=8,
                               bg=ModernStyle.BG_SELECTED, fg="white",
                               command=lambda: self._set_type("DC"))
        self.dc_btn.pack(side=tk.LEFT, padx=1)
        
        self.pulse_btn = tk.Button(type_frame, text="Pulse", width=8,
                                  bg=ModernStyle.BG_PANEL,
                                  command=lambda: self._set_type("Pulse"))
        self.pulse_btn.pack(side=tk.LEFT, padx=1)
        
        # Function selection (Voltage / Current)
        func_frame = ttk.Frame(self)
        func_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(func_frame, text="Function").pack(side=tk.LEFT, padx=(0, 10))
        
        self.function_var = tk.StringVar(value="Voltage")
        self.volt_btn = tk.Button(func_frame, text="Voltage", width=8,
                                 bg=ModernStyle.BG_SELECTED, fg="white",
                                 command=lambda: self._set_function("Voltage"))
        self.volt_btn.pack(side=tk.LEFT, padx=1)
        
        self.curr_btn = tk.Button(func_frame, text="Current", width=8,
                                 bg=ModernStyle.BG_PANEL,
                                 command=lambda: self._set_function("Current"))
        self.curr_btn.pack(side=tk.LEFT, padx=1)
        
        # Mode selection
        mode_frame = ttk.Frame(self)
        mode_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(mode_frame, text="Mode").pack(side=tk.LEFT, padx=(0, 10))
        self.mode_var = tk.StringVar(value="List Sweep")
        self.mode_combo = ttk.Combobox(mode_frame, textvariable=self.mode_var,
                                       values=["Constant", "Linear Sweep", "List Sweep", "Log Sweep"],
                                       state="readonly", width=15)
        self.mode_combo.pack(side=tk.LEFT)
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)
        
        # Range selection
        range_frame = ttk.Frame(self)
        range_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(range_frame, text="Range").pack(side=tk.LEFT, padx=(0, 10))
        self.range_var = tk.StringVar(value="Auto")
        self.range_combo = ttk.Combobox(range_frame, textvariable=self.range_var,
                                        values=["Auto", "200 mV", "2 V", "20 V", "200 V"],
                                        state="readonly", width=10)
        self.range_combo.pack(side=tk.LEFT)
        
        # Limit
        limit_frame = ttk.Frame(self)
        limit_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(limit_frame, text="Limit").pack(side=tk.LEFT, padx=(0, 10))
        self.limit_var = tk.StringVar(value="0.5 A")
        self.limit_entry = ttk.Entry(limit_frame, textvariable=self.limit_var, width=12)
        self.limit_entry.pack(side=tk.LEFT)
        
        # Sweep list frame
        self.list_frame = ttk.LabelFrame(self, text="Sweep Values", padding=5)
        self.list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # List table
        columns = ('Index', 'DC Voltage (V)')
        self.list_tree = ttk.Treeview(self.list_frame, columns=columns, 
                                      show='headings', height=6)
        self.list_tree.heading('Index', text='Index')
        self.list_tree.heading('DC Voltage (V)', text='DC Voltage (V)')
        self.list_tree.column('Index', width=50, anchor=tk.CENTER)
        self.list_tree.column('DC Voltage (V)', width=150, anchor=tk.CENTER)
        
        list_scroll = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL, 
                                    command=self.list_tree.yview)
        self.list_tree.configure(yscrollcommand=list_scroll.set)
        
        self.list_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # List buttons
        list_btn_frame = ttk.Frame(self)
        list_btn_frame.pack(fill=tk.X, pady=5)
        
        self.import_btn = tk.Button(list_btn_frame, text="Import File",
                                   bg=ModernStyle.BUTTON_BG, fg=ModernStyle.BUTTON_FG,
                                   command=self._import_list)
        self.import_btn.pack(side=tk.LEFT, padx=2)
        
        self.export_btn = tk.Button(list_btn_frame, text="Export to File",
                                   bg=ModernStyle.BUTTON_BG, fg=ModernStyle.BUTTON_FG,
                                   command=self._export_list)
        self.export_btn.pack(side=tk.LEFT, padx=2)
        
        # Linear sweep frame (hidden by default)
        self.linear_frame = ttk.LabelFrame(self, text="Linear Sweep Settings", padding=5)
        
        ttk.Label(self.linear_frame, text="Start:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.start_var = tk.StringVar(value="0")
        ttk.Entry(self.linear_frame, textvariable=self.start_var, width=12).grid(row=0, column=1)
        ttk.Label(self.linear_frame, text="V").grid(row=0, column=2, sticky=tk.W)
        
        ttk.Label(self.linear_frame, text="Stop:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.stop_var = tk.StringVar(value="5")
        ttk.Entry(self.linear_frame, textvariable=self.stop_var, width=12).grid(row=1, column=1)
        ttk.Label(self.linear_frame, text="V").grid(row=1, column=2, sticky=tk.W)
        
        # Generate list button
        self.gen_btn = ttk.Button(self, text="Generate List from Settings",
                                 command=self._generate_list)
        self.gen_btn.pack(fill=tk.X, pady=5)
    
    def _set_type(self, type_name: str):
        """Set source type (DC/Pulse)"""
        self.source_type_var.set(type_name)
        if type_name == "DC":
            self.dc_btn.config(bg=ModernStyle.BG_SELECTED, fg="white")
            self.pulse_btn.config(bg=ModernStyle.BG_PANEL, fg="black")
        else:
            self.dc_btn.config(bg=ModernStyle.BG_PANEL, fg="black")
            self.pulse_btn.config(bg=ModernStyle.BG_SELECTED, fg="white")
    
    def _set_function(self, func_name: str):
        """Set source function (Voltage/Current)"""
        self.function_var.set(func_name)
        if func_name == "Voltage":
            self.volt_btn.config(bg=ModernStyle.BG_SELECTED, fg="white")
            self.curr_btn.config(bg=ModernStyle.BG_PANEL, fg="black")
            self.list_tree.heading('DC Voltage (V)', text='DC Voltage (V)')
            self.limit_var.set("0.5 A")
        else:
            self.volt_btn.config(bg=ModernStyle.BG_PANEL, fg="black")
            self.curr_btn.config(bg=ModernStyle.BG_SELECTED, fg="white")
            self.list_tree.heading('DC Voltage (V)', text='DC Current (A)')
            self.limit_var.set("20 V")
    
    def _on_mode_change(self, event=None):
        """Handle mode change"""
        mode = self.mode_var.get()
        if mode == "List Sweep":
            self.list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
            self.linear_frame.pack_forget()
        elif mode in ["Linear Sweep", "Log Sweep"]:
            self.list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
            self.linear_frame.pack(fill=tk.X, pady=5, before=self.list_frame)
        else:  # Constant
            self.list_frame.pack_forget()
            self.linear_frame.pack_forget()
    
    def _generate_list(self):
        """Generate sweep list from settings"""
        try:
            mode = self.mode_var.get()
            points = int(self.app.common_panel.points_var.get())
            start = float(self.start_var.get())
            stop = float(self.stop_var.get())
            
            if mode == "Linear Sweep":
                values = np.linspace(start, stop, points)
            elif mode == "Log Sweep":
                if start <= 0 or stop <= 0:
                    messagebox.showerror("Error", "Log sweep requires positive values")
                    return
                values = np.logspace(np.log10(start), np.log10(stop), points)
            else:
                values = np.linspace(start, stop, points)
            
            self._populate_list(values)
            
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid values: {e}")
    
    def _populate_list(self, values: List[float]):
        """Populate sweep list"""
        # Clear existing
        for item in self.list_tree.get_children():
            self.list_tree.delete(item)
        
        # Add new values
        for i, val in enumerate(values, 1):
            self.list_tree.insert('', 'end', values=(i, f"{val:.14g}"))
    
    def _import_list(self):
        """Import sweep list from file"""
        filename = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not filename:
            return
        
        try:
            values = []
            with open(filename, 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row:
                        try:
                            values.append(float(row[0]))
                        except ValueError:
                            continue
            
            if values:
                self._populate_list(values)
                self.app.common_panel.points_var.set(str(len(values)))
                messagebox.showinfo("Import Complete", f"Imported {len(values)} values")
            else:
                messagebox.showwarning("Import", "No valid values found in file")
                
        except Exception as e:
            messagebox.showerror("Import Error", str(e))
    
    def _export_list(self):
        """Export sweep list to file"""
        items = self.list_tree.get_children()
        if not items:
            messagebox.showwarning("Export", "No values to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt")]
        )
        if not filename:
            return
        
        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                for item in items:
                    values = self.list_tree.item(item)['values']
                    writer.writerow([values[1]])
            
            messagebox.showinfo("Export Complete", f"Exported to {filename}")
            
        except Exception as e:
            messagebox.showerror("Export Error", str(e))
    
    def get_sweep_values(self) -> List[float]:
        """Get sweep values from list"""
        values = []
        for item in self.list_tree.get_children():
            val = self.list_tree.item(item)['values'][1]
            values.append(float(val))
        return values


class MeasurePanel(ttk.LabelFrame):
    """Measurement configuration panel"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="Measure", padding=10)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Measurement checkboxes
        check_frame = ttk.Frame(self)
        check_frame.pack(fill=tk.X, pady=5)
        
        self.measure_voltage = tk.BooleanVar(value=True)
        self.measure_current = tk.BooleanVar(value=True)
        self.measure_power = tk.BooleanVar(value=True)
        self.measure_resistance = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(check_frame, text="Voltage", 
                       variable=self.measure_voltage).grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(check_frame, text="Current",
                       variable=self.measure_current).grid(row=1, column=0, sticky=tk.W)
        ttk.Checkbutton(check_frame, text="Power",
                       variable=self.measure_power).grid(row=2, column=0, sticky=tk.W)
        ttk.Checkbutton(check_frame, text="Resistance",
                       variable=self.measure_resistance).grid(row=3, column=0, sticky=tk.W)
        
        # Settings frame
        settings_frame = ttk.Frame(self)
        settings_frame.pack(fill=tk.X, pady=5)
        
        # Range
        ttk.Label(settings_frame, text="Range").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.range_var = tk.StringVar(value="Auto")
        ttk.Combobox(settings_frame, textvariable=self.range_var,
                    values=["Auto", "10 nA", "100 nA", "1 µA", "10 µA", "100 µA",
                           "1 mA", "10 mA", "100 mA", "1 A"],
                    state="readonly", width=10).grid(row=0, column=1, pady=2)
        
        # Minimum Range
        ttk.Label(settings_frame, text="Minimum\nRange").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.min_range_var = tk.StringVar(value="10 nA")
        ttk.Combobox(settings_frame, textvariable=self.min_range_var,
                    values=["10 nA", "100 nA", "1 µA", "10 µA", "100 µA",
                           "1 mA", "10 mA", "100 mA"],
                    state="readonly", width=10).grid(row=1, column=1, pady=2)
        
        # Auto Zero
        ttk.Label(settings_frame, text="Auto Zero").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.auto_zero_var = tk.StringVar(value="On")
        ttk.Combobox(settings_frame, textvariable=self.auto_zero_var,
                    values=["On", "Off", "Once"],
                    state="readonly", width=10).grid(row=2, column=1, pady=2)


class InstrumentSettingsPanel(ttk.LabelFrame):
    """Instrument settings panel"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="Instrument Settings", padding=10)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Input Terminals
        term_frame = ttk.Frame(self)
        term_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(term_frame, text="Input Terminals").pack(side=tk.LEFT, padx=(0, 10))
        
        self.terminal_var = tk.StringVar(value="Rear")
        self.front_btn = tk.Button(term_frame, text="Front", width=6,
                                  bg=ModernStyle.BG_PANEL,
                                  command=lambda: self._set_terminal("Front"))
        self.front_btn.pack(side=tk.LEFT, padx=1)
        
        self.rear_btn = tk.Button(term_frame, text="Rear", width=6,
                                 bg=ModernStyle.BG_SELECTED, fg="white",
                                 command=lambda: self._set_terminal("Rear"))
        self.rear_btn.pack(side=tk.LEFT, padx=1)
        
        # Sense mode
        sense_frame = ttk.Frame(self)
        sense_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(sense_frame, text="Sense").pack(side=tk.LEFT, padx=(0, 10))
        
        self.sense_var = tk.StringVar(value="4-Wire")
        self.sense_2w_btn = tk.Button(sense_frame, text="2-Wire", width=6,
                                     bg=ModernStyle.BG_PANEL,
                                     command=lambda: self._set_sense("2-Wire"))
        self.sense_2w_btn.pack(side=tk.LEFT, padx=1)
        
        self.sense_4w_btn = tk.Button(sense_frame, text="4-Wire", width=6,
                                     bg=ModernStyle.BG_SELECTED, fg="white",
                                     command=lambda: self._set_sense("4-Wire"))
        self.sense_4w_btn.pack(side=tk.LEFT, padx=1)
        
        # High Capacitance
        hicap_frame = ttk.Frame(self)
        hicap_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(hicap_frame, text="High\nCapacitance").pack(side=tk.LEFT, padx=(0, 10))
        self.high_cap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(hicap_frame, variable=self.high_cap_var).pack(side=tk.LEFT)
        
        # Output Off
        off_frame = ttk.Frame(self)
        off_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(off_frame, text="Output Off").pack(side=tk.LEFT, padx=(0, 10))
        self.output_off_var = tk.StringVar(value="Normal")
        ttk.Combobox(off_frame, textvariable=self.output_off_var,
                    values=["Normal", "Zero", "High-Z", "Guard"],
                    state="readonly", width=10).pack(side=tk.LEFT)
    
    def _set_terminal(self, term: str):
        """Set terminal selection"""
        self.terminal_var.set(term)
        if term == "Front":
            self.front_btn.config(bg=ModernStyle.BG_SELECTED, fg="white")
            self.rear_btn.config(bg=ModernStyle.BG_PANEL, fg="black")
        else:
            self.front_btn.config(bg=ModernStyle.BG_PANEL, fg="black")
            self.rear_btn.config(bg=ModernStyle.BG_SELECTED, fg="white")
        
        # Apply to instrument
        if self.app.smu:
            try:
                self.app.smu.set_terminal(term.upper())
            except:
                pass
    
    def _set_sense(self, mode: str):
        """Set sense mode"""
        self.sense_var.set(mode)
        if mode == "2-Wire":
            self.sense_2w_btn.config(bg=ModernStyle.BG_SELECTED, fg="white")
            self.sense_4w_btn.config(bg=ModernStyle.BG_PANEL, fg="black")
        else:
            self.sense_2w_btn.config(bg=ModernStyle.BG_PANEL, fg="black")
            self.sense_4w_btn.config(bg=ModernStyle.BG_SELECTED, fg="white")


class CommonSettingsPanel(ttk.LabelFrame):
    """Common settings panel (right side)"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="Common Settings", padding=10)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Source/Sweep Points
        ttk.Label(self, text="Source/Sweep\nPoints").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.points_var = tk.StringVar(value="12000")
        ttk.Entry(self, textvariable=self.points_var, width=12).grid(row=0, column=1, pady=5)
        
        # Repeat
        ttk.Label(self, text="Repeat").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.repeat_var = tk.StringVar(value="1")
        ttk.Entry(self, textvariable=self.repeat_var, width=12).grid(row=1, column=1, pady=5)
        
        # Source to Measure Delay
        ttk.Label(self, text="Source to\nMeasure Delay").grid(row=2, column=0, sticky=tk.W, pady=5)
        delay_frame = ttk.Frame(self)
        delay_frame.grid(row=2, column=1, pady=5)
        self.delay_var = tk.StringVar(value="0.917")
        ttk.Entry(delay_frame, textvariable=self.delay_var, width=8).pack(side=tk.LEFT)
        ttk.Label(delay_frame, text="s").pack(side=tk.LEFT)
        
        # Measure Window
        ttk.Label(self, text="Measure Window").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.window_label = ttk.Label(self, text="20 ms")
        self.window_label.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        # NPLC
        ttk.Label(self, text="NPLC").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.nplc_var = tk.StringVar(value="1")
        ttk.Entry(self, textvariable=self.nplc_var, width=12).grid(row=4, column=1, pady=5)
        
        # Update measure window when NPLC changes
        self.nplc_var.trace_add('write', self._update_window)
    
    def _update_window(self, *args):
        """Update measure window based on NPLC"""
        try:
            nplc = float(self.nplc_var.get())
            # Assuming 50Hz power line, 1 NPLC = 20ms
            window_ms = nplc * 20
            self.window_label.config(text=f"{window_ms:.0f} ms")
        except:
            pass


class TimelinePanel(ttk.Frame):
    """Timeline/progress panel at top"""
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Trigger type label
        ttk.Label(self, text="Trigger Type :  Internal", 
                 font=ModernStyle.FONT_HEADER).pack(anchor=tk.W, pady=5)
        
        # Timeline canvas
        self.canvas = tk.Canvas(self, height=50, bg='white', highlightthickness=1,
                               highlightbackground='gray')
        self.canvas.pack(fill=tk.X, pady=5)
        
        # Draw initial timeline
        self._draw_timeline(0, 0)
    
    def _draw_timeline(self, current: int, total: int):
        """Draw timeline with progress"""
        self.canvas.delete('all')
        width = self.canvas.winfo_width() or 800
        height = 50
        
        # Labels
        self.canvas.create_text(10, 10, text="SMU-1", anchor=tk.W, font=ModernStyle.FONT_SMALL)
        
        # Timeline bar background
        bar_y = 30
        bar_height = 15
        self.canvas.create_rectangle(50, bar_y, width - 20, bar_y + bar_height,
                                    fill='#e0e0e0', outline='gray')
        
        # Progress bar
        if total > 0:
            progress_width = (current / total) * (width - 70)
            self.canvas.create_rectangle(50, bar_y, 50 + progress_width, bar_y + bar_height,
                                        fill='#ffc107', outline='#ffc107')
        
        # Time markers
        for i in range(5):
            x = 50 + i * (width - 70) / 4
            time_val = i * 0.5  # Example time scale
            self.canvas.create_text(x, height - 5, text=f"{time_val}s",
                                   font=ModernStyle.FONT_SMALL)
    
    def update_progress(self, current: int, total: int):
        """Update timeline progress"""
        self.after(0, lambda: self._draw_timeline(current, total))


class DataTablePanel(ttk.Frame):
    """Data table panel"""
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Button bar at top
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=5, padx=5)
        
        self.save_btn = tk.Button(btn_frame, text="💾 Save to CSV",
                                 bg="#28a745", fg="white",
                                 font=("Segoe UI", 10, "bold"),
                                 command=self._save_csv)
        self.save_btn.pack(side=tk.LEFT, padx=5)
        
        self.copy_btn = tk.Button(btn_frame, text="📋 Copy to Clipboard",
                                 bg="#007bff", fg="white",
                                 font=("Segoe UI", 10),
                                 command=self._copy_to_clipboard)
        self.copy_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_btn = tk.Button(btn_frame, text="🗑 Clear Data",
                                  bg="#dc3545", fg="white",
                                  font=("Segoe UI", 10),
                                  command=self._clear_with_confirm)
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Data count label
        self.count_var = tk.StringVar(value="0 data points")
        ttk.Label(btn_frame, textvariable=self.count_var,
                 font=("Segoe UI", 10)).pack(side=tk.RIGHT, padx=10)
        
        # Create treeview with columns
        columns = ('Index', 'Time (s)', 'Source (V)', 'Voltage (V)', 
                  'Current (A)', 'Resistance (Ω)', 'Power (W)')
        
        self.tree = ttk.Treeview(self, columns=columns, show='headings')
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100, anchor=tk.CENTER)
        
        # Scrollbars
        y_scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        
        # Layout
        self.tree.grid(row=1, column=0, sticky='nsew')
        y_scroll.grid(row=1, column=1, sticky='ns')
        x_scroll.grid(row=2, column=0, sticky='ew')
        
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
    
    def _save_csv(self):
        """Save data to CSV file"""
        if not self.tree.get_children():
            messagebox.showwarning("No Data", "No data to save")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"iv_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if filename:
            self.export_data(filename)
            messagebox.showinfo("Saved", f"Data saved to:\n{filename}")
    
    def _copy_to_clipboard(self):
        """Copy data to clipboard"""
        if not self.tree.get_children():
            messagebox.showwarning("No Data", "No data to copy")
            return
        
        # Build tab-separated text
        lines = ["Index\tTime (s)\tSource (V)\tVoltage (V)\tCurrent (A)\tResistance (Ω)\tPower (W)"]
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            lines.append("\t".join(str(v) for v in values))
        
        text = "\n".join(lines)
        
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", f"Copied {len(self.tree.get_children())} data points to clipboard")
    
    def _clear_with_confirm(self):
        """Clear data with confirmation"""
        if self.tree.get_children():
            if messagebox.askyesno("Clear Data", "Are you sure you want to clear all data?"):
                self.clear_data()
                self.app.graph_panel._clear_plot()
    
    def add_data_point(self, point: MeasurementDataPoint):
        """Add data point to table"""
        self.tree.insert('', 'end', values=(
            point.index,
            f"{point.timestamp:.3f}",
            f"{point.source_value:.6f}",
            f"{point.voltage:.6f}" if point.voltage is not None else "---",
            f"{point.current:.9e}" if point.current is not None else "---",
            f"{point.resistance:.2f}" if point.resistance and abs(point.resistance) < 1e9 else "---",
            f"{point.power:.6e}" if point.power is not None else "---"
        ))
        self.tree.yview_moveto(1)
        self.count_var.set(f"{len(self.tree.get_children())} data points")
    
    def clear_data(self):
        """Clear all data"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.count_var.set("0 data points")
    
    def export_data(self, filename: str):
        """Export data to CSV"""
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Index', 'Time (s)', 'Source (V)', 'Voltage (V)',
                           'Current (A)', 'Resistance (Ω)', 'Power (W)'])
            for item in self.tree.get_children():
                writer.writerow(self.tree.item(item)['values'])


class GraphPanel(ttk.Frame):
    """Graph panel with matplotlib - supports live updates and dual Y-axis"""
    
    # Units for each measurement type
    UNITS = {
        "Index": "",
        "Time": "s",
        "Voltage": "V",
        "Current": "A",
        "Resistance": "Ω",
        "Power": "W"
    }
    
    # Colors for dual axis
    COLORS = {
        "Voltage": "#1f77b4",      # Blue
        "Current": "#2ca02c",      # Green
        "Resistance": "#ff7f0e",   # Orange
        "Power": "#d62728"         # Red
    }
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.data_points: List[MeasurementDataPoint] = []
        self.live_update = True  # Auto-update enabled by default
        self.ax2 = None  # Second Y-axis
        self._create_widgets()
    
    def _create_widgets(self):
        # Control frame - Row 1
        ctrl_frame1 = ttk.Frame(self)
        ctrl_frame1.pack(fill=tk.X, pady=5)
        
        ttk.Label(ctrl_frame1, text="X-Axis:").pack(side=tk.LEFT, padx=5)
        self.x_var = tk.StringVar(value="Time")
        x_combo = ttk.Combobox(ctrl_frame1, textvariable=self.x_var,
                    values=["Index", "Time", "Voltage", "Current"],
                    state="readonly", width=10)
        x_combo.pack(side=tk.LEFT)
        x_combo.bind("<<ComboboxSelected>>", lambda e: self._on_axis_change())
        
        ttk.Label(ctrl_frame1, text="Y1-Axis (Left):").pack(side=tk.LEFT, padx=(20, 5))
        self.y1_var = tk.StringVar(value="Current")
        y1_combo = ttk.Combobox(ctrl_frame1, textvariable=self.y1_var,
                    values=["None", "Voltage", "Current", "Resistance", "Power"],
                    state="readonly", width=10)
        y1_combo.pack(side=tk.LEFT)
        y1_combo.bind("<<ComboboxSelected>>", lambda e: self._on_axis_change())
        
        ttk.Label(ctrl_frame1, text="Y2-Axis (Right):").pack(side=tk.LEFT, padx=(20, 5))
        self.y2_var = tk.StringVar(value="None")
        y2_combo = ttk.Combobox(ctrl_frame1, textvariable=self.y2_var,
                    values=["None", "Voltage", "Current", "Resistance", "Power"],
                    state="readonly", width=10)
        y2_combo.pack(side=tk.LEFT)
        y2_combo.bind("<<ComboboxSelected>>", lambda e: self._on_axis_change())
        
        # Control frame - Row 2
        ctrl_frame2 = ttk.Frame(self)
        ctrl_frame2.pack(fill=tk.X, pady=5)
        
        # Live update checkbox
        self.live_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl_frame2, text="Live Update", variable=self.live_var,
                       command=self._toggle_live).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(ctrl_frame2, text="Update Now", command=self._update_plot).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame2, text="Clear", command=self._clear_plot).pack(side=tk.LEFT, padx=5)
        ttk.Button(ctrl_frame2, text="Autoscale", command=self._autoscale).pack(side=tk.LEFT, padx=5)
        
        # Quick presets
        ttk.Label(ctrl_frame2, text="  Presets:").pack(side=tk.LEFT, padx=(20, 5))
        ttk.Button(ctrl_frame2, text="I-V", width=6,
                  command=lambda: self._set_preset("Voltage", "Current", "None")).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_frame2, text="I-t", width=6,
                  command=lambda: self._set_preset("Time", "Current", "None")).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_frame2, text="V,P-t", width=6,
                  command=lambda: self._set_preset("Time", "Voltage", "Power")).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl_frame2, text="I,R-t", width=6,
                  command=lambda: self._set_preset("Time", "Current", "Resistance")).pack(side=tk.LEFT, padx=2)
        
        # Figure with space for dual axis
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self._setup_initial_plot()
        
        self.canvas = FigureCanvasTkAgg(self.fig, self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Toolbar
        toolbar_frame = ttk.Frame(self)
        toolbar_frame.pack(fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()
    
    def _setup_initial_plot(self):
        """Setup initial empty plot"""
        self.ax.set_xlabel('Time (s)')
        self.ax.set_ylabel('Current (A)', color=self.COLORS["Current"])
        self.ax.tick_params(axis='y', labelcolor=self.COLORS["Current"])
        self.ax.set_title('Live Measurement Data')
        self.ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
    
    def _set_preset(self, x: str, y1: str, y2: str):
        """Set axis preset"""
        self.x_var.set(x)
        self.y1_var.set(y1)
        self.y2_var.set(y2)
        self._on_axis_change()
    
    def _toggle_live(self):
        """Toggle live update"""
        self.live_update = self.live_var.get()
    
    def _on_axis_change(self):
        """Handle axis selection change"""
        if self.data_points:
            self._update_plot()
    
    def add_data_point(self, point: MeasurementDataPoint):
        """Add data point and update plot if live"""
        self.data_points.append(point)
        if self.live_update and len(self.data_points) % 10 == 0:  # Update every 10 points for performance
            self._update_plot()
    
    def _get_axis_data(self, axis_name: str) -> List[float]:
        """Get data for specified axis"""
        data = []
        for p in self.data_points:
            if axis_name == "Index":
                data.append(p.index)
            elif axis_name == "Time":
                data.append(p.timestamp)
            elif axis_name == "Voltage":
                data.append(p.voltage if p.voltage is not None else 0)
            elif axis_name == "Current":
                data.append(p.current if p.current is not None else 0)
            elif axis_name == "Resistance":
                if p.resistance and abs(p.resistance) < 1e9:
                    data.append(p.resistance)
                else:
                    data.append(float('nan'))
            elif axis_name == "Power":
                data.append(p.power if p.power is not None else 0)
        return data
    
    def _format_axis_label(self, name: str) -> str:
        """Format axis label with units"""
        unit = self.UNITS.get(name, "")
        if unit:
            return f"{name} ({unit})"
        return name
    
    def _update_plot(self):
        """Update plot with current data"""
        if not self.data_points:
            return
        
        # Get settings
        x_name = self.x_var.get()
        y1_name = self.y1_var.get()
        y2_name = self.y2_var.get()
        
        # Clear existing plots
        self.ax.clear()
        if self.ax2:
            self.ax2.remove()
            self.ax2 = None
        
        x_data = self._get_axis_data(x_name)
        
        # Plot Y1 (left axis)
        if y1_name != "None":
            y1_data = self._get_axis_data(y1_name)
            color1 = self.COLORS.get(y1_name, "#1f77b4")
            self.ax.plot(x_data, y1_data, '.-', color=color1, markersize=2, linewidth=1, label=y1_name)
            self.ax.set_ylabel(self._format_axis_label(y1_name), color=color1)
            self.ax.tick_params(axis='y', labelcolor=color1)
        
        # Plot Y2 (right axis)
        if y2_name != "None":
            self.ax2 = self.ax.twinx()
            y2_data = self._get_axis_data(y2_name)
            color2 = self.COLORS.get(y2_name, "#d62728")
            self.ax2.plot(x_data, y2_data, '.-', color=color2, markersize=2, linewidth=1, label=y2_name)
            self.ax2.set_ylabel(self._format_axis_label(y2_name), color=color2)
            self.ax2.tick_params(axis='y', labelcolor=color2)
        
        # Set X axis
        self.ax.set_xlabel(self._format_axis_label(x_name))
        
        # Title
        if y2_name != "None":
            title = f"{y1_name} & {y2_name} vs {x_name}"
        elif y1_name != "None":
            title = f"{y1_name} vs {x_name}"
        else:
            title = "No data selected"
        self.ax.set_title(title)
        
        # Grid and legend
        self.ax.grid(True, alpha=0.3)
        
        # Combined legend for dual axis
        if y1_name != "None" and y2_name != "None":
            lines1, labels1 = self.ax.get_legend_handles_labels()
            lines2, labels2 = self.ax2.get_legend_handles_labels()
            self.ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        elif y1_name != "None":
            self.ax.legend(loc='upper left')
        
        self.fig.tight_layout()
        self.canvas.draw_idle()
    
    def plot_live(self):
        """Force update plot - called at end of measurement"""
        self._update_plot()
    
    def _clear_plot(self):
        """Clear plot and data"""
        self.data_points.clear()
        self.ax.clear()
        if self.ax2:
            self.ax2.remove()
            self.ax2 = None
        self._setup_initial_plot()
        self.canvas.draw()
    
    def _autoscale(self):
        """Autoscale axes"""
        self.ax.autoscale()
        if self.ax2:
            self.ax2.autoscale()
        self.canvas.draw()
        self.ax.autoscale()
        self.canvas.draw()


class StatusBar(ttk.Frame):
    """Status bar at bottom"""
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Run controls
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.pack(side=tk.LEFT, padx=10)
        
        self.run_btn = tk.Button(ctrl_frame, text="▶", font=("Segoe UI", 14),
                                bg=ModernStyle.ACCENT_GREEN, fg="white",
                                width=3, command=self.app.start_measurement)
        self.run_btn.pack(side=tk.LEFT, padx=2)
        
        self.stop_btn = tk.Button(ctrl_frame, text="⏹", font=("Segoe UI", 14),
                                 bg=ModernStyle.ACCENT_RED, fg="white",
                                 width=3, command=self.app.stop_measurement,
                                 state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        
        # Progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(self, variable=self.progress_var,
                                        length=300, maximum=100)
        self.progress.pack(side=tk.LEFT, padx=20)
        
        # Status text
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(self, textvariable=self.status_var,
                                      font=ModernStyle.FONT_NORMAL)
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Export buttons
        export_frame = ttk.Frame(self)
        export_frame.pack(side=tk.RIGHT, padx=10)
        
        self.save_csv_btn = tk.Button(export_frame, text="💾 Save CSV",
                                      font=("Segoe UI", 10),
                                      bg="#28a745", fg="white",
                                      command=self.app.export_data)
        self.save_csv_btn.pack(side=tk.LEFT, padx=5)
        
        self.export_btn = tk.Button(export_frame, text="📁", font=("Segoe UI", 12),
                                   command=self.app.export_data)
        self.export_btn.pack(side=tk.LEFT, padx=2)
        
        # Instruments button
        self.inst_btn = tk.Button(export_frame, text="Instruments",
                                 bg=ModernStyle.BUTTON_BG, fg=ModernStyle.BUTTON_FG,
                                 command=self.app.show_connection_dialog)
        self.inst_btn.pack(side=tk.LEFT, padx=10)
    
    def set_running(self, running: bool):
        """Update UI for running state"""
        if running:
            self.run_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
        else:
            self.run_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
    
    def update_progress(self, current: int, total: int, status: str = ""):
        """Update progress display"""
        if total > 0:
            percent = (current / total) * 100
            self.progress_var.set(percent)
            self.status_var.set(f"{current} of {total}  {percent:.0f}%  {status}")
        else:
            self.progress_var.set(0)
            self.status_var.set(status)


class ConnectionDialog(tk.Toplevel):
    """Connection dialog with simulation settings"""
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Connect to Instrument")
        self.geometry("550x480")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
        self._refresh_resources()
    
    def _create_widgets(self):
        main = ttk.Frame(self, padding=20)
        main.pack(fill=tk.BOTH, expand=True)
        
        # === Real Instrument Section ===
        ttk.Label(main, text="Connect to Real Instrument:", 
                 font=ModernStyle.FONT_HEADER).pack(anchor=tk.W)
        
        # Resource list
        self.resource_var = tk.StringVar()
        self.resource_list = tk.Listbox(main, height=6, font=ModernStyle.FONT_MONO)
        self.resource_list.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Connection buttons
        conn_btn_frame = ttk.Frame(main)
        conn_btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(conn_btn_frame, text="Refresh", command=self._refresh_resources).pack(side=tk.LEFT)
        ttk.Button(conn_btn_frame, text="Connect", command=self._connect).pack(side=tk.RIGHT)
        
        # Separator
        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # === Simulation Section ===
        ttk.Label(main, text="Simulation Mode:", 
                 font=ModernStyle.FONT_HEADER).pack(anchor=tk.W)
        
        sim_frame = ttk.LabelFrame(main, text="Simulation Settings", padding=10)
        sim_frame.pack(fill=tk.X, pady=5)
        
        # Resistance selection
        res_frame = ttk.Frame(sim_frame)
        res_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(res_frame, text="Simulated Resistance:").pack(side=tk.LEFT)
        
        self.sim_resistance_var = tk.StringVar(value="1000")
        res_entry = ttk.Entry(res_frame, textvariable=self.sim_resistance_var, width=12)
        res_entry.pack(side=tk.LEFT, padx=10)
        
        ttk.Label(res_frame, text="Ω").pack(side=tk.LEFT)
        
        # Quick resistance presets
        preset_frame = ttk.Frame(sim_frame)
        preset_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(preset_frame, text="Presets:").pack(side=tk.LEFT)
        
        for val, label in [(10, "10Ω"), (100, "100Ω"), (1000, "1kΩ"), 
                           (10000, "10kΩ"), (100000, "100kΩ"), (1000000, "1MΩ")]:
            ttk.Button(preset_frame, text=label, width=7,
                      command=lambda v=val: self.sim_resistance_var.set(str(v))).pack(side=tk.LEFT, padx=2)
        
        # Simulate button
        sim_btn_frame = ttk.Frame(main)
        sim_btn_frame.pack(fill=tk.X, pady=10)
        
        self.sim_btn = tk.Button(sim_btn_frame, text="🎮 Start Simulation",
                                bg="#17a2b8", fg="white",
                                font=("Segoe UI", 11, "bold"),
                                command=self._simulate)
        self.sim_btn.pack(fill=tk.X)
        
        # Cancel button
        ttk.Button(main, text="Cancel", command=self.destroy).pack(pady=5)
    
    def _refresh_resources(self):
        """Refresh available resources"""
        self.resource_list.delete(0, tk.END)
        resources = Keithley2450.list_available_instruments()
        for r in resources:
            self.resource_list.insert(tk.END, r)
        
        # Highlight Keithley 2450
        for i, r in enumerate(resources):
            if "2450" in r or "05E6" in r.upper():
                self.resource_list.select_set(i)
                self.resource_list.see(i)
                break
    
    def _connect(self):
        """Connect to selected instrument"""
        selection = self.resource_list.curselection()
        if not selection:
            messagebox.showwarning("Select Resource", "Please select a VISA resource")
            return
        
        resource = self.resource_list.get(selection[0])
        try:
            self.app.connect_instrument(resource)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
    
    def _simulate(self):
        """Start simulation mode with selected resistance"""
        try:
            resistance = float(self.sim_resistance_var.get())
            if resistance <= 0:
                raise ValueError("Resistance must be positive")
            self.app.connect_instrument(None, simulate=True, simulation_resistance=resistance)
            self.destroy()
        except ValueError as e:
            messagebox.showerror("Invalid Resistance", f"Please enter a valid positive number: {e}")


class Keithley2450App:
    """Main application class"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("I-V Characterizer - Keithley 2450")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)
        
        # State
        self.smu: Optional[Keithley2450] = None
        self.connected = False
        self.running = False
        self.abort_flag = False
        self.safety_limits = SafetyLimits()
        self.measurement_data: List[MeasurementDataPoint] = []
        
        # Configure styles
        self._configure_styles()
        
        # Create UI
        self._create_menu()
        self._create_layout()
        
        # Bind close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _configure_styles(self):
        """Configure ttk styles"""
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('.', background=ModernStyle.BG_MAIN,
                       foreground=ModernStyle.TEXT_PRIMARY)
        style.configure('TFrame', background=ModernStyle.BG_MAIN)
        style.configure('TLabel', background=ModernStyle.BG_MAIN)
        style.configure('TLabelframe', background=ModernStyle.BG_MAIN)
        style.configure('TLabelframe.Label', background=ModernStyle.BG_MAIN,
                       font=ModernStyle.FONT_HEADER)
        style.configure('TNotebook', background=ModernStyle.BG_MAIN)
        style.configure('TNotebook.Tab', padding=[10, 5])
    
    def _create_menu(self):
        """Create menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Export Data...", command=self.export_data)
        file_menu.add_command(label="Import Sweep List...", command=self._import_list)
        file_menu.add_separator()
        file_menu.add_command(label="Save Configuration...", command=self._save_config)
        file_menu.add_command(label="Load Configuration...", command=self._load_config)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        
        # Instrument menu
        inst_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Instrument", menu=inst_menu)
        inst_menu.add_command(label="Connect...", command=self.show_connection_dialog)
        inst_menu.add_command(label="Disconnect", command=self.disconnect_instrument)
        inst_menu.add_separator()
        inst_menu.add_command(label="Reset", command=self._reset_instrument)
        inst_menu.add_command(label="Safety Settings...", command=self._safety_settings)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)
    
    def _create_layout(self):
        """Create main layout"""
        # Main container
        main = ttk.Frame(self.root, padding=5)
        main.pack(fill=tk.BOTH, expand=True)
        
        # Top - Tabs (Settings, Table, Graph)
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # === Settings Tab ===
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="Settings")
        
        # Timeline at top
        self.timeline = TimelinePanel(settings_frame, self)
        self.timeline.pack(fill=tk.X, pady=5)
        
        # Content area
        content = ttk.Frame(settings_frame)
        content.pack(fill=tk.BOTH, expand=True)
        
        # Left column - Instrument info
        left_col = ttk.Frame(content)
        left_col.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        self.instrument_panel = InstrumentPanel(left_col, self)
        self.instrument_panel.pack(fill=tk.X)
        
        # Middle column - Source, Measure, Instrument Settings
        middle_col = ttk.Frame(content)
        middle_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.source_panel = SourcePanel(middle_col, self)
        self.source_panel.pack(fill=tk.BOTH, expand=True)
        
        bottom_middle = ttk.Frame(middle_col)
        bottom_middle.pack(fill=tk.X, pady=5)
        
        self.measure_panel = MeasurePanel(bottom_middle, self)
        self.measure_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.inst_settings_panel = InstrumentSettingsPanel(bottom_middle, self)
        self.inst_settings_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Right column - Common Settings
        right_col = ttk.Frame(content)
        right_col.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        
        self.common_panel = CommonSettingsPanel(right_col, self)
        self.common_panel.pack(fill=tk.X)
        
        # === Table Tab ===
        table_frame = ttk.Frame(self.notebook)
        self.notebook.add(table_frame, text="Table")
        
        self.table_panel = DataTablePanel(table_frame, self)
        self.table_panel.pack(fill=tk.BOTH, expand=True)
        
        # === Graph Tab ===
        graph_frame = ttk.Frame(self.notebook)
        self.notebook.add(graph_frame, text="Graph")
        
        self.graph_panel = GraphPanel(graph_frame, self)
        self.graph_panel.pack(fill=tk.BOTH, expand=True)
        
        # Status bar at bottom
        self.status_bar = StatusBar(self.root, self)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
    
    # === Connection Methods ===
    
    def show_connection_dialog(self):
        """Show connection dialog"""
        ConnectionDialog(self.root, self)
    
    def connect_instrument(self, resource: Optional[str], simulate: bool = False, 
                          simulation_resistance: float = 1000.0):
        """Connect to instrument"""
        self.smu = Keithley2450(
            resource_name=resource,
            safety_limits=self.safety_limits,
            simulate=simulate,
            simulation_resistance=simulation_resistance
        )
        self.smu.connect()
        self.connected = True
        self.simulation_resistance = simulation_resistance if simulate else None
        
        # Update UI
        if simulate:
            res_str = f"{simulation_resistance:.0f}Ω" if simulation_resistance < 10000 else f"{simulation_resistance/1000:.0f}kΩ"
            self.instrument_panel.inst_name.config(text=f"SMU-1 (SIM: {res_str})")
        else:
            self.instrument_panel.inst_name.config(text="SMU-1")
        
        self.status_bar.status_var.set("Connected")
    
    def disconnect_instrument(self):
        """Disconnect from instrument"""
        if self.smu:
            self.smu.disconnect()
            self.smu = None
        self.connected = False
        self.status_bar.status_var.set("Disconnected")
    
    # === Measurement Methods ===
    
    def start_measurement(self):
        """Start measurement/sweep"""
        if not self.smu:
            messagebox.showwarning("Not Connected", "Please connect to an instrument first")
            return
        
        # Validate settings
        try:
            self._validate_settings()
        except Exception as e:
            messagebox.showerror("Invalid Settings", str(e))
            return
        
        # Confirm
        mode = self.source_panel.mode_var.get()
        function = self.source_panel.function_var.get()
        
        if not messagebox.askyesno("Start Measurement",
                                  f"Start {mode} ({function})?\n\nThis will enable the output.",
                                  icon='warning'):
            return
        
        # Clear previous data
        self.measurement_data.clear()
        self.table_panel.clear_data()
        self.graph_panel._clear_plot()
        
        # Start measurement thread
        self.running = True
        self.abort_flag = False
        self.status_bar.set_running(True)
        
        thread = threading.Thread(target=self._run_measurement)
        thread.daemon = True
        thread.start()
    
    def stop_measurement(self):
        """Stop measurement"""
        self.abort_flag = True
        if self.smu:
            self.smu.output_off()
    
    def _validate_settings(self):
        """Validate measurement settings BEFORE starting"""
        mode = self.source_panel.mode_var.get()
        function = self.source_panel.function_var.get()
        
        # Get sweep values
        if mode in ["List Sweep", "Linear Sweep", "Log Sweep"]:
            values = self.source_panel.get_sweep_values()
            if not values:
                raise ValueError("No sweep values defined. Generate or import a list.")
        else:
            values = [float(self.source_panel.start_var.get())]
        
        # Validate limit (compliance)
        limit_str = self.source_panel.limit_var.get()
        try:
            limit = float(limit_str.replace('A', '').replace('V', '').strip())
        except:
            raise ValueError(f"Invalid limit: {limit_str}")
        
        # ========== SAFETY VALIDATION OF ALL VALUES ==========
        # Check EVERY value in sweep list against safety limits BEFORE starting
        
        if function == "Voltage":
            # Check voltage limits
            min_v = self.safety_limits.min_voltage
            max_v = self.safety_limits.max_voltage
            max_power = self.safety_limits.power_limit
            
            for i, v in enumerate(values):
                if not (min_v <= v <= max_v):
                    raise ValueError(
                        f"SAFETY ERROR: Sweep point {i+1} voltage {v}V is outside "
                        f"safety limits [{min_v}V, {max_v}V]"
                    )
                # Power check: V * I_compliance
                potential_power = abs(v * limit)
                if potential_power > max_power:
                    raise ValueError(
                        f"SAFETY ERROR: Sweep point {i+1} ({v}V × {limit}A = {potential_power:.1f}W) "
                        f"exceeds power limit {max_power}W"
                    )
            
            # Check compliance current
            if abs(limit) > self.safety_limits.max_current:
                raise ValueError(
                    f"SAFETY ERROR: Compliance current {limit}A exceeds "
                    f"safety limit {self.safety_limits.max_current}A"
                )
        else:
            # Check current limits
            min_i = self.safety_limits.min_current
            max_i = self.safety_limits.max_current
            max_power = self.safety_limits.power_limit
            
            for i, curr in enumerate(values):
                if not (min_i <= curr <= max_i):
                    raise ValueError(
                        f"SAFETY ERROR: Sweep point {i+1} current {curr}A is outside "
                        f"safety limits [{min_i}A, {max_i}A]"
                    )
                # Power check: I * V_compliance
                potential_power = abs(curr * limit)
                if potential_power > max_power:
                    raise ValueError(
                        f"SAFETY ERROR: Sweep point {i+1} ({curr}A × {limit}V = {potential_power:.1f}W) "
                        f"exceeds power limit {max_power}W"
                    )
            
            # Check compliance voltage
            if abs(limit) > self.safety_limits.max_voltage:
                raise ValueError(
                    f"SAFETY ERROR: Compliance voltage {limit}V exceeds "
                    f"safety limit {self.safety_limits.max_voltage}V"
                )
        
        # Report validation success
        print(f"✓ Safety check passed: {len(values)} points validated, "
              f"Max potential power: {max(abs(v * limit) for v in values):.2f}W")
    
    def _run_measurement(self):
        """Run measurement in background thread"""
        try:
            mode = self.source_panel.mode_var.get()
            function = self.source_panel.function_var.get()
            repeat = int(self.common_panel.repeat_var.get())
            delay = float(self.common_panel.delay_var.get())
            nplc = float(self.common_panel.nplc_var.get())
            
            # Parse limit
            limit_str = self.source_panel.limit_var.get()
            limit = float(limit_str.replace('A', '').replace('V', '').strip())
            
            # Get sweep values
            if mode in ["List Sweep", "Linear Sweep", "Log Sweep"]:
                sweep_values = self.source_panel.get_sweep_values()
            else:
                sweep_values = [float(self.source_panel.start_var.get())]
            
            total_points = len(sweep_values) * repeat
            current_point = 0
            start_time = time.time()
            
            self._update_status(0, total_points, "Configuring instrument...")
            
            # Configure instrument
            if function == "Voltage":
                self.smu.set_source_voltage(sweep_values[0], compliance_current=limit)
            else:
                self.smu.set_source_current(sweep_values[0], compliance_voltage=limit)
            
            # Set NPLC
            self.smu._write(f"SENS:CURR:NPLC {nplc}")
            self.smu._write(f"SENS:VOLT:NPLC {nplc}")
            
            # Apply instrument settings
            term = self.inst_settings_panel.terminal_var.get()
            self.smu.set_terminal(term.upper())
            
            sense = self.inst_settings_panel.sense_var.get()
            if sense == "4-Wire":
                self.smu._write("SENS:CURR:RSEN ON")
                self.smu._write("SENS:VOLT:RSEN ON")
            else:
                self.smu._write("SENS:CURR:RSEN OFF")
                self.smu._write("SENS:VOLT:RSEN OFF")
            
            # Enable output
            self.smu.output_on()
            
            # Run measurement
            for rep in range(repeat):
                if self.abort_flag:
                    break
                
                for i, source_val in enumerate(sweep_values):
                    if self.abort_flag:
                        break
                    
                    current_point += 1
                    elapsed = time.time() - start_time
                    
                    # Set source value (WITH SAFETY VALIDATION)
                    if function == "Voltage":
                        self.smu.set_voltage(source_val)  # Safe method with limits check
                    else:
                        self.smu.set_current(source_val)  # Safe method with limits check
                    
                    # Delay
                    time.sleep(delay)
                    
                    # Measure
                    voltage = None
                    current = None
                    resistance = None
                    power = None
                    
                    if self.measure_panel.measure_voltage.get():
                        self.smu._write("SENS:FUNC 'VOLT'")
                        voltage = float(self.smu._query("READ?"))
                    
                    if self.measure_panel.measure_current.get():
                        self.smu._write("SENS:FUNC 'CURR'")
                        current = float(self.smu._query("READ?"))
                    
                    if self.measure_panel.measure_resistance.get() and voltage and current:
                        if abs(current) > 1e-12:
                            resistance = voltage / current
                    
                    if self.measure_panel.measure_power.get() and voltage and current:
                        power = abs(voltage * current)
                    
                    # Store data point
                    point = MeasurementDataPoint(
                        index=current_point,
                        timestamp=elapsed,
                        source_value=source_val,
                        voltage=voltage,
                        current=current,
                        resistance=resistance,
                        power=power
                    )
                    self.measurement_data.append(point)
                    
                    # Update UI
                    self._add_data_point(point)
                    self._update_status(current_point, total_points, "Measuring...")
                    self._update_timeline(current_point, total_points)
            
            # Measurement complete
            self._update_status(total_points, total_points, "Run completed")
            
        except Exception as e:
            self._update_status(0, 0, f"Error: {e}")
            
        finally:
            self.running = False
            if self.smu:
                self.smu.output_off()
            self.root.after(0, lambda: self.status_bar.set_running(False))
            self.root.after(0, self.graph_panel._update_plot)
    
    def _add_data_point(self, point: MeasurementDataPoint):
        """Add data point to UI (thread-safe)"""
        self.root.after(0, lambda: self.table_panel.add_data_point(point))
        self.root.after(0, lambda: self.graph_panel.add_data_point(point))
        
        # Update instrument panel
        measures = []
        if point.voltage is not None:
            measures.append("V")
        if point.current is not None:
            measures.append("A")
        if point.resistance is not None:
            measures.append("Ω")
        if point.power is not None:
            measures.append("W")
        
        self.root.after(0, lambda: self.instrument_panel.update_info(
            self.source_panel.function_var.get(),
            self.source_panel.mode_var.get(),
            point.source_value,
            float(self.source_panel.limit_var.get().replace('A', '').replace('V', '').strip()),
            ", ".join(measures)
        ))
    
    def _update_status(self, current: int, total: int, status: str):
        """Update status bar (thread-safe)"""
        self.root.after(0, lambda: self.status_bar.update_progress(current, total, status))
    
    def _update_timeline(self, current: int, total: int):
        """Update timeline (thread-safe)"""
        self.root.after(0, lambda: self.timeline.update_progress(current, total))
    
    # === File Operations ===
    
    def export_data(self):
        """Export measurement data"""
        if not self.measurement_data:
            messagebox.showwarning("No Data", "No data to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"iv_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if filename:
            self.table_panel.export_data(filename)
            messagebox.showinfo("Export Complete", f"Data exported to:\n{filename}")
    
    def _import_list(self):
        """Import sweep list"""
        self.source_panel._import_list()
    
    def _save_config(self):
        """Save configuration"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile="iv_config.json"
        )
        if not filename:
            return
        
        config = {
            'source': {
                'type': self.source_panel.source_type_var.get(),
                'function': self.source_panel.function_var.get(),
                'mode': self.source_panel.mode_var.get(),
                'range': self.source_panel.range_var.get(),
                'limit': self.source_panel.limit_var.get(),
                'start': self.source_panel.start_var.get(),
                'stop': self.source_panel.stop_var.get(),
            },
            'measure': {
                'voltage': self.measure_panel.measure_voltage.get(),
                'current': self.measure_panel.measure_current.get(),
                'power': self.measure_panel.measure_power.get(),
                'resistance': self.measure_panel.measure_resistance.get(),
                'range': self.measure_panel.range_var.get(),
                'auto_zero': self.measure_panel.auto_zero_var.get(),
            },
            'instrument': {
                'terminal': self.inst_settings_panel.terminal_var.get(),
                'sense': self.inst_settings_panel.sense_var.get(),
                'high_cap': self.inst_settings_panel.high_cap_var.get(),
                'output_off': self.inst_settings_panel.output_off_var.get(),
            },
            'common': {
                'points': self.common_panel.points_var.get(),
                'repeat': self.common_panel.repeat_var.get(),
                'delay': self.common_panel.delay_var.get(),
                'nplc': self.common_panel.nplc_var.get(),
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(config, f, indent=2)
        
        messagebox.showinfo("Saved", f"Configuration saved to:\n{filename}")
    
    def _load_config(self):
        """Load configuration"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")]
        )
        if not filename:
            return
        
        try:
            with open(filename, 'r') as f:
                config = json.load(f)
            
            # Apply settings
            if 'source' in config:
                s = config['source']
                self.source_panel.source_type_var.set(s.get('type', 'DC'))
                self.source_panel.function_var.set(s.get('function', 'Voltage'))
                self.source_panel.mode_var.set(s.get('mode', 'List Sweep'))
                self.source_panel.range_var.set(s.get('range', 'Auto'))
                self.source_panel.limit_var.set(s.get('limit', '0.5 A'))
                self.source_panel.start_var.set(s.get('start', '0'))
                self.source_panel.stop_var.set(s.get('stop', '5'))
            
            if 'measure' in config:
                m = config['measure']
                self.measure_panel.measure_voltage.set(m.get('voltage', True))
                self.measure_panel.measure_current.set(m.get('current', True))
                self.measure_panel.measure_power.set(m.get('power', True))
                self.measure_panel.measure_resistance.set(m.get('resistance', True))
                self.measure_panel.range_var.set(m.get('range', 'Auto'))
                self.measure_panel.auto_zero_var.set(m.get('auto_zero', 'On'))
            
            if 'instrument' in config:
                i = config['instrument']
                self.inst_settings_panel.terminal_var.set(i.get('terminal', 'Rear'))
                self.inst_settings_panel.sense_var.set(i.get('sense', '4-Wire'))
                self.inst_settings_panel.high_cap_var.set(i.get('high_cap', False))
                self.inst_settings_panel.output_off_var.set(i.get('output_off', 'Normal'))
            
            if 'common' in config:
                c = config['common']
                self.common_panel.points_var.set(c.get('points', '12000'))
                self.common_panel.repeat_var.set(c.get('repeat', '1'))
                self.common_panel.delay_var.set(c.get('delay', '0.917'))
                self.common_panel.nplc_var.set(c.get('nplc', '1'))
            
            messagebox.showinfo("Loaded", "Configuration loaded successfully")
            
        except Exception as e:
            messagebox.showerror("Load Error", str(e))
    
    # === Instrument Operations ===
    
    def _reset_instrument(self):
        """Reset instrument"""
        if self.smu and messagebox.askyesno("Reset", "Reset instrument to defaults?"):
            try:
                self.smu.reset()
                messagebox.showinfo("Reset", "Instrument reset to defaults")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def _safety_settings(self):
        """Show safety settings"""
        from keithley2450_gui import SafetySettingsDialog
        dialog = SafetySettingsDialog(self.root, self.safety_limits)
        self.root.wait_window(dialog)
        if dialog.result:
            self.safety_limits = dialog.result
            if self.smu:
                self.smu.safety_limits = self.safety_limits
    
    def _show_about(self):
        """Show about dialog"""
        messagebox.showinfo(
            "About",
            "Keithley 2450 I-V Characterizer\n\n"
            "Version 1.0\n\n"
            "A professional I-V characterization application\n"
            "for the Keithley 2450 Source Measure Unit.\n\n"
            "Features:\n"
            "• List/Linear/Log Sweep modes\n"
            "• DC and Pulse source types\n"
            "• 2-Wire and 4-Wire sensing\n"
            "• Configurable NPLC and delays\n"
            "• Real-time plotting\n"
            "• Data export to CSV"
        )
    
    def _on_close(self):
        """Handle close"""
        self.abort_flag = True
        if self.smu:
            try:
                self.smu.disconnect()
            except:
                pass
        self.root.destroy()


def main():
    """Main entry point"""
    root = tk.Tk()
    app = Keithley2450App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
