"""Runs the monitor engine off the GUI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from unblock_tracker import config
from unblock_tracker.monitor import Event, MonitorEngine


class MonitorWorker(QThread):
    """Thin Qt wrapper: the engine's callbacks become signals."""

    log_line = Signal(str)
    status_changed = Signal(str, str)
    event_recorded = Signal(object)
    run_finished = Signal(str)

    def __init__(self, settings: config.Settings, password: str, parent=None):
        super().__init__(parent)
        self.engine = MonitorEngine(
            settings,
            password,
            on_log=self.log_line.emit,
            on_status=lambda status, detail: self.status_changed.emit(status, detail),
            on_event=self._emit_event,
        )

    def _emit_event(self, event: Event) -> None:
        self.event_recorded.emit(event)

    def run(self) -> None:
        self.run_finished.emit(self.engine.run())

    def stop(self) -> None:
        self.engine.stop()
