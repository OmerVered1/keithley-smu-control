"""
Real Time tab
=============
Unified live view of the connected calorimeter (Heat Flow, Sample T, and
External T if present) and any running K2602B sweep (Voltage, Current,
Resistance, Power) in one time-locked plot.

Controls (one row per signal):
    [ show ✓ ] [ Name ]   value + unit   [ Unit ▾ ] [ auto-range ✓ ]

Layout of Y axes as signals are toggled on/off:
    1 visible → left
    2 visible → left + right
    3 visible → left + right + right-outer
    4 visible → left-outer + left + right + right-outer
    5 visible → left-outer + left + right + right-outer + right-farther
    6+ visible → alternate further outward, always keeping visible signals
                 distributed on both sides of the plot area.

Time axis semantics:
    - Default: X = seconds since calorimeter was connected.
    - On experiment (sweep) start: X = seconds since experiment start;
      plot buffers are cleared so the new run starts at t=0.
    - On experiment end: X keeps the experiment-start reference so the
      completed run stays visible; next Connect or next experiment resets.
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass, field

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg


# ---- Signal catalog --------------------------------------------------------

# Each signal has a unique key, display name, list of unit options, and color.
# Unit options: (display_label, transform_from_base_fn). The base unit is the
# first entry — any raw sample coming into the tab is assumed to be in that
# unit; the transform converts to whatever the user picked in the dropdown.

def _mul(factor: float):
    return lambda x: x * factor

def _c_to_k(x: float) -> float: return x + 273.15
def _c_to_f(x: float) -> float: return x * 9.0 / 5.0 + 32.0


@dataclass
class SignalSpec:
    key: str
    name: str
    color: str
    units: list[tuple[str, callable]]   # (label, base→display fn)


SIGNAL_CATALOG: list[SignalSpec] = [
    SignalSpec("hf",    "Heat Flow",            "#dc2626",
               [("mW", _mul(1)), ("µW", _mul(1000)), ("W", _mul(1e-3)), ("kW", _mul(1e-6))]),
    SignalSpec("t",     "Sample Temperature",   "#2563eb",
               [("°C", _mul(1)), ("K", _c_to_k), ("°F", _c_to_f)]),
    SignalSpec("ext_t", "External Temperature", "#ea580c",
               [("°C", _mul(1)), ("K", _c_to_k), ("°F", _c_to_f)]),
    SignalSpec("v",     "Voltage",              "#16a34a",
               [("V", _mul(1)), ("mV", _mul(1000)), ("µV", _mul(1e6)), ("kV", _mul(1e-3))]),
    SignalSpec("i",     "Current",              "#f59e0b",
               [("A", _mul(1)), ("mA", _mul(1000)), ("µA", _mul(1e6)), ("nA", _mul(1e9))]),
    SignalSpec("r",     "Resistance",           "#8b5cf6",
               [("Ω", _mul(1)), ("kΩ", _mul(1e-3)), ("MΩ", _mul(1e-6)), ("mΩ", _mul(1000))]),
    SignalSpec("p",     "Power",                "#0891b2",
               [("W", _mul(1)), ("mW", _mul(1000)), ("µW", _mul(1e6)), ("kW", _mul(1e-3))]),
]

MUTED = "#6b7280"


@dataclass
class Series:
    spec: SignalSpec
    xs: list[float] = field(default_factory=list)
    ys_base: list[float] = field(default_factory=list)   # values in base unit
    curve: pg.PlotDataItem = None
    axis: pg.AxisItem = None
    view_box: pg.ViewBox = None
    available: bool = True    # instrument exposes it
    visible: bool = True      # user has it toggled on
    unit_index: int = 0
    auto_range: bool = True

    def display_ys(self) -> list[float]:
        transform = self.spec.units[self.unit_index][1]
        return [transform(y) for y in self.ys_base]

    def current_unit_label(self) -> str:
        return self.spec.units[self.unit_index][0]


class RealTimeTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._t_ref: float | None = None
        self._t_ref_source: str = "connect"

        self._series: dict[str, Series] = {
            spec.key: Series(spec=spec) for spec in SIGNAL_CATALOG
        }

        # Row-widgets we need to refer to later, keyed by signal key
        self._control_rows: dict[str, dict] = {}

        self._setup_ui()
        # Start with only calorimeter defaults visible (V/I/R/P off) — Keithley
        # signals only make sense during a sweep. The K2602B app will call
        # set_available_signals() when a calorimeter connects.
        for key in ("v", "i", "r", "p"):
            self._series[key].visible = False

    # ---- UI construction ---------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # Two-column layout: plot on the left, per-signal controls on the right
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(self._build_plot(), stretch=1)
        top.addWidget(self._build_controls_panel())
        outer.addLayout(top, stretch=1)

        outer.addLayout(self._build_action_row())

    def _build_controls_panel(self) -> QGroupBox:
        group = QGroupBox("Signals")
        group.setMinimumWidth(340)
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        # Header row
        headers = ["", "Signal", "Value", "Unit", "Auto"]
        for col, text in enumerate(headers):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
            grid.addWidget(lbl, 0, col)

        row = 1
        for spec in SIGNAL_CATALOG:
            s = self._series[spec.key]

            show_cb = QCheckBox()
            show_cb.setChecked(s.visible)
            show_cb.toggled.connect(
                lambda checked, k=spec.key: self._on_show_toggled(k, checked)
            )
            grid.addWidget(show_cb, row, 0)

            name_lbl = QLabel(spec.name)
            name_lbl.setStyleSheet(
                f"color: {spec.color}; font-weight: bold; font-size: 13px;"
            )
            grid.addWidget(name_lbl, row, 1)

            value_lbl = QLabel("—")
            value_lbl.setStyleSheet(f"color: {spec.color}; font-size: 13px; font-family: monospace;")
            value_lbl.setMinimumWidth(85)
            grid.addWidget(value_lbl, row, 2)

            unit_combo = QComboBox()
            for unit_label, _ in spec.units:
                unit_combo.addItem(unit_label)
            unit_combo.currentIndexChanged.connect(
                lambda idx, k=spec.key: self._on_unit_changed(k, idx)
            )
            grid.addWidget(unit_combo, row, 3)

            auto_cb = QCheckBox()
            auto_cb.setChecked(True)
            auto_cb.toggled.connect(
                lambda checked, k=spec.key: self._on_auto_range_toggled(k, checked)
            )
            grid.addWidget(auto_cb, row, 4)

            self._control_rows[spec.key] = {
                "show": show_cb,
                "name": name_lbl,
                "value": value_lbl,
                "unit": unit_combo,
                "auto": auto_cb,
            }
            row += 1

        grid.setRowStretch(row, 1)
        return group

    def _build_plot(self) -> pg.PlotWidget:
        self._plot = pg.PlotWidget()
        self._plot.setBackground("w")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        plot_item = self._plot.plotItem
        plot_item.setLabel("bottom", "Time since connect (s)")

        # Hide both built-in Y axes; _rebuild_axes decides which to show and
        # what stacked right-axes to add.
        plot_item.hideAxis("left")
        plot_item.hideAxis("right")

        # One ViewBox per signal. The one signal that occupies the "left"
        # slot at any time uses the plot's own vb (linked to the built-in
        # left axis when shown). All other signals get their own extra
        # ViewBox + AxisItem stacked on the right.
        for spec in SIGNAL_CATALOG:
            s = self._series[spec.key]
            s.view_box = pg.ViewBox()
            s.view_box.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
            plot_item.scene().addItem(s.view_box)
            s.view_box.setXLink(plot_item.vb)
            s.curve = pg.PlotDataItem(pen=pg.mkPen(spec.color, width=2))
            s.view_box.addItem(s.curve)
            # Right-side axis for this signal, created once, reused
            s.axis = pg.AxisItem("right")
            s.axis.setLabel(f"{spec.name} ({s.current_unit_label()})", color=spec.color)
            s.axis.setPen(spec.color)
            s.axis.setTextPen(spec.color)
            s.axis.linkToView(s.view_box)

        # Keep aux ViewBoxes' geometry synced with the main plot area
        plot_item.vb.sigResized.connect(self._sync_viewboxes)

        self._rebuild_axes()
        return self._plot

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._on_clear)
        row.addWidget(self.clear_btn)
        self.save_btn = QPushButton("Save CSV…")
        self.save_btn.clicked.connect(self._on_save_csv)
        row.addWidget(self.save_btn)
        return row

    # ---- Axis layout -------------------------------------------------------

    def _rebuild_axes(self) -> None:
        """Assign visible signals to axis slots.

        Rule: at most one axis on the left (the plot's built-in left axis,
        linked to the first-visible signal's ViewBox). All other visible
        signals get their own AxisItem stacked outward on the right, in
        SIGNAL_CATALOG order. Matches Omer's stated examples:
            n=1  → left
            n=2  → left + right
            n=3  → left + 2 right (innermost + outer)
            n=4+ → left + more right
        """
        plot_item = self._plot.plotItem
        layout = plot_item.layout

        # Detach all right-side axes from the layout
        for s in self._series.values():
            try:
                layout.removeItem(s.axis)
            except Exception:
                pass
            s.axis.hide()

        visible = [self._series[spec.key] for spec in SIGNAL_CATALOG
                   if self._series[spec.key].available and self._series[spec.key].visible]

        left_axis = plot_item.getAxis("left")
        if not visible:
            plot_item.hideAxis("left")
            layout.invalidate()
            self._sync_viewboxes()
            return

        # First visible signal owns the built-in left axis
        first = visible[0]
        left_axis.linkToView(first.view_box)
        left_axis.setLabel(f"{first.spec.name} ({first.current_unit_label()})",
                           color=first.spec.color)
        left_axis.setPen(first.spec.color)
        left_axis.setTextPen(first.spec.color)
        plot_item.showAxis("left")

        # Remaining visible signals: right-side stacked axes (innermost first)
        for i, s in enumerate(visible[1:]):
            s.axis.setLabel(f"{s.spec.name} ({s.current_unit_label()})",
                            color=s.spec.color)
            layout.addItem(s.axis, 2, 2 + i)
            s.axis.show()

        layout.invalidate()
        self._sync_viewboxes()

    def _sync_viewboxes(self) -> None:
        primary = self._plot.plotItem.vb
        rect = primary.sceneBoundingRect()
        for s in self._series.values():
            if s.view_box is not None and s.view_box is not primary:
                s.view_box.setGeometry(rect)
                s.view_box.linkedViewChanged(primary, s.view_box.XAxis)

    # ---- Signal control handlers ------------------------------------------

    def _on_show_toggled(self, key: str, checked: bool) -> None:
        s = self._series[key]
        s.visible = checked
        if s.curve is not None:
            if checked:
                s.curve.setData(s.xs, s.display_ys())
            else:
                s.curve.setData([], [])
        self._rebuild_axes()

    def _on_unit_changed(self, key: str, idx: int) -> None:
        s = self._series[key]
        s.unit_index = idx
        if s.axis is not None:
            s.axis.setLabel(f"{s.spec.name} ({s.current_unit_label()})",
                            color=s.spec.color)
        if s.curve is not None and s.visible:
            s.curve.setData(s.xs, s.display_ys())
        # Update value readout too
        if s.ys_base:
            self._update_value_label(s)

    def _on_auto_range_toggled(self, key: str, checked: bool) -> None:
        s = self._series[key]
        s.auto_range = checked
        if s.view_box is not None:
            s.view_box.enableAutoRange(axis=pg.ViewBox.YAxis, enable=checked)

    # ---- Public API called by Keithley2602BApp -----------------------------

    def set_available_signals(self, keys: list[str]) -> None:
        """Hide control rows for signals not exposed by the current
        instrument. `keys` is a list of signal keys ("hf", "t", "ext_t", …).
        Signals not in `keys` become both `available=False` and hidden in
        the control panel; they cannot be toggled on.
        """
        available_set = set(keys)
        for spec in SIGNAL_CATALOG:
            s = self._series[spec.key]
            avail = spec.key in available_set
            s.available = avail
            row = self._control_rows.get(spec.key)
            if row is None:
                continue
            # Hide/show the row
            for w in (row["show"], row["name"], row["value"], row["unit"], row["auto"]):
                w.setVisible(avail)
            if not avail:
                s.visible = False
        self._rebuild_axes()

    def set_reference_now(self, source: str) -> None:
        """Reset the X-axis reference to now. `source` in {"connect", "experiment"}."""
        self._t_ref = time.time()
        self._t_ref_source = source
        label = "connect" if source == "connect" else "experiment"
        self._plot.plotItem.setLabel("bottom", f"Time since {label} (s)")
        for s in self._series.values():
            s.xs.clear()
            s.ys_base.clear()
            if s.curve is not None:
                s.curve.setData([], [])

    def push_calorimeter_sample(self, wall_ts: float, readings: dict) -> None:
        """`readings` keys: "hf", "t", "ext_t" (any subset)."""
        for key in ("hf", "t", "ext_t"):
            if key in readings:
                self._append(key, wall_ts, float(readings[key]))

    def push_keithley_sample(self, wall_ts: float, v, i, r, p) -> None:
        for key, value in (("v", v), ("i", i), ("r", r), ("p", p)):
            if value is None:
                continue
            self._append(key, wall_ts, float(value))

    def _append(self, key: str, wall_ts: float, value_base: float) -> None:
        s = self._series[key]
        if not s.available:
            return
        if self._t_ref is None:
            self._t_ref = wall_ts
            self._t_ref_source = "connect"
            self._plot.plotItem.setLabel("bottom", "Time since connect (s)")
        rel_t = wall_ts - self._t_ref
        s.xs.append(rel_t)
        s.ys_base.append(value_base)
        if s.visible and s.curve is not None:
            s.curve.setData(s.xs, s.display_ys())
        self._update_value_label(s)

    def _update_value_label(self, s: Series) -> None:
        row = self._control_rows.get(s.spec.key)
        if row is None or not s.ys_base:
            return
        transform = s.spec.units[s.unit_index][1]
        display_val = transform(s.ys_base[-1])
        row["value"].setText(f"{display_val:.4g} {s.current_unit_label()}")

    # ---- Actions -----------------------------------------------------------

    def _on_clear(self) -> None:
        for s in self._series.values():
            s.xs.clear()
            s.ys_base.clear()
            if s.curve is not None:
                s.curve.setData([], [])
            row = self._control_rows.get(s.spec.key)
            if row is not None:
                row["value"].setText("—")

    def _on_save_csv(self) -> None:
        n = sum(len(s.xs) for s in self._series.values() if s.available)
        if n == 0:
            QMessageBox.information(self, "Nothing to save", "No samples recorded yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Real-Time log as CSV", "realtime_log.csv", "CSV files (*.csv)"
        )
        if not path:
            return

        timeline: dict[float, dict[str, float]] = {}
        for s in self._series.values():
            if not s.available:
                continue
            for x, y in zip(s.xs, s.ys_base):
                timeline.setdefault(x, {})[s.spec.key] = y

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                header = ["time_s"]
                cols: list[Series] = [s for s in self._series.values() if s.available]
                for s in cols:
                    # Base unit for the CSV (unambiguous, unit-agnostic)
                    base_unit = s.spec.units[0][0]
                    header.append(f"{s.spec.name} ({base_unit})")
                w.writerow(header)
                for t_rel in sorted(timeline.keys()):
                    row_vals = [t_rel]
                    for s in cols:
                        row_vals.append(timeline[t_rel].get(s.spec.key, ""))
                    w.writerow(row_vals)
        except OSError as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return
        QMessageBox.information(
            self, "Saved", f"Wrote {len(timeline)} rows to\n{path}"
        )


