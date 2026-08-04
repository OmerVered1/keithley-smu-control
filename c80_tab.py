"""
C80 Calorimeter tab
====================
Qt widget that lives inside the Keithley 2602B main window as a top-level tab.
Displays live heat flow and sample temperature from a Setaram C80 read over
LAN alongside Calisto. Display-only; a manual Save CSV button writes the
current buffer to disk.
"""

from __future__ import annotations

import csv

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

from c80_reader import C80_PORT, C80Reader, discover_c80_ip


HF_COLOR = "#dc2626"   # red
T_COLOR = "#2563eb"    # blue
MUTED = "#6b7280"
OK_COLOR = "#16a34a"


class C80Tab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._reader: C80Reader | None = None
        self._times: list[float] = []
        self._hf: list[float] = []
        self._temp: list[float] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        outer.addWidget(self._build_connection_bar())
        outer.addLayout(self._build_readout_bar())
        outer.addWidget(self._build_plot(), stretch=1)

    def _build_connection_bar(self) -> QGroupBox:
        box = QGroupBox("C80 Connection")
        row = QHBoxLayout(box)

        row.addWidget(QLabel("Host:"))
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("169.254.x.x (click Discover)")
        self.host_edit.setMinimumWidth(200)
        row.addWidget(self.host_edit)

        self.discover_btn = QPushButton("Discover")
        self.discover_btn.setToolTip(
            "Look up the C80's IP in the OS ARP cache using its fixed MAC.\n"
            f"MAC: 00:50:C2:30:E1:CC.\nRequires Calisto to be running."
        )
        self.discover_btn.clicked.connect(self._on_discover)
        row.addWidget(self.discover_btn)

        row.addSpacing(20)
        row.addWidget(QLabel("Poll (s):"))
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.5, 60.0)
        self.interval_spin.setValue(1.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setDecimals(1)
        row.addWidget(self.interval_spin)

        row.addSpacing(20)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect_toggle)
        row.addWidget(self.connect_btn)

        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet(f"color: {MUTED};")
        row.addWidget(self.status_label)

        row.addStretch()
        return box

    def _build_readout_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.hf_label = QLabel("HF: —  mW")
        self.hf_label.setFont(QFont("Inter", 22, QFont.Bold))
        self.hf_label.setStyleSheet(f"color: {HF_COLOR};")
        row.addWidget(self.hf_label)

        row.addSpacing(30)

        self.temp_label = QLabel("T: —  °C")
        self.temp_label.setFont(QFont("Inter", 22, QFont.Bold))
        self.temp_label.setStyleSheet(f"color: {T_COLOR};")
        row.addWidget(self.temp_label)

        row.addStretch()

        self.samples_label = QLabel("0 samples")
        self.samples_label.setStyleSheet(f"color: {MUTED};")
        row.addWidget(self.samples_label)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._on_clear)
        row.addWidget(self.clear_btn)

        self.save_btn = QPushButton("Save CSV…")
        self.save_btn.clicked.connect(self._on_save_csv)
        row.addWidget(self.save_btn)

        return row

    def _build_plot(self) -> pg.PlotWidget:
        self._plot = pg.PlotWidget()
        self._plot.setBackground("w")
        self._plot.showGrid(x=True, y=True, alpha=0.3)

        plot_item = self._plot.plotItem
        plot_item.setLabel("bottom", "Time (s)")
        plot_item.setLabel("left", "Heat flow (mW)", color=HF_COLOR)
        plot_item.getAxis("left").setPen(HF_COLOR)
        plot_item.getAxis("left").setTextPen(HF_COLOR)

        # Second Y axis for temperature — separate ViewBox linked to the same X
        self._t_vb = pg.ViewBox()
        plot_item.showAxis("right")
        plot_item.scene().addItem(self._t_vb)
        plot_item.getAxis("right").linkToView(self._t_vb)
        plot_item.getAxis("right").setLabel("Sample T (°C)", color=T_COLOR)
        plot_item.getAxis("right").setPen(T_COLOR)
        plot_item.getAxis("right").setTextPen(T_COLOR)
        self._t_vb.setXLink(plot_item)

        self._hf_curve = pg.PlotDataItem(pen=pg.mkPen(HF_COLOR, width=2))
        plot_item.addItem(self._hf_curve)

        self._t_curve = pg.PlotDataItem(pen=pg.mkPen(T_COLOR, width=2))
        self._t_vb.addItem(self._t_curve)

        plot_item.vb.sigResized.connect(self._sync_second_axis)
        self._sync_second_axis()

        return self._plot

    def _sync_second_axis(self) -> None:
        # Keep the temperature ViewBox aligned with the HF plot area on resize
        self._t_vb.setGeometry(self._plot.plotItem.vb.sceneBoundingRect())

    # -- discovery / connect / disconnect ------------------------------------

    def _on_discover(self) -> None:
        ip = discover_c80_ip()
        if ip:
            self.host_edit.setText(ip)
            self._set_status(f"Found C80 at {ip}", OK_COLOR)
        else:
            self._set_status(
                "C80 not found in ARP cache — is Calisto running?", HF_COLOR
            )

    def _on_connect_toggle(self) -> None:
        if self._reader is not None and self._reader.isRunning():
            self._stop_reader()
            return

        host = self.host_edit.text().strip()
        if not host:
            self._on_discover()
            host = self.host_edit.text().strip()
            if not host:
                return

        self._reader = C80Reader(host, C80_PORT, float(self.interval_spin.value()))
        self._reader.sample.connect(self._on_sample)
        self._reader.error.connect(self._on_error)
        self._reader.start()
        self.connect_btn.setText("Disconnect")
        self._set_status(f"Connecting to {host}…", MUTED)

    def _stop_reader(self) -> None:
        if self._reader is not None:
            self._reader.stop()
            self._reader.wait(2000)
            self._reader = None
        self.connect_btn.setText("Connect")
        self._set_status("Disconnected", MUTED)

    def _on_sample(self, t: float, hf: float, temp: float) -> None:
        # First sample = successful connect
        if not self._times:
            self._set_status(f"Connected to {self.host_edit.text().strip()}", OK_COLOR)
        self._times.append(t)
        self._hf.append(hf)
        self._temp.append(temp)
        self.hf_label.setText(f"HF: {hf:8.3f}  mW")
        self.temp_label.setText(f"T: {temp:7.3f}  °C")
        self.samples_label.setText(f"{len(self._times)} samples")
        self._hf_curve.setData(self._times, self._hf)
        self._t_curve.setData(self._times, self._temp)

    def _on_error(self, msg: str) -> None:
        self._set_status(f"Error: {msg}", HF_COLOR)
        self._stop_reader()

    # -- buffer controls -----------------------------------------------------

    def _on_clear(self) -> None:
        self._times.clear()
        self._hf.clear()
        self._temp.clear()
        self._hf_curve.clear()
        self._t_curve.clear()
        self.hf_label.setText("HF: —  mW")
        self.temp_label.setText("T: —  °C")
        self.samples_label.setText("0 samples")

    def _on_save_csv(self) -> None:
        if not self._times:
            QMessageBox.information(self, "Nothing to save", "No samples recorded yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save C80 log as CSV", "c80_log.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["time_s", "HF_mW", "T_C"])
                for row in zip(self._times, self._hf, self._temp):
                    w.writerow(row)
        except OSError as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return
        QMessageBox.information(
            self, "Saved", f"Wrote {len(self._times)} samples to\n{path}"
        )

    # -- helpers -------------------------------------------------------------

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    def closeEvent(self, event):
        self._stop_reader()
        super().closeEvent(event)
