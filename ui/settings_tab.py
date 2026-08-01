"""Settings tab — the only place account names, handles and tokens come from.

Nothing here ships with a value. A fresh install opens with empty fields and
the monitor refuses to start until they are filled in.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from unblock_tracker import config, notifiers, secrets


class SecretField(QWidget):
    """A masked line edit with a reveal toggle, backed by the Keychain."""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText(placeholder)

        self.toggle = QPushButton("Show")
        self.toggle.setCheckable(True)
        self.toggle.setFixedWidth(60)
        self.toggle.toggled.connect(self._on_toggle)

        layout.addWidget(self.edit, 1)
        layout.addWidget(self.toggle)

    def _on_toggle(self, shown: bool) -> None:
        self.edit.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        )
        self.toggle.setText("Hide" if shown else "Show")

    def text(self) -> str:
        return self.edit.text()

    def setText(self, value: str) -> None:  # noqa: N802 - matches Qt naming
        self.edit.setText(value)


def _browse_row(edit: QLineEdit, caption: str, directory: bool = False) -> QWidget:
    """A line edit plus a Browse… button."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    button = QPushButton("Browse…")
    button.setFixedWidth(90)

    def pick() -> None:
        if directory:
            chosen = QFileDialog.getExistingDirectory(container, caption, edit.text())
        else:
            chosen, _ = QFileDialog.getOpenFileName(container, caption, edit.text())
        if chosen:
            edit.setText(chosen)

    button.clicked.connect(pick)
    layout.addWidget(edit, 1)
    layout.addWidget(button)
    return container


class SettingsTab(QWidget):
    settings_saved = Signal()

    def __init__(self, settings: config.Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._loaded_account = settings.instagram_username

        self._build()
        self.load(settings)

    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(14)

        layout.addWidget(self._account_group())
        layout.addWidget(self._target_group())
        layout.addWidget(self._notify_group())
        layout.addWidget(self._schedule_group())
        layout.addWidget(self._browser_group())
        layout.addWidget(self._proxy_group())
        layout.addWidget(self._output_group())
        layout.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        footer = QHBoxLayout()
        self.keychain_label = QLabel(f"Secrets: macOS Keychain ({secrets.backend_name()})")
        self.keychain_label.setStyleSheet("color: palette(mid);")
        self.save_button = QPushButton("Save settings")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        footer.addWidget(self.keychain_label)
        footer.addStretch(1)
        footer.addWidget(self.save_button)
        outer.addLayout(footer)

    # -- groups ---------------------------------------------------------
    def _account_group(self) -> QGroupBox:
        group = QGroupBox("Your Instagram account")
        form = QFormLayout(group)

        self.check_mode = QComboBox()
        self.check_mode.addItem("Logged in (Selenium, accurate)", config.CHECK_MODE_LOGIN)
        self.check_mode.addItem(
            "Anonymous (public page only, no credentials)", config.CHECK_MODE_ANONYMOUS
        )
        self.check_mode.currentIndexChanged.connect(self._sync_mode)

        self.instagram_username = QLineEdit()
        self.instagram_username.setPlaceholderText("your own Instagram handle")
        self.instagram_password = SecretField("stored in your login Keychain")

        form.addRow("Check mode", self.check_mode)
        form.addRow("Username", self.instagram_username)
        form.addRow("Password", self.instagram_password)

        note = QLabel(
            "Anonymous mode needs no credentials but only sees what a "
            "logged-out visitor sees, and cannot take screenshots."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        form.addRow(note)
        return group

    def _target_group(self) -> QGroupBox:
        group = QGroupBox("Profile to watch")
        form = QFormLayout(group)
        self.target_profile = QLineEdit()
        self.target_profile.setPlaceholderText("handle without the @")
        form.addRow("Target profile", self.target_profile)
        return group

    def _notify_group(self) -> QGroupBox:
        group = QGroupBox("Notifications")
        layout = QVBoxLayout(group)

        top = QFormLayout()
        self.notifier = QComboBox()
        self.notifier.addItem("Off", config.NOTIFIER_NONE)
        self.notifier.addItem("Telegram", config.NOTIFIER_TELEGRAM)
        self.notifier.addItem("Pushbullet", config.NOTIFIER_PUSHBULLET)
        self.notifier.currentIndexChanged.connect(self._sync_notifier)
        top.addRow("Send alerts via", self.notifier)
        layout.addLayout(top)

        # Show/hide rather than a stacked widget, so the group shrinks to
        # nothing when notifications are off instead of holding empty space.
        self.telegram_box = QWidget()
        telegram_form = QFormLayout(self.telegram_box)
        telegram_form.setContentsMargins(0, 0, 0, 0)
        self.telegram_token = SecretField("token from @BotFather")
        self.telegram_chat_id = QLineEdit()
        self.telegram_chat_id.setPlaceholderText("numeric chat ID")
        telegram_form.addRow("Bot token", self.telegram_token)
        telegram_form.addRow("Chat ID", self.telegram_chat_id)
        layout.addWidget(self.telegram_box)

        self.pushbullet_box = QWidget()
        pushbullet_form = QFormLayout(self.pushbullet_box)
        pushbullet_form.setContentsMargins(0, 0, 0, 0)
        self.pushbullet_token = SecretField("token from pushbullet.com/account")
        pushbullet_form.addRow("Access token", self.pushbullet_token)
        layout.addWidget(self.pushbullet_box)

        self.test_button = QPushButton("Send test notification")
        self.test_button.clicked.connect(self._send_test)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.test_button)
        layout.addLayout(row)
        return group

    def _schedule_group(self) -> QGroupBox:
        group = QGroupBox("Schedule")
        form = QFormLayout(group)

        self.interval_min = QSpinBox()
        self.interval_min.setRange(1, 3600)
        self.interval_min.setSuffix(" s")
        self.interval_max = QSpinBox()
        self.interval_max.setRange(1, 3600)
        self.interval_max.setSuffix(" s")
        interval_row = QWidget()
        interval_layout = QHBoxLayout(interval_row)
        interval_layout.setContentsMargins(0, 0, 0, 0)
        interval_layout.addWidget(self.interval_min)
        interval_layout.addWidget(QLabel("to"))
        interval_layout.addWidget(self.interval_max)
        interval_layout.addStretch(1)

        self.max_runtime = QSpinBox()
        self.max_runtime.setRange(0, 10080)
        self.max_runtime.setSuffix(" min")
        self.max_runtime.setSpecialValueText("no limit")
        runtime_row = QWidget()
        runtime_layout = QHBoxLayout(runtime_row)
        runtime_layout.setContentsMargins(0, 0, 0, 0)
        runtime_layout.addWidget(self.max_runtime)
        runtime_layout.addStretch(1)

        self.stop_on_unblock = QCheckBox("Stop the run once the profile becomes visible")

        self.night_break = QCheckBox("Pause overnight")
        self.night_start = QSpinBox()
        self.night_start.setRange(0, 23)
        self.night_start.setSuffix(":00")
        self.night_end = QSpinBox()
        self.night_end.setRange(0, 23)
        self.night_end.setSuffix(":00")
        night_row = QWidget()
        night_layout = QHBoxLayout(night_row)
        night_layout.setContentsMargins(0, 0, 0, 0)
        night_layout.addWidget(self.night_start)
        night_layout.addWidget(QLabel("to"))
        night_layout.addWidget(self.night_end)
        night_layout.addStretch(1)
        self.night_break.toggled.connect(night_row.setEnabled)

        form.addRow("Wait between checks", interval_row)
        form.addRow("Maximum run time", runtime_row)
        form.addRow("", self.stop_on_unblock)
        form.addRow("", self.night_break)
        form.addRow("Quiet hours", night_row)
        return group

    def _browser_group(self) -> QGroupBox:
        group = QGroupBox("Browser (login mode)")
        form = QFormLayout(group)

        self.headless = QCheckBox("Run the browser hidden")
        self.rotate_user_agent = QCheckBox("Rotate the user agent between sessions")
        self.verify_login = QCheckBox("Confirm the session is logged in before checking")

        self.browser_binary = QLineEdit()
        self.browser_binary.setPlaceholderText("blank = system Chrome")
        self.chromedriver_path = QLineEdit()
        self.chromedriver_path.setPlaceholderText("blank = resolved automatically")

        self.restart_after = QSpinBox()
        self.restart_after.setRange(0, 10000)
        self.restart_after.setSpecialValueText("never")
        self.restart_after.setSuffix(" checks")

        self.login_attempts = QSpinBox()
        self.login_attempts.setRange(1, 10)

        form.addRow("", self.headless)
        form.addRow("", self.rotate_user_agent)
        form.addRow("", self.verify_login)
        form.addRow("Login attempts", self.login_attempts)
        form.addRow("Restart browser after", self.restart_after)
        form.addRow(
            "Browser binary", _browse_row(self.browser_binary, "Select a browser binary")
        )
        form.addRow(
            "chromedriver", _browse_row(self.chromedriver_path, "Select chromedriver")
        )
        return group

    def _proxy_group(self) -> QGroupBox:
        group = QGroupBox("Proxies")
        form = QFormLayout(group)
        self.use_proxy = QCheckBox("Route the browser through a fetched proxy pool")
        self.proxy_source = QLineEdit()
        self.proxy_source.setPlaceholderText("URL returning one proxy per line")
        self.use_proxy.toggled.connect(self.proxy_source.setEnabled)
        form.addRow("", self.use_proxy)
        form.addRow("Proxy list URL", self.proxy_source)
        return group

    def _output_group(self) -> QGroupBox:
        group = QGroupBox("Output")
        form = QFormLayout(group)
        self.save_screenshots = QCheckBox("Capture a screenshot on every status change")
        self.data_dir = QLineEdit()
        form.addRow("", self.save_screenshots)
        form.addRow(
            "Run data folder",
            _browse_row(self.data_dir, "Select a folder for logs and screenshots", True),
        )
        return group

    # -- state sync -----------------------------------------------------
    def _sync_mode(self) -> None:
        login_mode = self.check_mode.currentData() == config.CHECK_MODE_LOGIN
        self.instagram_username.setEnabled(login_mode)
        self.instagram_password.setEnabled(login_mode)

    def _sync_notifier(self) -> None:
        choice = self.notifier.currentData()
        self.telegram_box.setVisible(choice == config.NOTIFIER_TELEGRAM)
        self.pushbullet_box.setVisible(choice == config.NOTIFIER_PUSHBULLET)
        self.test_button.setEnabled(choice != config.NOTIFIER_NONE)

    # -- load / collect / save ------------------------------------------
    def load(self, settings: config.Settings) -> None:
        self.settings = settings
        self._loaded_account = settings.instagram_username
        account = settings.instagram_username

        self.check_mode.setCurrentIndex(
            max(0, self.check_mode.findData(settings.check_mode))
        )
        self.instagram_username.setText(settings.instagram_username)
        self.instagram_password.setText(secrets.get(secrets.INSTAGRAM_PASSWORD, account))

        self.target_profile.setText(settings.target_profile)

        self.notifier.setCurrentIndex(max(0, self.notifier.findData(settings.notifier)))
        self.telegram_token.setText(secrets.get(secrets.TELEGRAM_BOT_TOKEN, account))
        self.telegram_chat_id.setText(settings.telegram_chat_id)
        self.pushbullet_token.setText(secrets.get(secrets.PUSHBULLET_TOKEN, account))

        self.interval_min.setValue(settings.interval_min_seconds)
        self.interval_max.setValue(settings.interval_max_seconds)
        self.max_runtime.setValue(settings.max_runtime_minutes)
        self.stop_on_unblock.setChecked(settings.stop_on_unblock)
        self.night_break.setChecked(settings.night_break_enabled)
        self.night_start.setValue(settings.night_break_start_hour)
        self.night_end.setValue(settings.night_break_end_hour)

        self.headless.setChecked(settings.headless)
        self.rotate_user_agent.setChecked(settings.rotate_user_agent)
        self.verify_login.setChecked(settings.verify_login)
        self.login_attempts.setValue(settings.login_attempts)
        self.restart_after.setValue(settings.restart_after_checks)
        self.browser_binary.setText(settings.browser_binary)
        self.chromedriver_path.setText(settings.chromedriver_path)

        self.use_proxy.setChecked(settings.use_proxy)
        self.proxy_source.setText(settings.proxy_source_url)
        self.proxy_source.setEnabled(settings.use_proxy)

        self.save_screenshots.setChecked(settings.save_screenshots)
        self.data_dir.setText(settings.data_dir)

        self._sync_mode()
        self._sync_notifier()

    def collect(self) -> config.Settings:
        """Build a Settings object from the current form state."""
        return config.Settings(
            instagram_username=self.instagram_username.text().strip().lstrip("@"),
            target_profile=self.target_profile.text().strip().lstrip("@"),
            telegram_chat_id=self.telegram_chat_id.text().strip(),
            check_mode=self.check_mode.currentData(),
            notifier=self.notifier.currentData(),
            interval_min_seconds=self.interval_min.value(),
            interval_max_seconds=self.interval_max.value(),
            max_runtime_minutes=self.max_runtime.value(),
            stop_on_unblock=self.stop_on_unblock.isChecked(),
            night_break_enabled=self.night_break.isChecked(),
            night_break_start_hour=self.night_start.value(),
            night_break_end_hour=self.night_end.value(),
            headless=self.headless.isChecked(),
            browser_binary=self.browser_binary.text().strip(),
            chromedriver_path=self.chromedriver_path.text().strip(),
            rotate_user_agent=self.rotate_user_agent.isChecked(),
            user_agents=list(self.settings.user_agents),
            restart_after_checks=self.restart_after.value(),
            verify_login=self.verify_login.isChecked(),
            login_attempts=self.login_attempts.value(),
            use_proxy=self.use_proxy.isChecked(),
            proxy_source_url=self.proxy_source.text().strip(),
            save_screenshots=self.save_screenshots.isChecked(),
            data_dir=self.data_dir.text().strip() or "runs",
        )

    def password(self) -> str:
        return self.instagram_password.text()

    def save(self) -> bool:
        settings = self.collect()
        account = settings.instagram_username

        secrets.set(secrets.INSTAGRAM_PASSWORD, self.instagram_password.text(), account)
        secrets.set(secrets.TELEGRAM_BOT_TOKEN, self.telegram_token.text(), account)
        secrets.set(secrets.PUSHBULLET_TOKEN, self.pushbullet_token.text(), account)

        # Renaming the account moves its secrets; don't strand the old entries.
        if self._loaded_account and self._loaded_account != account:
            for name in (
                secrets.INSTAGRAM_PASSWORD,
                secrets.TELEGRAM_BOT_TOKEN,
                secrets.PUSHBULLET_TOKEN,
            ):
                secrets.delete(name, self._loaded_account)

        config.save(settings)
        self.settings = settings
        self._loaded_account = account
        self.settings_saved.emit()
        return True

    # -- actions --------------------------------------------------------
    def _send_test(self) -> None:
        settings = self.collect()
        token = (
            self.telegram_token.text()
            if settings.notifier == config.NOTIFIER_TELEGRAM
            else self.pushbullet_token.text()
        )
        problems = [
            p
            for p in settings.validate(password="skip", token=token)
            if "Telegram" in p or "Pushbullet" in p
        ]
        if problems:
            QMessageBox.warning(self, "Test notification", "\n".join(problems))
            return

        if settings.notifier == config.NOTIFIER_TELEGRAM:
            notifier = notifiers.TelegramNotifier(token, settings.telegram_chat_id)
        else:
            notifier = notifiers.PushbulletNotifier(token)

        try:
            notifier.send("Unblock Tracker test notification — this channel works.")
        except Exception as exc:  # noqa: BLE001 - surface any transport failure
            QMessageBox.critical(self, "Test notification", f"Failed to send:\n{exc}")
        else:
            QMessageBox.information(
                self, "Test notification", f"Sent via {notifier.describe()}."
            )
