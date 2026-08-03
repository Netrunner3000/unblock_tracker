"""Monitor tab — start/stop the run and watch it happen."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from unblock_tracker import checker

from . import theme


def status_colour(status: str, palette: theme.Palette) -> str:
    return {
        checker.VISIBLE_PUBLIC: palette.ok,
        checker.VISIBLE_PRIVATE: palette.ok,
        checker.BLOCKED: palette.bad,
        checker.ERROR: palette.warn,
        checker.UNKNOWN: palette.muted,
    }.get(status, palette.text)


class MonitorTab(QWidget):
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.palette_colours = theme.active()
        self._checks = 0
        self._started: datetime | None = None
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        page, column = theme.column(spacing=16)
        column.setContentsMargins(24, 20, 24, 24)

        # --- status card ---
        card, card_layout = theme.card()
        self.target_label = QLabel("No target configured")
        self.target_label.setObjectName("statusTarget")

        self.status_label = QLabel(checker.label(checker.UNKNOWN))
        self.status_label.setObjectName("statusValue")

        self.detail_label = QLabel("Not running.")
        self.detail_label.setObjectName("statusDetail")
        self.detail_label.setWordWrap(True)

        card_layout.setSpacing(6)
        card_layout.addWidget(self.target_label)
        card_layout.addWidget(self.status_label)
        card_layout.addWidget(self.detail_label)
        column.addWidget(card)

        # --- controls ---
        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.start_button = QPushButton("Start monitoring")
        self.start_button.setObjectName("primary")
        self.start_button.setMinimumWidth(150)
        self.start_button.clicked.connect(self.start_requested.emit)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.setMinimumWidth(90)
        self.stop_button.clicked.connect(self.stop_requested.emit)

        self.counter_label = QLabel("")
        self.counter_label.setObjectName("hint")

        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        controls.addWidget(self.counter_label)
        column.addLayout(controls)

        # --- activity log ---
        column.addWidget(theme.section_title("Activity"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setPlaceholderText("Activity from the current run appears here.")
        column.addWidget(self.log_view, 1)

        clear_row = QHBoxLayout()
        clear_row.addStretch(1)
        clear = QPushButton("Clear log view")
        clear.clicked.connect(self.log_view.clear)
        clear_row.addWidget(clear)
        column.addLayout(clear_row)

        outer.addWidget(page, 1)

    # ------------------------------------------------------------------
    def set_target(self, handle: str) -> None:
        self.target_label.setText(
            f"Watching @{handle}" if handle else "No target configured"
        )

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
            f"color: {status_colour(status, self.palette_colours)};"
        )
        self.detail_label.setText(detail)

        elapsed = ""
        if self._started:
            minutes = int((datetime.now() - self._started).total_seconds() // 60)
            elapsed = f" · {minutes} min elapsed"
        self.counter_label.setText(f"{self._checks} checks{elapsed}")

    def set_idle(self, reason: str) -> None:
        self.detail_label.setText(reason)
        self.status_label.setStyleSheet(f"color: {self.palette_colours.muted};")


class Placeholder(QLabel):
    """Centred muted message used when a panel has nothing to show."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("hint")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
