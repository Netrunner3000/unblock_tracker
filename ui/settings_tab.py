"""Settings tab — the only place account names, handles and tokens come from.

Nothing here ships with a value. A fresh install opens with empty fields and
the monitor refuses to start until they are filled in.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from unblock_tracker import checker, config, notifiers, secrets

from . import theme

FIELD_MIN = 240


class SecretField(QWidget):
    """A masked line edit with a reveal toggle, backed by the Keychain."""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setMinimumWidth(FIELD_MIN)

        self.toggle = QPushButton("Show")
        self.toggle.setCheckable(True)
        self.toggle.setFixedWidth(66)
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

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 - matches Qt naming
        self.edit.setEnabled(enabled)
        self.toggle.setEnabled(enabled)


def _row(*widgets, stretch_last: bool = False) -> QWidget:
    """Lay widgets out side by side inside one form field."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for widget in widgets:
        layout.addWidget(widget)
    if not stretch_last:
        layout.addStretch(1)
    return container


def _existing_dir(raw: str, fallback: Path) -> str:
    """Resolve a field's value to a directory the file dialog can actually open.

    A relative value like "runs" means nothing to QFileDialog, which then opens
    the filesystem root. Walk up to the nearest directory that exists.
    """
    path = Path(raw).expanduser() if raw.strip() else fallback
    if not path.is_absolute():
        path = fallback
    while not path.exists() and path != path.parent:
        path = path.parent
    return str(path)


def _browse_row(
    edit: QLineEdit,
    caption: str,
    directory: bool = False,
    start: Callable[[], Path] | None = None,
) -> QWidget:
    """A line edit plus a Browse… button.

    `start` supplies the folder to open when the field is blank or relative.
    """
    edit.setMinimumWidth(FIELD_MIN)
    button = QPushButton("Browse…")
    button.setFixedWidth(96)

    def pick() -> None:
        fallback = start() if start else Path.home()
        opening = _existing_dir(edit.text(), fallback)
        if directory:
            chosen = QFileDialog.getExistingDirectory(edit, caption, opening)
        else:
            chosen, _ = QFileDialog.getOpenFileName(edit, caption, opening)
        if chosen:
            edit.setText(chosen)

    button.clicked.connect(pick)
    return _row(edit, button, stretch_last=True)


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
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        page, column = theme.column()
        column.setContentsMargins(24, 20, 24, 24)

        for title, builder in (
            ("Your Instagram account", self._account_card),
            ("Profile to watch", self._target_card),
            ("Notifications", self._notify_card),
            ("Schedule", self._schedule_card),
            ("Browser", self._browser_card),
            ("Proxies", self._proxy_card),
            ("Output", self._output_card),
        ):
            column.addWidget(theme.section_title(title))
            column.addWidget(builder())
        column.addStretch(1)

        scroll.setWidget(page)
        outer.addWidget(scroll, 1)
        outer.addWidget(self._footer())

    def _footer(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 10, 24, 14)

        self.keychain_label = QLabel(
            f"Secrets are stored in the macOS Keychain ({secrets.backend_name()})"
        )
        self.keychain_label.setObjectName("hint")

        self.save_button = QPushButton("Save settings")
        self.save_button.setObjectName("primary")
        self.save_button.setMinimumWidth(140)
        self.save_button.clicked.connect(self.save)

        layout.addWidget(self.keychain_label)
        layout.addStretch(1)
        layout.addWidget(self.save_button)
        return bar

    # -- cards ----------------------------------------------------------
    def _account_card(self) -> QWidget:
        frame, layout = theme.card()
        form = theme.form()

        self.check_mode = QComboBox()
        self.check_mode.addItem("Logged in — accurate, needs credentials", config.CHECK_MODE_LOGIN)
        self.check_mode.addItem("Anonymous — public page only", config.CHECK_MODE_ANONYMOUS)
        self.check_mode.currentIndexChanged.connect(self._sync_mode)

        self.instagram_username = QLineEdit()
        self.instagram_username.setPlaceholderText("your own Instagram handle")
        self.instagram_username.setMinimumWidth(FIELD_MIN)
        self.instagram_password = SecretField("stored in your login Keychain")

        form.addRow(theme.label("Check mode"), self.check_mode)
        form.addRow(theme.label("Username"), self.instagram_username)
        form.addRow(theme.label("Password"), self.instagram_password)
        layout.addLayout(form)

        self.mode_hint = theme.hint(
            "Anonymous mode needs no credentials, but only sees what a logged-out "
            "visitor sees and cannot take screenshots."
        )
        layout.addWidget(self.mode_hint)
        return frame

    def _target_card(self) -> QWidget:
        frame, layout = theme.card()
        form = theme.form()
        self.target_profile = QLineEdit()
        self.target_profile.setPlaceholderText("handle without the @")
        self.target_profile.setMinimumWidth(FIELD_MIN)
        form.addRow(theme.label("Target profile"), self.target_profile)

        self.watchlist = QPlainTextEdit()
        self.watchlist.setPlaceholderText("optional — one extra handle per line")
        self.watchlist.setFixedHeight(80)
        form.addRow(theme.label("Also watch"), self.watchlist)
        layout.addLayout(form)

        self.watchlist_hint = theme.hint(
            "Each cycle checks every handle in turn, so more profiles means a longer "
            "cycle. With more than one, a run keeps going past the first profile that "
            "becomes visible rather than stopping."
        )
        layout.addWidget(self.watchlist_hint)
        return frame

    def _notify_card(self) -> QWidget:
        frame, layout = theme.card()

        form = theme.form()
        self.notifier = QComboBox()
        self.notifier.addItem("Off", config.NOTIFIER_NONE)
        self.notifier.addItem("Telegram", config.NOTIFIER_TELEGRAM)
        self.notifier.addItem("Pushbullet", config.NOTIFIER_PUSHBULLET)
        self.notifier.currentIndexChanged.connect(self._sync_notifier)
        form.addRow(theme.label("Send alerts via"), self.notifier)
        layout.addLayout(form)

        # Shown/hidden rather than stacked, so the card collapses when off.
        self.telegram_box = QWidget()
        telegram_form = theme.form()
        self.telegram_box.setLayout(telegram_form)
        self.telegram_token = SecretField("token from @BotFather")
        self.telegram_chat_id = QLineEdit()
        self.telegram_chat_id.setPlaceholderText("numeric chat ID")
        self.telegram_chat_id.setMinimumWidth(FIELD_MIN)
        telegram_form.addRow(theme.label("Bot token"), self.telegram_token)
        telegram_form.addRow(theme.label("Chat ID"), self.telegram_chat_id)
        layout.addWidget(self.telegram_box)

        self.pushbullet_box = QWidget()
        pushbullet_form = theme.form()
        self.pushbullet_box.setLayout(pushbullet_form)
        self.pushbullet_token = SecretField("token from pushbullet.com/account")
        pushbullet_form.addRow(theme.label("Access token"), self.pushbullet_token)
        layout.addWidget(self.pushbullet_box)

        self.notify_members = QCheckBox("Followers arriving or leaving, by name")
        self.notify_flags = QCheckBox("Private, restricted and close-friends changes")
        self.notify_counts = QCheckBox("Follower, following and post counts")
        for box in (self.notify_members, self.notify_flags, self.notify_counts):
            layout.addWidget(box)

        self.notify_hint = theme.hint(
            "Visibility changes always alert — that is the point of the app. Counts "
            "are off by default because an active account moves them constantly and "
            "would bury the alerts that matter. Everything is recorded either way."
        )
        layout.addWidget(self.notify_hint)

        self.test_button = QPushButton("Send test notification")
        self.test_button.clicked.connect(self._send_test)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.test_button)
        layout.addLayout(row)
        return frame

    def _schedule_card(self) -> QWidget:
        frame, layout = theme.card()
        form = theme.form()

        self.interval_min = QSpinBox()
        self.interval_min.setRange(1, 3600)
        self.interval_min.setSuffix(" s")
        self.interval_max = QSpinBox()
        self.interval_max.setRange(1, 3600)
        self.interval_max.setSuffix(" s")

        self.max_runtime = QSpinBox()
        self.max_runtime.setRange(0, 10080)
        self.max_runtime.setSuffix(" min")
        self.max_runtime.setSpecialValueText("no limit")

        self.night_start = QSpinBox()
        self.night_start.setRange(0, 23)
        self.night_start.setSuffix(":00")
        self.night_end = QSpinBox()
        self.night_end.setRange(0, 23)
        self.night_end.setSuffix(":00")
        self.quiet_row = _row(self.night_start, QLabel("to"), self.night_end)

        self.stop_on_unblock = QCheckBox("Stop the run once the profile becomes visible")
        self.night_break = QCheckBox("Pause overnight")
        self.night_break.toggled.connect(self.quiet_row.setEnabled)

        form.addRow(
            theme.label("Wait between checks"),
            _row(self.interval_min, QLabel("to"), self.interval_max),
        )
        form.addRow(theme.label("Maximum run time"), _row(self.max_runtime))
        form.addRow(theme.label(""), self.stop_on_unblock)
        form.addRow(theme.label(""), self.night_break)
        form.addRow(theme.label("Quiet hours"), self.quiet_row)

        self.backoff = QSpinBox()
        self.backoff.setRange(0, 3600)
        self.backoff.setSuffix(" s")
        self.backoff.setSpecialValueText("no backoff")
        form.addRow(theme.label("Wait after a failure"), _row(self.backoff))

        self.page_timeout = QSpinBox()
        self.page_timeout.setRange(5, 120)
        self.page_timeout.setSuffix(" s")
        form.addRow(theme.label("Page load timeout"), _row(self.page_timeout))
        layout.addLayout(form)

        self.schedule_hint = theme.hint(
            "After a failed check the wait doubles while failures continue. Failures "
            "usually mean rate limiting or a dead session, and asking harder makes "
            "both worse."
        )
        layout.addWidget(self.schedule_hint)
        return frame

    def _browser_card(self) -> QWidget:
        frame, layout = theme.card()
        form = theme.form()

        self.headless = QCheckBox("Run the browser hidden")
        self.persist_session = QCheckBox("Stay signed in between runs")
        self.rotate_user_agent = QCheckBox("Rotate the user agent between sessions")
        self.verify_login = QCheckBox("Confirm the session is logged in before checking")

        self.forget_button = QPushButton("Forget saved session")
        self.forget_button.setToolTip(
            "Delete the stored login cookies so the next run signs in fresh."
        )
        self.forget_button.clicked.connect(self._forget_session)

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

        form.addRow(theme.label(""), self.headless)
        form.addRow(theme.label(""), self.persist_session)
        form.addRow(theme.label(""), self.rotate_user_agent)
        form.addRow(theme.label(""), self.verify_login)
        form.addRow(theme.label("Saved session"), _row(self.forget_button))
        form.addRow(theme.label("Login attempts"), _row(self.login_attempts))
        form.addRow(theme.label("Restart browser after"), _row(self.restart_after))
        form.addRow(
            theme.label("Browser binary"),
            _browse_row(
                self.browser_binary,
                "Select a browser binary",
                start=lambda: Path("/Applications"),
            ),
        )
        form.addRow(
            theme.label("chromedriver"),
            _browse_row(
                self.chromedriver_path,
                "Select chromedriver",
                start=lambda: Path("/opt/homebrew/bin"),
            ),
        )
        layout.addLayout(form)

        self.browser_hint = theme.hint(
            "These settings apply to logged-in mode only. Staying signed in reuses "
            "Instagram's cookies instead of signing in again on every run and every "
            "browser restart — repeated sign-ins are the likeliest thing to get an "
            "account challenged. Cookies are stored outside this folder, in "
            "Application Support."
        )
        layout.addWidget(self.browser_hint)
        return frame

    def _proxy_card(self) -> QWidget:
        frame, layout = theme.card()
        form = theme.form()
        self.use_proxy = QCheckBox("Route the browser through a fetched proxy pool")
        self.proxy_source = QLineEdit()
        self.proxy_source.setPlaceholderText("URL returning one proxy per line")
        self.proxy_source.setMinimumWidth(FIELD_MIN)
        self.use_proxy.toggled.connect(self.proxy_source.setEnabled)
        form.addRow(theme.label(""), self.use_proxy)
        form.addRow(theme.label("Proxy list URL"), self.proxy_source)
        layout.addLayout(form)

        self.proxy_hint = theme.hint(
            "Makes requests arrive from another IP, which avoids per-IP rate limits. "
            "In logged-in mode this usually backfires: Instagram treats sign-ins from "
            "unfamiliar rotating addresses as a far stronger signal than request rate, "
            "so you invite a challenge. It fits anonymous mode, where there is no "
            "session to make suspicious. See the guide for the full picture."
        )
        layout.addWidget(self.proxy_hint)
        return frame

    def _output_card(self) -> QWidget:
        frame, layout = theme.card()
        form = theme.form()
        self.save_screenshots = QCheckBox("Capture a screenshot on every status change")
        self.data_dir = QLineEdit()
        form.addRow(theme.label(""), self.save_screenshots)
        form.addRow(
            theme.label("Run data folder"),
            _browse_row(
                self.data_dir,
                "Select a folder for logs and screenshots",
                directory=True,
                start=self._current_data_dir,
            ),
        )
        layout.addLayout(form)
        return frame

    # -- state sync -----------------------------------------------------
    def _current_data_dir(self) -> Path:
        """Where Browse… should open for the run folder.

        Created if absent, so the dialog lands inside it rather than on its
        parent the first time it is used.
        """
        target = self.collect().resolved_data_dir()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            return config.DATA_ROOT
        return target

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
        self.watchlist.setPlainText("\n".join(settings.watchlist))

        self.notifier.setCurrentIndex(max(0, self.notifier.findData(settings.notifier)))
        self.notify_members.setChecked("members" in settings.notify_kinds)
        self.notify_flags.setChecked("flag" in settings.notify_kinds)
        self.notify_counts.setChecked("count" in settings.notify_kinds)
        self.telegram_token.setText(secrets.get(secrets.TELEGRAM_BOT_TOKEN, account))
        self.telegram_chat_id.setText(settings.telegram_chat_id)
        self.pushbullet_token.setText(secrets.get(secrets.PUSHBULLET_TOKEN, account))

        self.interval_min.setValue(settings.interval_min_seconds)
        self.interval_max.setValue(settings.interval_max_seconds)
        self.max_runtime.setValue(settings.max_runtime_minutes)
        self.stop_on_unblock.setChecked(settings.stop_on_unblock)
        self.night_break.setChecked(settings.night_break_enabled)
        self.quiet_row.setEnabled(settings.night_break_enabled)
        self.backoff.setValue(settings.backoff_seconds)
        self.page_timeout.setValue(settings.page_timeout_seconds)
        self.night_start.setValue(settings.night_break_start_hour)
        self.night_end.setValue(settings.night_break_end_hour)

        self.headless.setChecked(settings.headless)
        self.persist_session.setChecked(settings.persist_session)
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
            watchlist=[
                line.strip().lstrip("@")
                for line in self.watchlist.toPlainText().splitlines()
                if line.strip()
            ],
            telegram_chat_id=self.telegram_chat_id.text().strip(),
            check_mode=self.check_mode.currentData(),
            notifier=self.notifier.currentData(),
            notify_kinds=[
                kind
                for kind, box in (
                    ("members", self.notify_members),
                    ("flag", self.notify_flags),
                    ("count", self.notify_counts),
                )
                if box.isChecked()
            ],
            interval_min_seconds=self.interval_min.value(),
            interval_max_seconds=self.interval_max.value(),
            max_runtime_minutes=self.max_runtime.value(),
            stop_on_unblock=self.stop_on_unblock.isChecked(),
            night_break_enabled=self.night_break.isChecked(),
            backoff_seconds=self.backoff.value(),
            page_timeout_seconds=self.page_timeout.value(),
            night_break_start_hour=self.night_start.value(),
            night_break_end_hour=self.night_end.value(),
            headless=self.headless.isChecked(),
            persist_session=self.persist_session.isChecked(),
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
    def _forget_session(self) -> None:
        settings = self.collect()
        if not checker.has_saved_session(settings):
            QMessageBox.information(
                self,
                "Saved session",
                f"No saved session for @{settings.instagram_username or '(no account)'}.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Forget saved session",
            f"Delete the stored login for @{settings.instagram_username}?\n\n"
            "The next run will sign in again from scratch.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        if checker.forget_session(settings):
            QMessageBox.information(self, "Saved session", "Session forgotten.")
        else:
            QMessageBox.warning(
                self, "Saved session", "Could not remove the saved session."
            )

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
