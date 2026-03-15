"""
Keithley SMU Control Suite — Unified Launcher
===============================================
In-process launcher that lets users choose which Keithley instrument to control.
Supports: Keithley 2450, Keithley 6430, Keithley 2602B.

Author: Omer Vered
Date: 2026
"""

import sys
import os

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QGridLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPalette, QColor


__version__ = "1.1.3"
__app_name__ = "Keithley SMU Control Suite"
__author__ = "Omer Vered"
__organization__ = "Ben-Gurion University of the Negev (BGU)"


class InstrumentCard(QFrame):
    """A clickable card representing an instrument"""

    def __init__(self, model: str, subtitle: str, specs: str,
                 accent_color: str, parent=None):
        super().__init__(parent)
        self.model = model
        self.accent_color = accent_color

        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedSize(320, 300)
        self.setCursor(Qt.PointingHandCursor)

        self._setup_ui(model, subtitle, specs, accent_color)
        self._set_default_style()

    def _setup_ui(self, model, subtitle, specs, accent_color):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Model label
        model_label = QLabel(model)
        model_label.setFont(QFont("Inter", 28, QFont.Bold))
        model_label.setStyleSheet(f"color: {accent_color}; background: transparent;")
        model_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(model_label)

        # Subtitle
        sub_label = QLabel(subtitle)
        sub_label.setFont(QFont("Inter", 14))
        sub_label.setStyleSheet("color: #9ca3af; background: transparent;")
        sub_label.setAlignment(Qt.AlignCenter)
        sub_label.setWordWrap(True)
        layout.addWidget(sub_label)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {accent_color};")
        line.setFixedHeight(2)
        layout.addWidget(line)

        # Specs
        specs_label = QLabel(specs)
        specs_label.setFont(QFont("Inter", 12))
        specs_label.setStyleSheet("color: #9ca3af; background: transparent;")
        specs_label.setAlignment(Qt.AlignCenter)
        specs_label.setWordWrap(True)
        layout.addWidget(specs_label)

        layout.addStretch()

        # Launch button
        self.launch_btn = QPushButton(f"Launch {model}")
        self.launch_btn.setFont(QFont("Inter", 16, QFont.Bold))
        self.launch_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent_color};
                color: white;
                border: none;
                padding: 14px 20px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                opacity: 0.85;
            }}
        """)
        layout.addWidget(self.launch_btn)

    def _set_default_style(self):
        self.setStyleSheet(f"""
            InstrumentCard {{
                background-color: #1e1e2e;
                border: 2px solid #374151;
                border-radius: 16px;
            }}
            InstrumentCard:hover {{
                border-color: {self.accent_color};
                background-color: #252536;
            }}
        """)

    def enterEvent(self, event):
        self.setStyleSheet(f"""
            InstrumentCard {{
                background-color: #252536;
                border: 2px solid {self.accent_color};
                border-radius: 16px;
            }}
        """)

    def leaveEvent(self, event):
        self._set_default_style()


class LauncherWindow(QMainWindow):
    """Main launcher window with instrument selection"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(__app_name__)
        self.setFixedSize(1100, 520)
        self._instrument_windows = []
        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(30)
        layout.setContentsMargins(40, 30, 40, 30)

        # Title
        title = QLabel(__app_name__)
        title.setFont(QFont("Inter", 32, QFont.Bold))
        title.setStyleSheet("color: #e5e7eb;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Select an instrument to launch its control application")
        subtitle.setFont(QFont("Inter", 14))
        subtitle.setStyleSheet("color: #9ca3af;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        # Cards row
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(30)
        cards_layout.addStretch()

        # K2450 Card
        card_2450 = InstrumentCard(
            model="K2450",
            subtitle="General Purpose SourceMeter",
            specs="\u00b1200V / \u00b11A / 22W\nUSB \u00b7 SCPI\nFront & Rear Terminals",
            accent_color="#2563eb",
        )
        card_2450.launch_btn.clicked.connect(lambda: self._launch_instrument("2450"))
        cards_layout.addWidget(card_2450)

        # K6430 Card
        card_6430 = InstrumentCard(
            model="K6430",
            subtitle="Sub-Femtoamp SourceMeter",
            specs="\u00b1105V / \u00b1105mA / 11W\nRS-232 \u00b7 SCPI\nTriax \u00b7 Guard Mode",
            accent_color="#0d9488",
        )
        card_6430.launch_btn.clicked.connect(lambda: self._launch_instrument("6430"))
        cards_layout.addWidget(card_6430)

        # K2602B Card
        card_2602b = InstrumentCard(
            model="K2602B",
            subtitle="Dual-Channel SourceMeter",
            specs="\u00b140V / \u00b13A DC / 40.4W\nUSB \u00b7 GPIB \u00b7 LAN \u00b7 TSP\nDual Independent Channels",
            accent_color="#16a34a",
        )
        card_2602b.launch_btn.clicked.connect(lambda: self._launch_instrument("2602b"))
        cards_layout.addWidget(card_2602b)

        cards_layout.addStretch()
        layout.addLayout(cards_layout)

        # Footer
        footer = QLabel(f"v{__version__} Created by {__author__} with claude code")
        footer.setFont(QFont("Inter", 11))
        footer.setStyleSheet("color: #6b7280;")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

    def _launch_instrument(self, instrument: str):
        """Launch an instrument control window"""
        try:
            app = QApplication.instance()

            if instrument == "2450":
                from keithley2450_pyqt import Keithley2450App, LightPalette as K2450Palette
                # Import stylesheet from the module
                import keithley2450_pyqt
                palette = K2450Palette()
                app.setPalette(palette)
                # Read stylesheet from main() — we need to get it
                # The 2450 doesn't export its stylesheet as a variable, so re-apply it inline
                window = Keithley2450App()

            elif instrument == "6430":
                from keithley6430_pyqt import Keithley6430App, LightPalette as K6430Palette
                palette = K6430Palette()
                app.setPalette(palette)
                window = Keithley6430App()

            elif instrument == "2602b":
                from keithley2602b_pyqt import Keithley2602BApp, LightPalette as K2602BPalette, GLOBAL_STYLESHEET
                palette = K2602BPalette()
                app.setPalette(palette)
                app.setStyleSheet(GLOBAL_STYLESHEET)
                window = Keithley2602BApp()

            else:
                return

            window.show()
            self._instrument_windows.append(window)

            # Connect close event to restore launcher
            window.destroyed.connect(lambda: self._on_instrument_closed(window))

        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Launch Error",
                f"Failed to launch {instrument} control:\n{e}")

    def _on_instrument_closed(self, window):
        """Handle instrument window closing"""
        if window in self._instrument_windows:
            self._instrument_windows.remove(window)

    def closeEvent(self, event):
        """Close all instrument windows when launcher closes"""
        for window in self._instrument_windows:
            try:
                window.close()
            except:
                pass
        event.accept()


class LauncherPalette(QPalette):
    """Dark theme palette for the launcher"""
    def __init__(self):
        super().__init__()
        self.setColor(QPalette.Window, QColor(17, 17, 27))        # #11111b dark bg
        self.setColor(QPalette.WindowText, QColor(229, 231, 235)) # #e5e7eb
        self.setColor(QPalette.Base, QColor(30, 30, 46))          # #1e1e2e
        self.setColor(QPalette.AlternateBase, QColor(37, 37, 54)) # #252536
        self.setColor(QPalette.Text, QColor(229, 231, 235))
        self.setColor(QPalette.Button, QColor(55, 65, 81))        # #374151
        self.setColor(QPalette.ButtonText, QColor(229, 231, 235))
        self.setColor(QPalette.Highlight, QColor(59, 130, 246))
        self.setColor(QPalette.HighlightedText, QColor(255, 255, 255))


def main():
    app = QApplication(sys.argv)
    app.setPalette(LauncherPalette())
    app.setStyle('Fusion')

    font = QFont("Inter", 13)
    app.setFont(font)

    app.setStyleSheet("""
        QMainWindow {
            background-color: #11111b;
        }
    """)

    launcher = LauncherWindow()
    launcher.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
