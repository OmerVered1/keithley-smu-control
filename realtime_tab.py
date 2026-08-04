"""
Real Time tab
=============
Unified live view of the connected calorimeter (HF, T) and any running
K2602B sweep (V, I, R, P) in one time-locked plot. The tab is display-only —
connection is managed elsewhere (see ConnectionDialog in
keithley2602b_pyqt.py).

Time axis semantics:
    - Default: X = seconds since calorimeter was connected.
    - On experiment (sweep) start: X = seconds since experiment start.
      The plot buffers are cleared so the new run starts at t=0.
    - On experiment end: X keeps the experiment-start reference so the
      completed run stays visible. The next Connect or the next
      experiment resets it again.

Legend items are click-to-toggle: click a signal name to hide/show the
line and switch the Y-axis to that signal's units.
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass, field

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg


# name, unit, color
SIGNAL_SPECS = [
    ("HF", "mW", "#dc2626"),   # red
    ("T",  "°C", "#2563eb"),   # blue
    ("V",  "V",  "#16a34a"),   # green
    ("I",  "A",  "#f59e0b"),   # amber
    ("R",  "Ω",  "#8b5cf6"),   # purple
    ("P",  "W",  "#0891b2"),   # cyan
]

MUTED = "#6b7280"


@dataclass
class Series:
    name: str
    unit: str
    color: str
    xs: list[float] = field(default_factory=list)
    ys: list[float] = field(default_factory=list)
    curve: pg.PlotDataItem = None
    axis: pg.AxisItem = None
    view_box: pg.ViewBox = None
    axis_row: int = 2
    axis_col: int = 0
    visible: bool = True
    legend_btn: QPushButton = None


class RealTimeTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Absolute wall-clock reference (seconds since epoch). t_ref is None
        # until the calorimeter or an experiment sets it.
        self._t_ref: float | None = None
        self._t_ref_source: str = "connect"   # "connect" or "experiment"

        self._series: dict[str, Series] = {
            name: Series(name=name, unit=unit, color=color)
            for name, unit, color in SIGNAL_SPECS
        }

        self._setup_ui()

    # ---- UI construction ---------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        outer.addLayout(self._build_readout_row())
        outer.addLayout(self._build_legend_row())
        outer.addWidget(self._build_plot(), stretch=1)
        outer.addLayout(self._build_action_row())

    def _build_readout_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._readout_labels: dict[str, QLabel] = {}
        for name, unit, color in SIGNAL_SPECS:
            lbl = QLabel(f"{name}: —")
            lbl.setFont(QFont("Inter", 14, QFont.Bold))
            lbl.setStyleSheet(f"color: {color};")
            self._readout_labels[name] = lbl
            row.addWidget(lbl)
            row.addSpacing(6)
        row.addStretch()
        return row

    def _build_legend_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Show:"))
        for name, unit, color in SIGNAL_SPECS:
            btn = QPushButton(f"■ {name} ({unit})")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self._legend_style(color, active=True))
            btn.clicked.connect(lambda checked, n=name: self._on_legend_toggle(n, checked))
            self._series[name].legend_btn = btn
            row.addWidget(btn)
        row.addStretch()
        return row

    @staticmethod
    def _legend_style(color: str, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ color: {color}; background: transparent; "
                f"border: 1px solid {color}; border-radius: 4px; padding: 3px 8px; "
                f"font-weight: bold; }}"
                f"QPushButton:hover {{ background: rgba(0,0,0,0.05); }}"
            )
        return (
            f"QPushButton {{ color: {MUTED}; background: transparent; "
            f"border: 1px solid #d1d5db; border-radius: 4px; padding: 3px 8px; }}"
            f"QPushButton:hover {{ background: rgba(0,0,0,0.05); }}"
        )

    def _build_plot(self) -> pg.PlotWidget:
        """One Y axis per signal, all sharing the X axis.

        The first signal (HF) uses the plot's built-in left axis and its
        primary ViewBox. Every other signal gets a new right-side axis
        stacked outward, each with its own ViewBox that X-links to the
        primary. Toggling a signal off hides both its curve and its axis;
        toggling on brings both back.
        """
        self._plot = pg.PlotWidget()
        self._plot.setBackground("w")
        self._plot.showGrid(x=True, y=True, alpha=0.3)

        plot_item = self._plot.plotItem
        plot_item.setLabel("bottom", "Time since connect (s)")

        # Hide the built-in left axis entirely. All signals get uniform
        # right-side axes so toggle-off can freely remove any axis without
        # special-casing the primary.
        plot_item.hideAxis("left")

        for i, (name, unit, color) in enumerate(SIGNAL_SPECS):
            s = self._series[name]
            s.axis = pg.AxisItem("right")
            s.axis.setLabel(f"{name} ({unit})", color=color)
            s.axis.setPen(color)
            s.axis.setTextPen(color)
            s.axis_row = 2
            s.axis_col = 2 + i
            plot_item.layout.addItem(s.axis, s.axis_row, s.axis_col)
            s.view_box = pg.ViewBox()
            s.view_box.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
            plot_item.scene().addItem(s.view_box)
            s.axis.linkToView(s.view_box)
            s.view_box.setXLink(plot_item.vb)
            s.curve = pg.PlotDataItem(pen=pg.mkPen(color, width=2))
            s.view_box.addItem(s.curve)

        # Keep the ViewBoxes' geometry synced with the primary plot area
        plot_item.vb.sigResized.connect(self._sync_viewboxes)
        self._sync_viewboxes()

        return self._plot

    def _sync_viewboxes(self) -> None:
        primary = self._plot.plotItem.vb
        rect = primary.sceneBoundingRect()
        for s in self._series.values():
            if s.view_box is not None and s.view_box is not primary:
                s.view_box.setGeometry(rect)
                s.view_box.linkedViewChanged(primary, s.view_box.XAxis)

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

    # ---- Reference clock ---------------------------------------------------

    def set_reference_now(self, source: str) -> None:
        """Reset the X-axis reference to now. `source` in {"connect", "experiment"}."""
        self._t_ref = time.time()
        self._t_ref_source = source
        label = "connect" if source == "connect" else "experiment"
        self._plot.plotItem.setLabel("bottom", f"Time since {label} (s)")
        # Clear buffers so the new reference actually starts at t=0
        for s in self._series.values():
            s.xs.clear()
            s.ys.clear()
            if s.curve is not None:
                s.curve.setData([], [])

    def clear_reference(self) -> None:
        self._t_ref = None
        self._plot.plotItem.setLabel("bottom", "Time (waiting for connect)")

    # ---- Sample intake -----------------------------------------------------

    def push_calorimeter_sample(self, wall_ts: float, hf: float, temp: float) -> None:
        self._append_sample("HF", wall_ts, hf)
        self._append_sample("T", wall_ts, temp)
        self._readout_labels["HF"].setText(f"HF: {hf:.3f} mW")
        self._readout_labels["T"].setText(f"T: {temp:.3f} °C")

    def push_keithley_sample(
        self,
        wall_ts: float,
        v: float | None,
        i: float | None,
        r: float | None,
        p: float | None,
    ) -> None:
        for name, value in [("V", v), ("I", i), ("R", r), ("P", p)]:
            if value is None:
                continue
            self._append_sample(name, wall_ts, float(value))
            self._readout_labels[name].setText(
                f"{name}: {value:.4g} {self._series[name].unit}"
            )

    def _append_sample(self, name: str, wall_ts: float, value: float) -> None:
        if self._t_ref is None:
            # Not started yet — anchor on first sample if nothing else has
            self._t_ref = wall_ts
            self._t_ref_source = "connect"
            self._plot.plotItem.setLabel("bottom", "Time since connect (s)")
        rel_t = wall_ts - self._t_ref
        s = self._series[name]
        s.xs.append(rel_t)
        s.ys.append(value)
        if s.visible and s.curve is not None:
            s.curve.setData(s.xs, s.ys)

    # ---- Legend / axis -----------------------------------------------------

    def _on_legend_toggle(self, name: str, checked: bool) -> None:
        s = self._series[name]
        s.visible = checked
        plot_item = self._plot.plotItem
        if s.curve is not None:
            if checked:
                s.curve.setData(s.xs, s.ys)
            else:
                s.curve.setData([], [])
        if s.axis is not None:
            if checked:
                # Re-add to layout at its reserved column so signals stay
                # in a consistent left-to-right order.
                plot_item.layout.addItem(s.axis, s.axis_row, s.axis_col)
                s.axis.show()
            else:
                # Fully remove from layout so its column collapses and the
                # plot area expands to fill the freed space.
                plot_item.layout.removeItem(s.axis)
                s.axis.hide()
        s.legend_btn.setStyleSheet(self._legend_style(s.color, active=checked))
        # Force the plot to re-flow, then re-sync the viewbox geometries
        plot_item.layout.invalidate()
        self._sync_viewboxes()

    # ---- Actions -----------------------------------------------------------

    def _on_clear(self) -> None:
        for s in self._series.values():
            s.xs.clear()
            s.ys.clear()
            if s.curve is not None:
                s.curve.setData([], [])
            self._readout_labels[s.name].setText(f"{s.name}: —")
        # Keep t_ref so the axis label stays sensible

    def _on_save_csv(self) -> None:
        n = sum(len(s.xs) for s in self._series.values())
        if n == 0:
            QMessageBox.information(self, "Nothing to save", "No samples recorded yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Real-Time log as CSV", "realtime_log.csv", "CSV files (*.csv)"
        )
        if not path:
            return

        # Union of all timestamps across signals, sparse fill per column
        timeline: dict[float, dict[str, float]] = {}
        for s in self._series.values():
            for x, y in zip(s.xs, s.ys):
                timeline.setdefault(x, {})[s.name] = y

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                header = ["time_s"] + [
                    f"{s.name}_{s.unit}" for s in self._series.values()
                ]
                w.writerow(header)
                for t_rel in sorted(timeline.keys()):
                    row = [t_rel]
                    for s in self._series.values():
                        row.append(timeline[t_rel].get(s.name, ""))
                    w.writerow(row)
        except OSError as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return
        QMessageBox.information(
            self, "Saved", f"Wrote {len(timeline)} rows to\n{path}"
        )
