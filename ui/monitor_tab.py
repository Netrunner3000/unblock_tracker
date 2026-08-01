"""Monitor tab — start/stop the run and watch it happen."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from unblock_tracker import checker

STATUS_COLOURS = {
    checker.VISIBLE_PUBLIC: "#1f9d55",
    checker.VISIBLE_PRIVATE: "#1f9d55",
    checker.BLOCKED: "#b23c3c",
    checker.ERROR: "#b26b00",
    checker.UNKNOWN: "palette(mid)",
}


class MonitorTab(QWidget):
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checks = 0
        self._started: datetime | None = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        status_box = QGroupBox("Current status")
        status_layout = QVBoxLayout(status_box)

        self.target_label = QLabel("No target configured")
        self.target_label.setStyleSheet("color: palette(mid);")

        self.status_label = QLabel(checker.label(checker.UNKNOWN))
        font = self.status_label.font()
        font.setPointSize(font.pointSize() + 10)
        font.setBold(True)
        self.status_label.setFont(font)

        self.detail_label = QLabel("Not running.")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: palette(mid);")

        status_layout.addWidget(self.target_label)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.detail_label)
        layout.addWidget(status_box)

        controls = QHBoxLayout()
        self.start_button = QPushButton("Start monitoring")
        self.start_button.clicked.connect(self.start_requested.emit)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.counter_label = QLabel("")
        self.counter_label.setStyleSheet("color: palette(mid);")
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        controls.addWidget(self.counter_label)
        layout.addLayout(controls)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setPlaceholderText("Activity from the current run appears here.")
        layout.addWidget(self.log_view, 1)

        clear_row = QHBoxLayout()
        clear_row.addStretch(1)
        clear = QPushButton("Clear log view")
        clear.clicked.connect(self.log_view.clear)
        clear_row.addWidget(clear)
        layout.addLayout(clear_row)

    # ------------------------------------------------------------------
    def set_target(self, handle: str) -> None:
        self.target_label.setText(f"Watching @{handle}" if handle else "No target configured")

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if running:
            self._checks = 0
            self._started = datetime.now()
        else:
            self._started = None

    def append_log(self, line: str) -> None:
        self.log_view.appendPlainText(f"{datetime.now():%H:%M:%S}  {line}")

    def set_status(self, status: str, detail: str) -> None:
        self._checks += 1
        self.status_label.setText(checker.label(status))
        self.status_label.setStyleSheet(
            f"color: {STATUS_COLOURS.get(status, 'palette(text)')};"
        )
        self.detail_label.setText(detail)

        elapsed = ""
        if self._started:
            minutes = int((datetime.now() - self._started).total_seconds() // 60)
            elapsed = f" · {minutes} min elapsed"
        self.counter_label.setText(f"{self._checks} checks{elapsed}")

    def set_idle(self, reason: str) -> None:
        self.detail_label.setText(reason)
        self.status_label.setStyleSheet("color: palette(mid);")


class Placeholder(QLabel):
    """Centred grey message used when a panel has nothing to show."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("color: palette(mid);")
        self.setWordWrap(True)
