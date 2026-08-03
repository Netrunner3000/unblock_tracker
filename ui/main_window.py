"""Main window: Monitor / Events / Settings."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStatusBar, QTabWidget

from unblock_tracker import APP_NAME, asset_path, config, secrets

from . import theme
from .events_tab import EventsTab
from .monitor_tab import MonitorTab
from .settings_tab import SettingsTab
from .worker import MonitorWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = config.load()
        self.worker: MonitorWorker | None = None

        self.setWindowTitle(APP_NAME)
        self.resize(1000, 780)
        self.setMinimumSize(720, 560)

        self.tabs = QTabWidget()
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)
        self.monitor_tab = MonitorTab()
        self.events_tab = EventsTab(self.settings)
        self.settings_tab = SettingsTab(self.settings)

        self.tabs.addTab(self.monitor_tab, "Monitor")
        self.tabs.addTab(self.events_tab, "Events")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.setCentralWidget(self.tabs)

        self.setStatusBar(QStatusBar())

        self.monitor_tab.start_requested.connect(self.start)
        self.monitor_tab.stop_requested.connect(self.stop)
        self.settings_tab.settings_saved.connect(self._on_settings_saved)

        self._apply_settings(self.settings)

        if not self.settings.target_profile:
            self.tabs.setCurrentWidget(self.settings_tab)
            self.statusBar().showMessage(
                "Fill in your account and the profile to watch, then save.", 10000
            )

    # ------------------------------------------------------------------
    def _apply_settings(self, settings: config.Settings) -> None:
        self.settings = settings
        self.monitor_tab.set_target(settings.target_profile)
        self.events_tab.apply_settings(settings)

    def _on_settings_saved(self) -> None:
        self._apply_settings(self.settings_tab.settings)
        self.statusBar().showMessage("Settings saved.", 4000)

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        settings = self.settings_tab.collect()
        password = self.settings_tab.password()
        token = secrets.get(
            secrets.TELEGRAM_BOT_TOKEN
            if settings.notifier == config.NOTIFIER_TELEGRAM
            else secrets.PUSHBULLET_TOKEN,
            settings.instagram_username,
        )

        problems = settings.validate(password=password, token=token)
        if problems:
            QMessageBox.warning(
                self,
                "Not ready to run",
                "Fix these first:\n\n• " + "\n• ".join(problems),
            )
            self.tabs.setCurrentWidget(self.settings_tab)
            return

        # Persist whatever is on the form so a run always matches the UI.
        self.settings_tab.save()
        self._apply_settings(self.settings_tab.settings)

        self.worker = MonitorWorker(self.settings, password, self)
        self.worker.log_line.connect(self.monitor_tab.append_log)
        self.worker.status_changed.connect(self.monitor_tab.set_status)
        self.worker.event_recorded.connect(self._on_event)
        self.worker.run_finished.connect(self._on_finished)

        self.monitor_tab.set_running(True)
        self.tabs.setCurrentWidget(self.monitor_tab)
        self.statusBar().showMessage(f"Monitoring @{self.settings.target_profile}…")
        self.worker.start()

    def stop(self) -> None:
        if self.worker is not None:
            self.monitor_tab.append_log("Stop requested — finishing the current check…")
            self.worker.stop()

    def _on_event(self, _event) -> None:
        self.events_tab.refresh()

    def _on_finished(self, reason: str) -> None:
        self.monitor_tab.set_running(False)
        self.monitor_tab.set_idle(reason)
        self.events_tab.refresh()
        self.statusBar().showMessage(reason, 8000)
        self.worker = None

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.worker is not None and self.worker.isRunning():
            answer = QMessageBox.question(
                self,
                "Monitoring is running",
                "Stop the run and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.stop()
            self.worker.wait(15000)
        event.accept()


def run() -> int:
    """Create the application and show the window."""
    import sys

    from PySide6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    theme.apply(app)

    # A packaged .app takes its Dock icon from the bundle; this covers the
    # case of running from source, where there is no bundle to read.
    icon_file = asset_path("icon.icns")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    window = MainWindow()
    window.show()
    return app.exec()
