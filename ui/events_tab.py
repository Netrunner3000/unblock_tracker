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

from . import theme
from .monitor_tab import Placeholder

COLUMNS = ("Timestamp", "Target", "Status", "Detail", "Screenshot")
HEADINGS = ("When", "Target", "Status", "Detail", "Shot")
SHOT_COLUMN = 4


class EventsTab(QWidget):
    def __init__(self, settings: config.Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(14)

        self.table = QTableWidget(0, len(HEADINGS))
        self.table.setHorizontalHeaderLabels(list(HEADINGS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setWordWrap(False)
        self.table.itemSelectionChanged.connect(self._show_screenshot)

        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        splitter.addWidget(self.table)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)
        preview_layout.addWidget(theme.section_title("Screenshot"))
        preview_card, preview_card_layout = theme.card()
        self.preview = Placeholder("Select an event to see its screenshot.")
        self.preview.setMinimumWidth(260)
        preview_card_layout.addWidget(self.preview, 1)
        preview_layout.addWidget(preview_card, 1)
        splitter.addWidget(preview_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        reveal = QPushButton("Open run folder")
        reveal.clicked.connect(self._open_folder)
        self.summary = QLabel("")
        self.summary.setObjectName("hint")
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
            for column, key in enumerate(COLUMNS):
                value = row.get(key, "")
                if column == SHOT_COLUMN:
                    # The raw filename is long enough to squeeze every other
                    # column out of the viewport, and it isn't readable data.
                    # Keep it on the item and show a marker.
                    item = QTableWidgetItem("●" if value else "")
                    item.setData(Qt.ItemDataRole.UserRole, value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if value:
                        item.setToolTip(value)
                else:
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)  # recover text the column elides
                self.table.setItem(index, column, item)

        modes = QHeaderView.ResizeMode
        header = self.table.horizontalHeader()
        for column in (0, 1, 2):
            header.setSectionResizeMode(column, modes.ResizeToContents)
        header.setSectionResizeMode(3, modes.Stretch)
        header.setSectionResizeMode(SHOT_COLUMN, modes.Fixed)
        self.table.setColumnWidth(SHOT_COLUMN, 48)

        self.summary.setText(
            f"{len(rows)} recorded event{'s' if len(rows) != 1 else ''}"
        )

    def _show_screenshot(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        name_item = self.table.item(items[0].row(), SHOT_COLUMN)
        name = name_item.data(Qt.ItemDataRole.UserRole) if name_item else ""
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
