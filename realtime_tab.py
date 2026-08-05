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

from PyQt5.QtCore import Qt
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
    QSplitter,
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

        # Splitter so the user can drag-to-shrink the controls panel.
        # Controls on the LEFT, plot on the RIGHT.
        splitter = QSplitter(Qt.Horizontal)
        controls = self._build_controls_panel()
        controls.setMinimumWidth(80)   # can shrink but not fully collapse by mistake
        splitter.addWidget(controls)
        splitter.addWidget(self._build_plot())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, True)   # drag all the way to hide
        splitter.setCollapsible(1, False)
        splitter.setSizes([340, 900])
        outer.addWidget(splitter, stretch=1)

        outer.addLayout(self._build_action_row())

    def _build_controls_panel(self) -> QGroupBox:
        group = QGroupBox("Signals")
        group.setMinimumWidth(80)
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        # Header row (all black; only tick numbers/units on the plot get color)
        headers = ["", "Signal", "Unit", "Auto"]
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
            name_lbl.setStyleSheet("color: #000000; font-weight: bold; font-size: 13px;")
            grid.addWidget(name_lbl, row, 1)

            unit_combo = QComboBox()
            for unit_label, _ in spec.units:
                unit_combo.addItem(unit_label)
            unit_combo.currentIndexChanged.connect(
                lambda idx, k=spec.key: self._on_unit_changed(k, idx)
            )
            grid.addWidget(unit_combo, row, 2)

            auto_cb = QCheckBox()
            auto_cb.setChecked(True)
            auto_cb.toggled.connect(
                lambda checked, k=spec.key: self._on_auto_range_toggled(k, checked)
            )
            grid.addWidget(auto_cb, row, 3)

            self._control_rows[spec.key] = {
                "show": show_cb,
                "name": name_lbl,
                "unit": unit_combo,
                "auto": auto_cb,
            }
            row += 1

        grid.setRowStretch(row, 1)
        return group

    def create_status_values_widget(self) -> QWidget:
        """Compact per-signal value strip meant to sit in the app status bar.

        Text (signal name) is black; the numeric value + unit are colored.
        Only signals currently `available` are shown.
        """
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self._status_labels: dict[str, QLabel] = {}
        for spec in SIGNAL_CATALOG:
            lbl = QLabel()
            lbl.setTextFormat(Qt.RichText)
            lbl.setStyleSheet("font-size: 12px;")
            layout.addWidget(lbl)
            self._status_labels[spec.key] = lbl
            lbl.setVisible(self._series[spec.key].available)
        return w

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
            s.curve = pg.PlotDataItem(pen=pg.mkPen(spec.color, width=1))
            s.view_box.addItem(s.curve)
            # Right-side axis for this signal, created once, reused.
            # Axis line = black, tick numbers = colored, label = mixed
            # (name black + unit colored) via HTML in setLabel.
            s.axis = pg.AxisItem("right")
            s.axis.setLabel(_axis_label_html(spec.name, s.current_unit_label(), spec.color))
            s.axis.setPen("#000000")
            s.axis.setTextPen(spec.color)
            s.axis.linkToView(s.view_box)

        # Keep aux ViewBoxes' geometry synced with the main plot area
        plot_item.vb.sigResized.connect(self._sync_viewboxes)
        # Manual pan/zoom on X disables Follow so the user can navigate
        # earlier data without the plot snapping back on the next sample.
        plot_item.vb.sigRangeChangedManually.connect(self._on_manual_range_change)

        self._rebuild_axes()
        return self._plot

    def _on_manual_range_change(self, _mask=None) -> None:
        if getattr(self, "follow_cb", None) is not None and self.follow_cb.isChecked():
            self.follow_cb.setChecked(False)

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.follow_cb = QCheckBox("Follow")
        self.follow_cb.setChecked(True)
        self.follow_cb.setToolTip(
            "Auto-scroll X so the latest sample stays at the right edge.\n"
            "Preserves the current X window width; disables when you pan/zoom X."
        )
        row.addWidget(self.follow_cb)

        self.reset_btn = QPushButton("Reset View")
        self.reset_btn.setToolTip(
            "Re-enable auto-range on X and every visible signal's Y axis.\n"
            "Use when scrolling or zooming has left the plot in a weird state."
        )
        self.reset_btn.clicked.connect(self._on_reset_view)
        row.addWidget(self.reset_btn)

        row.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._on_clear)
        row.addWidget(self.clear_btn)
        self.save_btn = QPushButton("Save CSV…")
        self.save_btn.clicked.connect(self._on_save_csv)
        row.addWidget(self.save_btn)
        return row

    def _on_reset_view(self) -> None:
        primary = self._plot.plotItem.vb
        primary.enableAutoRange(axis=pg.ViewBox.XAxis, enable=True)
        for s in self._series.values():
            if s.view_box is not None and s.available and s.visible:
                s.view_box.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
                # Also re-sync the per-signal auto-range checkbox
                row = self._control_rows.get(s.spec.key)
                if row is not None:
                    row["auto"].setChecked(True)

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

        # First visible signal owns the built-in left axis. Axis line black,
        # tick numbers in the signal's color, label uses HTML so the signal
        # name is black and the unit is colored.
        first = visible[0]
        left_axis.linkToView(first.view_box)
        left_axis.setLabel(_axis_label_html(first.spec.name, first.current_unit_label(), first.spec.color))
        left_axis.setPen("#000000")
        left_axis.setTextPen(first.spec.color)
        plot_item.showAxis("left")

        # Remaining visible signals: right-side stacked axes (innermost first)
        for i, s in enumerate(visible[1:]):
            s.axis.setLabel(_axis_label_html(s.spec.name, s.current_unit_label(), s.spec.color))
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
        # Redraw any axis showing this signal (its own right-axis or the
        # built-in left-axis if it's the first-visible).
        new_label = _axis_label_html(s.spec.name, s.current_unit_label(), s.spec.color)
        if s.axis is not None:
            s.axis.setLabel(new_label)
        left_axis = self._plot.plotItem.getAxis("left")
        visible = [self._series[spec.key] for spec in SIGNAL_CATALOG
                   if self._series[spec.key].available and self._series[spec.key].visible]
        if visible and visible[0] is s:
            left_axis.setLabel(new_label)
        if s.curve is not None and s.visible:
            s.curve.setData(s.xs, s.display_ys())
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
        the control panel + status-bar strip; they cannot be toggled on.
        """
        available_set = set(keys)
        for spec in SIGNAL_CATALOG:
            s = self._series[spec.key]
            avail = spec.key in available_set
            s.available = avail
            row = self._control_rows.get(spec.key)
            if row is not None:
                for w in (row["show"], row["name"], row["unit"], row["auto"]):
                    w.setVisible(avail)
            labels = getattr(self, "_status_labels", None)
            if labels is not None and spec.key in labels:
                labels[spec.key].setVisible(avail)
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
        # Follow mode: X ranges from 0 to the latest sample time — t=0 pinned
        # to the left, right edge auto-expands as new data arrives.
        if getattr(self, "follow_cb", None) is not None and self.follow_cb.isChecked():
            max_t = max(
                (series.xs[-1] for series in self._series.values() if series.xs),
                default=rel_t,
            )
            if max_t <= 0:
                max_t = 0.01
            self._plot.plotItem.vb.setXRange(0.0, max_t, padding=0.02)

    def _update_value_label(self, s: Series) -> None:
        if not s.ys_base:
            return
        labels = getattr(self, "_status_labels", None)
        if labels is None:
            return
        lbl = labels.get(s.spec.key)
        if lbl is None:
            return
        transform = s.spec.units[s.unit_index][1]
        display_val = transform(s.ys_base[-1])
        # 9 significant digits preserves the full float32 wire precision
        # without cluttering the display with FP-noise trailing digits.
        val_str = f"{display_val:.9g}"
        unit = s.current_unit_label()
        lbl.setText(
            f"<span style='color:#000000;'>{s.spec.name}:</span> "
            f"<span style='color:{s.spec.color};font-weight:bold;'>{val_str} {unit}</span>"
        )

    # ---- Actions -----------------------------------------------------------

    def _on_clear(self) -> None:
        for s in self._series.values():
            s.xs.clear()
            s.ys_base.clear()
            if s.curve is not None:
                s.curve.setData([], [])
            labels = getattr(self, "_status_labels", None)
            if labels is not None and s.spec.key in labels:
                labels[s.spec.key].setText("")

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
            with open(path, "w", newline="", encoding="cp1252", errors="replace") as f:
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


def _axis_label_html(name: str, unit: str, color: str) -> str:
    """Axis label with the signal name in black and the unit in the signal's
    color. pyqtgraph AxisItem.setLabel accepts HTML."""
    return (
        f"<span style='color:#000000;'>{name} </span>"
        f"<span style='color:{color};'>({unit})</span>"
    )


