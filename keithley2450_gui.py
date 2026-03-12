"""
Keithley 2450 SourceMeter Control Program
==========================================
Professional GUI control application for the Keithley 2450 SMU.
Designed for safe, user-friendly operation similar to KickStart.

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
from typing import Optional, List, Dict, Any
import queue

# Import matplotlib for plotting
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt

# Import our driver
from keithley2450_driver import (
    Keithley2450, 
    SafetyLimits, 
    MeasurementResult,
    SourceFunction,
    MeasureFunction,
    Keithley2450Error
)


class ModernStyle:
    """Modern color scheme for the application"""
    # Colors
    BG_DARK = "#1e1e1e"
    BG_MEDIUM = "#252526"
    BG_LIGHT = "#2d2d30"
    BG_HIGHLIGHT = "#3e3e42"
    
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#cccccc"
    TEXT_DISABLED = "#808080"
    
    ACCENT_BLUE = "#007acc"
    ACCENT_GREEN = "#4ec9b0"
    ACCENT_RED = "#f14c4c"
    ACCENT_YELLOW = "#dcdcaa"
    ACCENT_ORANGE = "#ce9178"
    
    # Output state colors
    OUTPUT_ON = "#00ff00"
    OUTPUT_OFF = "#ff4444"
    
    # Fonts
    FONT_TITLE = ("Segoe UI", 14, "bold")
    FONT_HEADER = ("Segoe UI", 11, "bold")
    FONT_NORMAL = ("Segoe UI", 10)
    FONT_SMALL = ("Segoe UI", 9)
    FONT_MONO = ("Consolas", 11)
    FONT_LARGE_READING = ("Consolas", 24, "bold")
    FONT_MEDIUM_READING = ("Consolas", 16)


class SafetySettingsDialog(tk.Toplevel):
    """Dialog for configuring safety limits"""
    
    def __init__(self, parent, current_limits: SafetyLimits):
        super().__init__(parent)
        self.title("Safety Settings")
        self.geometry("400x450")
        self.resizable(False, False)
        self.configure(bg=ModernStyle.BG_MEDIUM)
        
        self.result = None
        self.current_limits = current_limits
        
        self._create_widgets()
        
        # Center on parent
        self.transient(parent)
        self.grab_set()
        
    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(main_frame, text="Safety Limits Configuration", 
                 font=ModernStyle.FONT_HEADER).pack(pady=(0, 20))
        
        # Warning
        warning_frame = ttk.Frame(main_frame)
        warning_frame.pack(fill=tk.X, pady=(0, 15))
        ttk.Label(warning_frame, text="⚠ WARNING: Changing these limits affects instrument protection!",
                 foreground="orange").pack()
        
        # Voltage limits
        volt_frame = ttk.LabelFrame(main_frame, text="Voltage Limits", padding=10)
        volt_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(volt_frame, text="Maximum Voltage (V):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.max_volt_var = tk.StringVar(value=str(self.current_limits.max_voltage))
        ttk.Entry(volt_frame, textvariable=self.max_volt_var, width=15).grid(row=0, column=1, padx=10)
        
        ttk.Label(volt_frame, text="Minimum Voltage (V):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.min_volt_var = tk.StringVar(value=str(self.current_limits.min_voltage))
        ttk.Entry(volt_frame, textvariable=self.min_volt_var, width=15).grid(row=1, column=1, padx=10)
        
        ttk.Label(volt_frame, text="Default Compliance (V):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.comp_volt_var = tk.StringVar(value=str(self.current_limits.compliance_voltage))
        ttk.Entry(volt_frame, textvariable=self.comp_volt_var, width=15).grid(row=2, column=1, padx=10)
        
        # Current limits
        curr_frame = ttk.LabelFrame(main_frame, text="Current Limits", padding=10)
        curr_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(curr_frame, text="Maximum Current (A):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.max_curr_var = tk.StringVar(value=str(self.current_limits.max_current))
        ttk.Entry(curr_frame, textvariable=self.max_curr_var, width=15).grid(row=0, column=1, padx=10)
        
        ttk.Label(curr_frame, text="Minimum Current (A):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.min_curr_var = tk.StringVar(value=str(self.current_limits.min_current))
        ttk.Entry(curr_frame, textvariable=self.min_curr_var, width=15).grid(row=1, column=1, padx=10)
        
        ttk.Label(curr_frame, text="Default Compliance (A):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.comp_curr_var = tk.StringVar(value=str(self.current_limits.compliance_current))
        ttk.Entry(curr_frame, textvariable=self.comp_curr_var, width=15).grid(row=2, column=1, padx=10)
        
        # Power limit
        power_frame = ttk.LabelFrame(main_frame, text="Power Limit", padding=10)
        power_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(power_frame, text="Maximum Power (W):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.power_var = tk.StringVar(value=str(self.current_limits.power_limit))
        ttk.Entry(power_frame, textvariable=self.power_var, width=15).grid(row=0, column=1, padx=10)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(20, 0))
        
        ttk.Button(btn_frame, text="Reset to Defaults", 
                  command=self._reset_defaults).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Cancel", 
                  command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Apply", 
                  command=self._apply).pack(side=tk.RIGHT)
    
    def _reset_defaults(self):
        defaults = SafetyLimits()
        self.max_volt_var.set(str(defaults.max_voltage))
        self.min_volt_var.set(str(defaults.min_voltage))
        self.comp_volt_var.set(str(defaults.compliance_voltage))
        self.max_curr_var.set(str(defaults.max_current))
        self.min_curr_var.set(str(defaults.min_current))
        self.comp_curr_var.set(str(defaults.compliance_current))
        self.power_var.set(str(defaults.power_limit))
    
    def _apply(self):
        try:
            self.result = SafetyLimits(
                max_voltage=float(self.max_volt_var.get()),
                min_voltage=float(self.min_volt_var.get()),
                compliance_voltage=float(self.comp_volt_var.get()),
                max_current=float(self.max_curr_var.get()),
                min_current=float(self.min_curr_var.get()),
                compliance_current=float(self.comp_curr_var.get()),
                power_limit=float(self.power_var.get())
            )
            self.destroy()
        except ValueError as e:
            messagebox.showerror("Invalid Input", f"Please enter valid numbers: {e}")


class ConnectionPanel(ttk.LabelFrame):
    """Panel for instrument connection management"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="Connection", padding=10)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Resource selection
        ttk.Label(self, text="VISA Resource:").grid(row=0, column=0, sticky=tk.W, pady=2)
        
        self.resource_var = tk.StringVar()
        self.resource_combo = ttk.Combobox(self, textvariable=self.resource_var, 
                                          width=45, state="readonly")
        self.resource_combo.grid(row=0, column=1, columnspan=2, padx=5, pady=2, sticky=tk.W)
        
        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=1, column=0, columnspan=3, pady=10)
        
        self.refresh_btn = ttk.Button(btn_frame, text="🔄 Refresh", 
                                      command=self._refresh_resources)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        
        self.connect_btn = ttk.Button(btn_frame, text="🔌 Connect", 
                                      command=self._connect)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_btn = ttk.Button(btn_frame, text="⏏ Disconnect", 
                                         command=self._disconnect, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)
        
        self.simulate_btn = ttk.Button(btn_frame, text="🎮 Simulate", 
                                       command=self._simulate)
        self.simulate_btn.pack(side=tk.LEFT, padx=5)
        
        # Status
        self.status_frame = ttk.Frame(self)
        self.status_frame.grid(row=2, column=0, columnspan=3, pady=5)
        
        self.status_indicator = tk.Label(self.status_frame, text="●", 
                                         fg=ModernStyle.OUTPUT_OFF,
                                         font=("Segoe UI", 16))
        self.status_indicator.pack(side=tk.LEFT)
        
        self.status_label = ttk.Label(self.status_frame, text="Disconnected",
                                      font=ModernStyle.FONT_NORMAL)
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Instrument info
        self.info_label = ttk.Label(self, text="", font=ModernStyle.FONT_SMALL,
                                   foreground=ModernStyle.TEXT_SECONDARY)
        self.info_label.grid(row=3, column=0, columnspan=3, sticky=tk.W)
        
        # Initial refresh
        self._refresh_resources()
    
    def _refresh_resources(self):
        """Refresh available VISA resources"""
        resources = Keithley2450.list_available_instruments()
        keithley_resources = Keithley2450.find_keithley_2450()
        
        self.resource_combo['values'] = resources
        
        # Auto-select Keithley 2450 if found
        if keithley_resources:
            self.resource_var.set(keithley_resources[0])
        elif resources:
            self.resource_var.set(resources[0])
    
    def _connect(self):
        """Connect to selected instrument"""
        resource = self.resource_var.get()
        if not resource:
            messagebox.showwarning("No Resource", "Please select a VISA resource")
            return
        
        try:
            self.app.smu = Keithley2450(
                resource_name=resource,
                safety_limits=self.app.safety_limits
            )
            self.app.smu.connect()
            
            self._update_connected_state(True)
            self.info_label.config(text=self.app.smu.get_identification())
            
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
    
    def _simulate(self):
        """Start simulation mode"""
        try:
            self.app.smu = Keithley2450(
                safety_limits=self.app.safety_limits,
                simulate=True
            )
            self.app.smu.connect()
            
            self._update_connected_state(True)
            self.info_label.config(text="SIMULATION MODE - " + self.app.smu.get_identification())
            
        except Exception as e:
            messagebox.showerror("Simulation Error", str(e))
    
    def _disconnect(self):
        """Disconnect from instrument"""
        if self.app.smu:
            try:
                self.app.smu.disconnect()
            except:
                pass
            self.app.smu = None
        
        self._update_connected_state(False)
        self.info_label.config(text="")
    
    def _update_connected_state(self, connected: bool):
        """Update UI based on connection state"""
        self.app.connected = connected
        
        if connected:
            self.status_indicator.config(fg=ModernStyle.OUTPUT_ON)
            self.status_label.config(text="Connected")
            self.connect_btn.config(state=tk.DISABLED)
            self.simulate_btn.config(state=tk.DISABLED)
            self.disconnect_btn.config(state=tk.NORMAL)
            self.resource_combo.config(state=tk.DISABLED)
        else:
            self.status_indicator.config(fg=ModernStyle.OUTPUT_OFF)
            self.status_label.config(text="Disconnected")
            self.connect_btn.config(state=tk.NORMAL)
            self.simulate_btn.config(state=tk.NORMAL)
            self.disconnect_btn.config(state=tk.DISABLED)
            self.resource_combo.config(state="readonly")
        
        # Notify app to update other panels
        self.app.update_connection_state(connected)


class OutputPanel(ttk.LabelFrame):
    """Panel for output control"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="Output Control", padding=15)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Large output indicator
        self.output_frame = tk.Frame(self, bg=ModernStyle.BG_DARK, 
                                     highlightthickness=2,
                                     highlightbackground=ModernStyle.OUTPUT_OFF)
        self.output_frame.pack(fill=tk.X, pady=10)
        
        self.output_label = tk.Label(self.output_frame, text="OUTPUT OFF",
                                     font=ModernStyle.FONT_TITLE,
                                     bg=ModernStyle.BG_DARK,
                                     fg=ModernStyle.OUTPUT_OFF)
        self.output_label.pack(pady=15)
        
        # Output button
        self.output_btn = ttk.Button(self, text="⚡ Turn OUTPUT ON",
                                     command=self._toggle_output,
                                     state=tk.DISABLED)
        self.output_btn.pack(fill=tk.X, pady=5)
        
        # Emergency off button
        self.emergency_btn = tk.Button(self, text="🛑 EMERGENCY OFF",
                                       command=self._emergency_off,
                                       bg="#cc0000", fg="white",
                                       font=ModernStyle.FONT_HEADER,
                                       state=tk.DISABLED)
        self.emergency_btn.pack(fill=tk.X, pady=10)
    
    def _toggle_output(self):
        """Toggle output state"""
        if not self.app.smu:
            return
        
        try:
            if self.app.smu.output_enabled:
                self.app.smu.output_off()
            else:
                # Confirm before enabling
                result = messagebox.askyesno(
                    "Enable Output",
                    "Are you sure you want to enable the output?\n\n"
                    f"Source: {self.app.smu._source_function.name}\n"
                    f"Value: {self.app.smu._source_value}",
                    icon='warning'
                )
                if result:
                    self.app.smu.output_on()
            
            self.update_state()
            
        except Exception as e:
            messagebox.showerror("Output Error", str(e))
    
    def _emergency_off(self):
        """Emergency output off - no confirmation"""
        if self.app.smu:
            try:
                self.app.smu.output_off()
                self.app.smu.reset()
                self.update_state()
                messagebox.showinfo("Emergency Off", "Output disabled and instrument reset to safe state")
            except Exception as e:
                messagebox.showerror("Error", f"Emergency off failed: {e}")
    
    def update_state(self):
        """Update output display state"""
        if self.app.smu and self.app.smu.output_enabled:
            self.output_label.config(text="OUTPUT ON", fg=ModernStyle.OUTPUT_ON)
            self.output_frame.config(highlightbackground=ModernStyle.OUTPUT_ON)
            self.output_btn.config(text="⚡ Turn OUTPUT OFF")
        else:
            self.output_label.config(text="OUTPUT OFF", fg=ModernStyle.OUTPUT_OFF)
            self.output_frame.config(highlightbackground=ModernStyle.OUTPUT_OFF)
            self.output_btn.config(text="⚡ Turn OUTPUT ON")
    
    def set_enabled(self, enabled: bool):
        """Enable/disable controls"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.output_btn.config(state=state)
        self.emergency_btn.config(state=state)


class SourcePanel(ttk.LabelFrame):
    """Panel for source configuration"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="Source Configuration", padding=10)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Source function selection
        func_frame = ttk.Frame(self)
        func_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(func_frame, text="Source Function:").pack(side=tk.LEFT)
        
        self.source_func_var = tk.StringVar(value="VOLTAGE")
        self.voltage_rb = ttk.Radiobutton(func_frame, text="Voltage", 
                                          variable=self.source_func_var,
                                          value="VOLTAGE",
                                          command=self._on_function_change)
        self.voltage_rb.pack(side=tk.LEFT, padx=10)
        
        self.current_rb = ttk.Radiobutton(func_frame, text="Current",
                                          variable=self.source_func_var,
                                          value="CURRENT",
                                          command=self._on_function_change)
        self.current_rb.pack(side=tk.LEFT, padx=10)
        
        # Source value frame
        value_frame = ttk.Frame(self)
        value_frame.pack(fill=tk.X, pady=10)
        
        self.source_label = ttk.Label(value_frame, text="Source Voltage (V):",
                                      font=ModernStyle.FONT_NORMAL)
        self.source_label.pack(side=tk.LEFT)
        
        self.source_value_var = tk.StringVar(value="0.0")
        self.source_entry = ttk.Entry(value_frame, textvariable=self.source_value_var,
                                      width=15, font=ModernStyle.FONT_MONO)
        self.source_entry.pack(side=tk.LEFT, padx=10)
        
        # Quick set buttons
        quick_frame = ttk.Frame(self)
        quick_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(quick_frame, text="Quick Set:").pack(side=tk.LEFT)
        
        for val in ["0", "1", "5", "10"]:
            btn = ttk.Button(quick_frame, text=val, width=5,
                           command=lambda v=val: self.source_value_var.set(v))
            btn.pack(side=tk.LEFT, padx=2)
        
        # Compliance frame
        comp_frame = ttk.Frame(self)
        comp_frame.pack(fill=tk.X, pady=10)
        
        self.comp_label = ttk.Label(comp_frame, text="Compliance Current (A):",
                                    font=ModernStyle.FONT_NORMAL)
        self.comp_label.pack(side=tk.LEFT)
        
        self.compliance_var = tk.StringVar(value="0.1")
        self.compliance_entry = ttk.Entry(comp_frame, textvariable=self.compliance_var,
                                          width=15, font=ModernStyle.FONT_MONO)
        self.compliance_entry.pack(side=tk.LEFT, padx=10)
        
        # Apply button
        self.apply_btn = ttk.Button(self, text="✓ Apply Source Settings",
                                    command=self._apply_settings,
                                    state=tk.DISABLED)
        self.apply_btn.pack(fill=tk.X, pady=10)
        
        # Current settings display
        self.current_settings = ttk.Label(self, text="Current: Not configured",
                                          font=ModernStyle.FONT_SMALL,
                                          foreground=ModernStyle.TEXT_SECONDARY)
        self.current_settings.pack(anchor=tk.W)
    
    def _on_function_change(self):
        """Handle source function change"""
        if self.source_func_var.get() == "VOLTAGE":
            self.source_label.config(text="Source Voltage (V):")
            self.comp_label.config(text="Compliance Current (A):")
            self.compliance_var.set(str(self.app.safety_limits.compliance_current))
        else:
            self.source_label.config(text="Source Current (A):")
            self.comp_label.config(text="Compliance Voltage (V):")
            self.compliance_var.set(str(self.app.safety_limits.compliance_voltage))
    
    def _apply_settings(self):
        """Apply source settings to instrument"""
        if not self.app.smu:
            return
        
        try:
            value = float(self.source_value_var.get())
            compliance = float(self.compliance_var.get())
            
            if self.source_func_var.get() == "VOLTAGE":
                self.app.smu.set_source_voltage(value, compliance)
                self.current_settings.config(
                    text=f"Current: {value} V source, {compliance} A compliance"
                )
            else:
                self.app.smu.set_source_current(value, compliance)
                self.current_settings.config(
                    text=f"Current: {value} A source, {compliance} V compliance"
                )
            
            self.app.output_panel.update_state()
            
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numeric values")
        except Keithley2450Error as e:
            messagebox.showerror("Safety Error", str(e))
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def set_enabled(self, enabled: bool):
        """Enable/disable controls"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.apply_btn.config(state=state)
        self.source_entry.config(state=state)
        self.compliance_entry.config(state=state)


class MeasurementPanel(ttk.LabelFrame):
    """Panel for live measurements display"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="Live Measurements", padding=10)
        self.app = app
        self.measuring = False
        self._create_widgets()
    
    def _create_widgets(self):
        # Large measurement displays
        readings_frame = ttk.Frame(self)
        readings_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Voltage display
        volt_frame = ttk.LabelFrame(readings_frame, text="Voltage", padding=10)
        volt_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.voltage_var = tk.StringVar(value="---")
        self.voltage_display = ttk.Label(volt_frame, textvariable=self.voltage_var,
                                         font=ModernStyle.FONT_LARGE_READING,
                                         foreground=ModernStyle.ACCENT_BLUE)
        self.voltage_display.pack()
        ttk.Label(volt_frame, text="V", font=ModernStyle.FONT_HEADER).pack()
        
        # Current display
        curr_frame = ttk.LabelFrame(readings_frame, text="Current", padding=10)
        curr_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.current_var = tk.StringVar(value="---")
        self.current_display = ttk.Label(curr_frame, textvariable=self.current_var,
                                         font=ModernStyle.FONT_LARGE_READING,
                                         foreground=ModernStyle.ACCENT_GREEN)
        self.current_display.pack()
        ttk.Label(curr_frame, text="A", font=ModernStyle.FONT_HEADER).pack()
        
        # Resistance display
        res_frame = ttk.LabelFrame(readings_frame, text="Resistance", padding=10)
        res_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.resistance_var = tk.StringVar(value="---")
        self.resistance_display = ttk.Label(res_frame, textvariable=self.resistance_var,
                                            font=ModernStyle.FONT_LARGE_READING,
                                            foreground=ModernStyle.ACCENT_YELLOW)
        self.resistance_display.pack()
        ttk.Label(res_frame, text="Ω", font=ModernStyle.FONT_HEADER).pack()
        
        # Power display
        power_frame = ttk.LabelFrame(readings_frame, text="Power", padding=10)
        power_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        self.power_var = tk.StringVar(value="---")
        self.power_display = ttk.Label(power_frame, textvariable=self.power_var,
                                       font=ModernStyle.FONT_LARGE_READING,
                                       foreground=ModernStyle.ACCENT_ORANGE)
        self.power_display.pack()
        ttk.Label(power_frame, text="W", font=ModernStyle.FONT_HEADER).pack()
        
        # Control buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.measure_once_btn = ttk.Button(btn_frame, text="📊 Measure Once",
                                           command=self._measure_once,
                                           state=tk.DISABLED)
        self.measure_once_btn.pack(side=tk.LEFT, padx=5)
        
        self.continuous_btn = ttk.Button(btn_frame, text="▶ Start Continuous",
                                         command=self._toggle_continuous,
                                         state=tk.DISABLED)
        self.continuous_btn.pack(side=tk.LEFT, padx=5)
        
        # Measurement interval
        ttk.Label(btn_frame, text="Interval (ms):").pack(side=tk.LEFT, padx=(20, 5))
        self.interval_var = tk.StringVar(value="500")
        self.interval_entry = ttk.Entry(btn_frame, textvariable=self.interval_var,
                                        width=8)
        self.interval_entry.pack(side=tk.LEFT)
        
        # Status
        self.status_label = ttk.Label(self, text="Ready", 
                                      font=ModernStyle.FONT_SMALL)
        self.status_label.pack(anchor=tk.W)
    
    def _measure_once(self):
        """Perform single measurement"""
        if not self.app.smu:
            return
        
        try:
            result = self.app.smu.measure_all()
            self._update_display(result)
            self.app.add_measurement(result)
        except Exception as e:
            messagebox.showerror("Measurement Error", str(e))
    
    def _toggle_continuous(self):
        """Toggle continuous measurement"""
        if self.measuring:
            self.measuring = False
            self.continuous_btn.config(text="▶ Start Continuous")
            self.status_label.config(text="Stopped")
        else:
            self.measuring = True
            self.continuous_btn.config(text="⏹ Stop")
            self.status_label.config(text="Measuring...")
            self._continuous_measure()
    
    def _continuous_measure(self):
        """Continuous measurement loop"""
        if not self.measuring or not self.app.smu:
            return
        
        try:
            result = self.app.smu.measure_all()
            self._update_display(result)
            self.app.add_measurement(result)
            
            interval = int(self.interval_var.get())
            self.after(interval, self._continuous_measure)
            
        except Exception as e:
            self.measuring = False
            self.continuous_btn.config(text="▶ Start Continuous")
            self.status_label.config(text=f"Error: {e}")
    
    def _update_display(self, result: MeasurementResult):
        """Update measurement displays"""
        self.voltage_var.set(f"{result.voltage:.6f}")
        self.current_var.set(f"{result.current:.9f}")
        
        if result.resistance and abs(result.resistance) < 1e9:
            self.resistance_var.set(f"{result.resistance:.2f}")
        else:
            self.resistance_var.set("---")
        
        power = abs(result.voltage * result.current)
        self.power_var.set(f"{power:.6f}")
    
    def set_enabled(self, enabled: bool):
        """Enable/disable controls"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.measure_once_btn.config(state=state)
        self.continuous_btn.config(state=state)
        
        if not enabled:
            self.measuring = False
            self.continuous_btn.config(text="▶ Start Continuous")


class SweepPanel(ttk.LabelFrame):
    """Panel for IV sweep measurements"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="IV Sweep", padding=10)
        self.app = app
        self.sweep_running = False
        self._create_widgets()
    
    def _create_widgets(self):
        # Sweep type
        type_frame = ttk.Frame(self)
        type_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(type_frame, text="Sweep Type:").pack(side=tk.LEFT)
        
        self.sweep_type_var = tk.StringVar(value="VOLTAGE")
        ttk.Radiobutton(type_frame, text="Voltage Sweep", 
                       variable=self.sweep_type_var, value="VOLTAGE",
                       command=self._on_type_change).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(type_frame, text="Current Sweep",
                       variable=self.sweep_type_var, value="CURRENT",
                       command=self._on_type_change).pack(side=tk.LEFT, padx=10)
        
        # Parameters frame
        params_frame = ttk.LabelFrame(self, text="Sweep Parameters", padding=10)
        params_frame.pack(fill=tk.X, pady=10)
        
        # Start value
        ttk.Label(params_frame, text="Start:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.start_var = tk.StringVar(value="0")
        self.start_entry = ttk.Entry(params_frame, textvariable=self.start_var, width=12)
        self.start_entry.grid(row=0, column=1, padx=5, pady=2)
        self.start_unit = ttk.Label(params_frame, text="V")
        self.start_unit.grid(row=0, column=2, sticky=tk.W)
        
        # Stop value
        ttk.Label(params_frame, text="Stop:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.stop_var = tk.StringVar(value="5")
        self.stop_entry = ttk.Entry(params_frame, textvariable=self.stop_var, width=12)
        self.stop_entry.grid(row=1, column=1, padx=5, pady=2)
        self.stop_unit = ttk.Label(params_frame, text="V")
        self.stop_unit.grid(row=1, column=2, sticky=tk.W)
        
        # Points
        ttk.Label(params_frame, text="Points:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.points_var = tk.StringVar(value="50")
        ttk.Entry(params_frame, textvariable=self.points_var, width=12).grid(
            row=2, column=1, padx=5, pady=2)
        
        # Delay
        ttk.Label(params_frame, text="Delay (ms):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.delay_var = tk.StringVar(value="50")
        ttk.Entry(params_frame, textvariable=self.delay_var, width=12).grid(
            row=3, column=1, padx=5, pady=2)
        
        # Compliance
        ttk.Label(params_frame, text="Compliance:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.sweep_comp_var = tk.StringVar(value="0.1")
        self.sweep_comp_entry = ttk.Entry(params_frame, textvariable=self.sweep_comp_var, 
                                          width=12)
        self.sweep_comp_entry.grid(row=4, column=1, padx=5, pady=2)
        self.comp_unit = ttk.Label(params_frame, text="A")
        self.comp_unit.grid(row=4, column=2, sticky=tk.W)
        
        # Bidirectional sweep
        self.bidir_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(params_frame, text="Bidirectional (forward + reverse)",
                       variable=self.bidir_var).grid(row=5, column=0, 
                       columnspan=3, sticky=tk.W, pady=5)
        
        # Control buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.run_btn = ttk.Button(btn_frame, text="▶ Run Sweep",
                                  command=self._run_sweep,
                                  state=tk.DISABLED)
        self.run_btn.pack(side=tk.LEFT, padx=5)
        
        self.abort_btn = ttk.Button(btn_frame, text="⏹ Abort",
                                    command=self._abort_sweep,
                                    state=tk.DISABLED)
        self.abort_btn.pack(side=tk.LEFT, padx=5)
        
        # Progress
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(self, variable=self.progress_var,
                                            maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        self.status_label = ttk.Label(self, text="Ready")
        self.status_label.pack(anchor=tk.W)
    
    def _on_type_change(self):
        """Handle sweep type change"""
        if self.sweep_type_var.get() == "VOLTAGE":
            self.start_unit.config(text="V")
            self.stop_unit.config(text="V")
            self.comp_unit.config(text="A")
            self.sweep_comp_var.set(str(self.app.safety_limits.compliance_current))
        else:
            self.start_unit.config(text="A")
            self.stop_unit.config(text="A")
            self.comp_unit.config(text="V")
            self.sweep_comp_var.set(str(self.app.safety_limits.compliance_voltage))
    
    def _run_sweep(self):
        """Start sweep measurement"""
        if not self.app.smu:
            return
        
        try:
            start = float(self.start_var.get())
            stop = float(self.stop_var.get())
            points = int(self.points_var.get())
            delay = float(self.delay_var.get()) / 1000  # Convert to seconds
            compliance = float(self.sweep_comp_var.get())
            
            # Confirm sweep
            sweep_type = self.sweep_type_var.get()
            unit = "V" if sweep_type == "VOLTAGE" else "A"
            
            result = messagebox.askyesno(
                "Confirm Sweep",
                f"Run {sweep_type.lower()} sweep?\n\n"
                f"Range: {start} to {stop} {unit}\n"
                f"Points: {points}\n"
                f"Compliance: {compliance} {'A' if sweep_type == 'VOLTAGE' else 'V'}\n\n"
                f"This will enable the output.",
                icon='warning'
            )
            
            if not result:
                return
            
            self.sweep_running = True
            self.run_btn.config(state=tk.DISABLED)
            self.abort_btn.config(state=tk.NORMAL)
            self.progress_var.set(0)
            
            # Run sweep in thread
            thread = threading.Thread(target=self._execute_sweep,
                                     args=(start, stop, points, delay, compliance))
            thread.daemon = True
            thread.start()
            
        except ValueError as e:
            messagebox.showerror("Invalid Input", f"Please enter valid numbers: {e}")
    
    def _execute_sweep(self, start, stop, points, delay, compliance):
        """Execute sweep in background thread"""
        try:
            self.after(0, lambda: self.status_label.config(text="Running sweep..."))
            
            if self.sweep_type_var.get() == "VOLTAGE":
                results = self.app.smu.voltage_sweep(
                    start, stop, points, compliance, delay
                )
            else:
                results = self.app.smu.current_sweep(
                    start, stop, points, compliance, delay
                )
            
            # Add results to data
            for r in results:
                self.app.add_measurement(r)
            
            # Bidirectional: reverse sweep
            if self.bidir_var.get():
                self.after(0, lambda: self.status_label.config(text="Running reverse sweep..."))
                
                if self.sweep_type_var.get() == "VOLTAGE":
                    reverse_results = self.app.smu.voltage_sweep(
                        stop, start, points, compliance, delay
                    )
                else:
                    reverse_results = self.app.smu.current_sweep(
                        stop, start, points, compliance, delay
                    )
                
                for r in reverse_results:
                    self.app.add_measurement(r)
                
                results.extend(reverse_results)
            
            # Update plot
            self.after(0, lambda: self.app.plot_panel.plot_iv_data(results))
            self.after(0, lambda: self.status_label.config(
                text=f"Sweep complete: {len(results)} points"))
            
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Sweep Error", str(e)))
            self.after(0, lambda: self.status_label.config(text=f"Error: {e}"))
        finally:
            self.sweep_running = False
            self.after(0, lambda: self.run_btn.config(state=tk.NORMAL))
            self.after(0, lambda: self.abort_btn.config(state=tk.DISABLED))
            self.after(0, lambda: self.progress_var.set(100))
            
            # Turn off output after sweep
            if self.app.smu:
                self.app.smu.output_off()
                self.after(0, lambda: self.app.output_panel.update_state())
    
    def _abort_sweep(self):
        """Abort running sweep"""
        self.sweep_running = False
        if self.app.smu:
            self.app.smu.output_off()
        self.status_label.config(text="Sweep aborted")
    
    def set_enabled(self, enabled: bool):
        """Enable/disable controls"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.run_btn.config(state=state)


class PlotPanel(ttk.LabelFrame):
    """Panel for data plotting"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="Data Plot", padding=5)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Plot type selection
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(ctrl_frame, text="Plot:").pack(side=tk.LEFT)
        
        self.plot_type_var = tk.StringVar(value="I-V")
        for ptype in ["I-V", "V-t", "I-t", "R-t"]:
            ttk.Radiobutton(ctrl_frame, text=ptype, 
                           variable=self.plot_type_var, value=ptype,
                           command=self._update_plot).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(ctrl_frame, text="Clear", command=self._clear_plot).pack(side=tk.RIGHT, padx=5)
        ttk.Button(ctrl_frame, text="Autoscale", command=self._autoscale).pack(side=tk.RIGHT)
        
        # Matplotlib figure
        self.fig = Figure(figsize=(8, 4), dpi=100, facecolor=ModernStyle.BG_MEDIUM)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(ModernStyle.BG_DARK)
        self.ax.tick_params(colors=ModernStyle.TEXT_PRIMARY)
        self.ax.xaxis.label.set_color(ModernStyle.TEXT_PRIMARY)
        self.ax.yaxis.label.set_color(ModernStyle.TEXT_PRIMARY)
        self.ax.spines['bottom'].set_color(ModernStyle.TEXT_SECONDARY)
        self.ax.spines['top'].set_color(ModernStyle.TEXT_SECONDARY)
        self.ax.spines['left'].set_color(ModernStyle.TEXT_SECONDARY)
        self.ax.spines['right'].set_color(ModernStyle.TEXT_SECONDARY)
        self.fig.tight_layout()
        
        self.canvas = FigureCanvasTkAgg(self.fig, self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Toolbar
        toolbar_frame = ttk.Frame(self)
        toolbar_frame.pack(fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()
        
        # Initialize empty plot
        self._setup_plot()
    
    def _setup_plot(self):
        """Set up initial plot"""
        self.ax.clear()
        self.ax.set_xlabel('Voltage (V)')
        self.ax.set_ylabel('Current (A)')
        self.ax.set_title('I-V Characteristic')
        self.ax.grid(True, alpha=0.3)
        self.ax.set_facecolor(ModernStyle.BG_DARK)
        self.canvas.draw()
    
    def _update_plot(self):
        """Update plot based on selected type"""
        self.ax.clear()
        
        plot_type = self.plot_type_var.get()
        data = self.app.measurement_data
        
        if not data:
            self._setup_plot()
            return
        
        if plot_type == "I-V":
            voltages = [d.voltage for d in data]
            currents = [d.current for d in data]
            self.ax.plot(voltages, currents, 'b.-', markersize=3)
            self.ax.set_xlabel('Voltage (V)')
            self.ax.set_ylabel('Current (A)')
            self.ax.set_title('I-V Characteristic')
            
        elif plot_type == "V-t":
            times = [(d.timestamp - data[0].timestamp) for d in data if d.timestamp]
            voltages = [d.voltage for d in data if d.timestamp]
            self.ax.plot(times, voltages, 'b.-', markersize=3)
            self.ax.set_xlabel('Time (s)')
            self.ax.set_ylabel('Voltage (V)')
            self.ax.set_title('Voltage vs Time')
            
        elif plot_type == "I-t":
            times = [(d.timestamp - data[0].timestamp) for d in data if d.timestamp]
            currents = [d.current for d in data if d.timestamp]
            self.ax.plot(times, currents, 'g.-', markersize=3)
            self.ax.set_xlabel('Time (s)')
            self.ax.set_ylabel('Current (A)')
            self.ax.set_title('Current vs Time')
            
        elif plot_type == "R-t":
            times = [(d.timestamp - data[0].timestamp) for d in data 
                    if d.timestamp and d.resistance]
            resistances = [d.resistance for d in data 
                          if d.timestamp and d.resistance and abs(d.resistance) < 1e9]
            if times and resistances:
                self.ax.plot(times[:len(resistances)], resistances, 'y.-', markersize=3)
            self.ax.set_xlabel('Time (s)')
            self.ax.set_ylabel('Resistance (Ω)')
            self.ax.set_title('Resistance vs Time')
        
        self.ax.grid(True, alpha=0.3)
        self.ax.set_facecolor(ModernStyle.BG_DARK)
        self.fig.tight_layout()
        self.canvas.draw()
    
    def plot_iv_data(self, data: List[MeasurementResult]):
        """Plot IV sweep data"""
        self.ax.clear()
        
        voltages = [d.voltage for d in data]
        currents = [d.current for d in data]
        
        self.ax.plot(voltages, currents, 'b.-', markersize=4, linewidth=1)
        self.ax.set_xlabel('Voltage (V)')
        self.ax.set_ylabel('Current (A)')
        self.ax.set_title('I-V Characteristic')
        self.ax.grid(True, alpha=0.3)
        self.ax.set_facecolor(ModernStyle.BG_DARK)
        self.fig.tight_layout()
        self.canvas.draw()
    
    def _clear_plot(self):
        """Clear the plot"""
        self._setup_plot()
    
    def _autoscale(self):
        """Autoscale the plot"""
        self.ax.autoscale()
        self.canvas.draw()


class DataLogPanel(ttk.LabelFrame):
    """Panel for data logging and export"""
    
    def __init__(self, parent, app):
        super().__init__(parent, text="Data Log", padding=10)
        self.app = app
        self._create_widgets()
    
    def _create_widgets(self):
        # Data table
        columns = ('Time', 'Voltage (V)', 'Current (A)', 'Resistance (Ω)')
        
        self.tree = ttk.Treeview(self, columns=columns, show='headings', height=8)
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Control buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(btn_frame, text="📁 Export CSV", 
                  command=self._export_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📋 Copy", 
                  command=self._copy_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🗑 Clear Data", 
                  command=self._clear_data).pack(side=tk.LEFT, padx=5)
        
        # Data count
        self.count_label = ttk.Label(btn_frame, text="0 points")
        self.count_label.pack(side=tk.RIGHT, padx=10)
    
    def add_measurement(self, result: MeasurementResult):
        """Add measurement to log"""
        timestamp = datetime.fromtimestamp(result.timestamp).strftime('%H:%M:%S.%f')[:-3] \
                   if result.timestamp else "N/A"
        
        resistance = f"{result.resistance:.2f}" if result.resistance and abs(result.resistance) < 1e9 else "---"
        
        self.tree.insert('', 'end', values=(
            timestamp,
            f"{result.voltage:.6f}",
            f"{result.current:.9f}",
            resistance
        ))
        
        # Auto-scroll to bottom
        self.tree.yview_moveto(1)
        
        # Update count
        self.count_label.config(text=f"{len(self.tree.get_children())} points")
    
    def _export_csv(self):
        """Export data to CSV file"""
        if not self.tree.get_children():
            messagebox.showwarning("No Data", "No data to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"keithley_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if not filename:
            return
        
        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Time', 'Voltage (V)', 'Current (A)', 'Resistance (Ω)'])
                
                for item in self.tree.get_children():
                    writer.writerow(self.tree.item(item)['values'])
            
            messagebox.showinfo("Export Complete", f"Data exported to:\n{filename}")
            
        except Exception as e:
            messagebox.showerror("Export Error", str(e))
    
    def _copy_data(self):
        """Copy data to clipboard"""
        if not self.tree.get_children():
            return
        
        data = "Time\tVoltage (V)\tCurrent (A)\tResistance (Ω)\n"
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            data += "\t".join(str(v) for v in values) + "\n"
        
        self.clipboard_clear()
        self.clipboard_append(data)
        
    def _clear_data(self):
        """Clear all data"""
        if messagebox.askyesno("Clear Data", "Clear all measurement data?"):
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.app.measurement_data.clear()
            self.count_label.config(text="0 points")
            self.app.plot_panel._update_plot()


class Keithley2450App:
    """Main application class"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Keithley 2450 SourceMeter Control")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)
        
        # Application state
        self.smu: Optional[Keithley2450] = None
        self.connected = False
        self.safety_limits = SafetyLimits()
        self.measurement_data: List[MeasurementResult] = []
        
        # Configure styles
        self._configure_styles()
        
        # Create menu
        self._create_menu()
        
        # Create main layout
        self._create_layout()
        
        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _configure_styles(self):
        """Configure ttk styles"""
        style = ttk.Style()
        
        # Use clam theme as base
        style.theme_use('clam')
        
        # Configure colors
        style.configure('.', 
                       background=ModernStyle.BG_MEDIUM,
                       foreground=ModernStyle.TEXT_PRIMARY,
                       fieldbackground=ModernStyle.BG_LIGHT)
        
        style.configure('TFrame', background=ModernStyle.BG_MEDIUM)
        style.configure('TLabel', background=ModernStyle.BG_MEDIUM,
                       foreground=ModernStyle.TEXT_PRIMARY)
        style.configure('TLabelframe', background=ModernStyle.BG_MEDIUM)
        style.configure('TLabelframe.Label', background=ModernStyle.BG_MEDIUM,
                       foreground=ModernStyle.TEXT_PRIMARY,
                       font=ModernStyle.FONT_HEADER)
        
        style.configure('TButton', padding=5)
        style.configure('TEntry', fieldbackground=ModernStyle.BG_LIGHT)
        
        style.configure('TRadiobutton', background=ModernStyle.BG_MEDIUM,
                       foreground=ModernStyle.TEXT_PRIMARY)
        style.configure('TCheckbutton', background=ModernStyle.BG_MEDIUM,
                       foreground=ModernStyle.TEXT_PRIMARY)
        
        # Notebook style
        style.configure('TNotebook', background=ModernStyle.BG_MEDIUM)
        style.configure('TNotebook.Tab', background=ModernStyle.BG_LIGHT,
                       foreground=ModernStyle.TEXT_PRIMARY, padding=[10, 5])
        style.map('TNotebook.Tab',
                 background=[('selected', ModernStyle.ACCENT_BLUE)],
                 foreground=[('selected', 'white')])
    
    def _create_menu(self):
        """Create application menu"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Export Data...", command=self._export_data)
        file_menu.add_command(label="Load Settings...", command=self._load_settings)
        file_menu.add_command(label="Save Settings...", command=self._save_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        
        # Instrument menu
        inst_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Instrument", menu=inst_menu)
        inst_menu.add_command(label="Reset", command=self._reset_instrument)
        inst_menu.add_command(label="Local Mode", command=self._local_mode)
        inst_menu.add_separator()
        inst_menu.add_command(label="Safety Settings...", command=self._safety_settings)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)
    
    def _create_layout(self):
        """Create main application layout"""
        # Main container
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left panel (controls)
        left_panel = ttk.Frame(main_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # Connection panel
        self.connection_panel = ConnectionPanel(left_panel, self)
        self.connection_panel.pack(fill=tk.X, pady=(0, 10))
        
        # Output panel
        self.output_panel = OutputPanel(left_panel, self)
        self.output_panel.pack(fill=tk.X, pady=(0, 10))
        
        # Source panel
        self.source_panel = SourcePanel(left_panel, self)
        self.source_panel.pack(fill=tk.X, pady=(0, 10))
        
        # Right panel (measurements, sweep, plot)
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Top right - Measurements
        self.measurement_panel = MeasurementPanel(right_panel, self)
        self.measurement_panel.pack(fill=tk.X, pady=(0, 10))
        
        # Notebook for sweep and data
        notebook = ttk.Notebook(right_panel)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Sweep tab
        sweep_frame = ttk.Frame(notebook)
        notebook.add(sweep_frame, text="IV Sweep")
        
        self.sweep_panel = SweepPanel(sweep_frame, self)
        self.sweep_panel.pack(fill=tk.X, pady=5, padx=5)
        
        self.plot_panel = PlotPanel(sweep_frame, self)
        self.plot_panel.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)
        
        # Data log tab
        data_frame = ttk.Frame(notebook)
        notebook.add(data_frame, text="Data Log")
        
        self.datalog_panel = DataLogPanel(data_frame, self)
        self.datalog_panel.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)
        
        # Status bar
        self.status_bar = ttk.Label(self.root, text="Ready", 
                                    relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def update_connection_state(self, connected: bool):
        """Update all panels based on connection state"""
        self.output_panel.set_enabled(connected)
        self.source_panel.set_enabled(connected)
        self.measurement_panel.set_enabled(connected)
        self.sweep_panel.set_enabled(connected)
        
        if connected:
            self.status_bar.config(text="Connected - Ready")
        else:
            self.status_bar.config(text="Disconnected")
    
    def add_measurement(self, result: MeasurementResult):
        """Add measurement to data store and log"""
        self.measurement_data.append(result)
        self.datalog_panel.add_measurement(result)
    
    def _export_data(self):
        """Export measurement data"""
        self.datalog_panel._export_csv()
    
    def _load_settings(self):
        """Load settings from file"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'r') as f:
                    settings = json.load(f)
                
                if 'safety_limits' in settings:
                    sl = settings['safety_limits']
                    self.safety_limits = SafetyLimits(
                        max_voltage=sl.get('max_voltage', 20.0),
                        min_voltage=sl.get('min_voltage', -20.0),
                        max_current=sl.get('max_current', 0.1),
                        min_current=sl.get('min_current', -0.1),
                        compliance_voltage=sl.get('compliance_voltage', 21.0),
                        compliance_current=sl.get('compliance_current', 0.105),
                        power_limit=sl.get('power_limit', 20.0)
                    )
                
                messagebox.showinfo("Settings Loaded", "Settings loaded successfully")
                
            except Exception as e:
                messagebox.showerror("Load Error", str(e))
    
    def _save_settings(self):
        """Save settings to file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="keithley_settings.json"
        )
        if filename:
            try:
                settings = {
                    'safety_limits': {
                        'max_voltage': self.safety_limits.max_voltage,
                        'min_voltage': self.safety_limits.min_voltage,
                        'max_current': self.safety_limits.max_current,
                        'min_current': self.safety_limits.min_current,
                        'compliance_voltage': self.safety_limits.compliance_voltage,
                        'compliance_current': self.safety_limits.compliance_current,
                        'power_limit': self.safety_limits.power_limit
                    }
                }
                
                with open(filename, 'w') as f:
                    json.dump(settings, f, indent=2)
                
                messagebox.showinfo("Settings Saved", f"Settings saved to:\n{filename}")
                
            except Exception as e:
                messagebox.showerror("Save Error", str(e))
    
    def _reset_instrument(self):
        """Reset instrument to defaults"""
        if self.smu:
            if messagebox.askyesno("Reset Instrument", 
                                  "Reset instrument to defaults?\nThis will turn off the output."):
                try:
                    self.smu.reset()
                    self.output_panel.update_state()
                    messagebox.showinfo("Reset", "Instrument reset to defaults")
                except Exception as e:
                    messagebox.showerror("Reset Error", str(e))
    
    def _local_mode(self):
        """Return instrument to local mode"""
        if self.smu:
            try:
                self.smu.local_mode()
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def _safety_settings(self):
        """Open safety settings dialog"""
        dialog = SafetySettingsDialog(self.root, self.safety_limits)
        self.root.wait_window(dialog)
        
        if dialog.result:
            self.safety_limits = dialog.result
            
            # Update SMU if connected
            if self.smu:
                self.smu.safety_limits = self.safety_limits
            
            messagebox.showinfo("Safety Settings", "Safety limits updated")
    
    def _show_about(self):
        """Show about dialog"""
        messagebox.showinfo(
            "About",
            "Keithley 2450 SourceMeter Control\n\n"
            "Version 1.0\n"
            "A professional control application for the\n"
            "Keithley 2450 Source Measure Unit.\n\n"
            "Features:\n"
            "• Safe operation with configurable limits\n"
            "• Source voltage/current with compliance\n"
            "• IV sweep measurements\n"
            "• Real-time data plotting\n"
            "• Data export to CSV"
        )
    
    def _on_close(self):
        """Handle application close"""
        # Stop any running measurements
        self.measurement_panel.measuring = False
        
        # Disconnect from instrument
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
