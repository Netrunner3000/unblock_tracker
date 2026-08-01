"""Events tab — the recorded history, replacing the old Flask dashboard."""

from __future__ import annotations

import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from unblock_tracker import config
from unblock_tracker.monitor import EventStore

from .monitor_tab import Placeholder


class EventsTab(QWidget):
    def __init__(self, settings: config.Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["When", "Status", "Detail", "Screenshot"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.table.itemSelectionChanged.connect(self._show_screenshot)
        splitter.addWidget(self.table)

        self.preview = Placeholder("Select an event to see its screenshot.")
        self.preview.setMinimumWidth(280)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        controls = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        reveal = QPushButton("Open run folder")
        reveal.clicked.connect(self._open_folder)
        self.summary = QLabel("")
        self.summary.setStyleSheet("color: palette(mid);")
        controls.addWidget(refresh)
        controls.addWidget(reveal)
        controls.addStretch(1)
        controls.addWidget(self.summary)
        layout.addLayout(controls)

    # ------------------------------------------------------------------
    def apply_settings(self, settings: config.Settings) -> None:
        self.settings = settings
        self.refresh()

    def refresh(self) -> None:
        rows = EventStore(self.settings).read_events()
        self.table.setRowCount(len(rows))
        for index, row in enumerate(reversed(rows)):
            for column, key in enumerate(("Timestamp", "Status", "Detail", "Screenshot")):
                self.table.setItem(index, column, QTableWidgetItem(row.get(key, "")))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.summary.setText(
            f"{len(rows)} recorded event{'s' if len(rows) != 1 else ''}"
        )

    def _show_screenshot(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        name_item = self.table.item(items[0].row(), 3)
        name = name_item.text() if name_item else ""
        if not name:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("No screenshot for this event.")
            return

        path = self.settings.screenshot_dir / name
        if not path.exists():
            self.preview.setPixmap(QPixmap())
            self.preview.setText(f"Missing file:\n{name}")
            return

        pixmap = QPixmap(str(path))
        self.preview.setText("")
        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _open_folder(self) -> None:
        folder = self.settings.resolved_data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(folder)], check=False)
