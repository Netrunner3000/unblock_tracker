"""The monitor loop — one engine covering every mode the old scripts had.

Deliberately free of Qt: the loop talks to the outside world through plain
callbacks, so it can be driven by the GUI, a test, or anything else.
"""

from __future__ import annotations

import csv
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import checker, config, notifiers


@dataclass
class Event:
    """A status change worth recording."""

    timestamp: datetime
    status: str
    detail: str
    screenshot: str = ""

    @property
    def stamp(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")


class EventStore:
    """Appends events to a CSV and a plain-text log inside the run directory."""

    HEADER = ["Timestamp", "Status", "Detail", "Screenshot"]

    def __init__(self, settings: config.Settings):
        self.csv_path = settings.csv_path
        self.log_path = settings.log_path
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: Event) -> None:
        new_file = not self.csv_path.exists()
        with self.csv_path.open("a", newline="") as handle:
            writer = csv.writer(handle)
            if new_file:
                writer.writerow(self.HEADER)
            writer.writerow(
                [event.stamp, checker.label(event.status), event.detail, event.screenshot]
            )

    def append_log(self, line: str) -> None:
        with self.log_path.open("a") as handle:
            handle.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {line}\n")

    def read_events(self) -> list[dict[str, str]]:
        if not self.csv_path.exists():
            return []
        with self.csv_path.open(newline="") as handle:
            return list(csv.DictReader(handle))


class MonitorEngine:
    """Runs checks on an interval until told to stop, or until the run ends."""

    def __init__(
        self,
        settings: config.Settings,
        password: str,
        on_log: Callable[[str], None] | None = None,
        on_status: Callable[[str, str], None] | None = None,
        on_event: Callable[[Event], None] | None = None,
    ):
        self.settings = settings
        self.password = password
        self.on_log = on_log or (lambda _msg: None)
        self.on_status = on_status or (lambda _status, _detail: None)
        self.on_event = on_event or (lambda _event: None)

        self.store = EventStore(settings)
        self._stop = threading.Event()

    # ------------------------------------------------------------------
    def log(self, message: str) -> None:
        self.store.append_log(message)
        self.on_log(message)

    def stop(self) -> None:
        self._stop.set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def _sleep(self, seconds: float) -> bool:
        """Interruptible sleep. Returns False if a stop was requested."""
        return not self._stop.wait(seconds)

    def _in_night_break(self, now: datetime) -> bool:
        if not self.settings.night_break_enabled:
            return False
        start = self.settings.night_break_start_hour
        end = self.settings.night_break_end_hour
        if start == end:
            return False
        if start < end:
            return start <= now.hour < end
        return now.hour >= start or now.hour < end  # window wraps past midnight

    # ------------------------------------------------------------------
    def run(self) -> str:
        """Run until stopped or finished. Returns a human-readable reason."""
        settings = self.settings
        probe = checker.build(settings, self.password, self.log)
        notifier = notifiers.build(settings)

        self.log(f"Monitoring @{settings.target_profile} — {notifier.describe()}.")

        try:
            probe.start()
        except checker.LoginFailed as exc:
            self.log(str(exc))
            return str(exc)

        started = datetime.now()
        deadline = (
            started.timestamp() + settings.max_runtime_minutes * 60
            if settings.max_runtime_minutes
            else None
        )
        last_status = checker.UNKNOWN
        last_fingerprint = ""
        checks = 0
        reason = "Stopped."

        try:
            while not self.stopping:
                now = datetime.now()

                if self._in_night_break(now):
                    self.log(
                        f"Night break until {settings.night_break_end_hour:02d}:00 — pausing."
                    )
                    while not self.stopping and self._in_night_break(datetime.now()):
                        if not self._sleep(60):
                            break
                    continue

                try:
                    result = probe.check()
                except Exception as exc:  # noqa: BLE001 - browser errors are varied
                    self.log(f"Check failed: {exc}. Restarting the browser…")
                    try:
                        probe.restart()
                    except checker.LoginFailed as restart_exc:
                        reason = str(restart_exc)
                        self.log(reason)
                        break
                    continue

                checks += 1
                self.on_status(result.status, result.detail)
                self.log(f"{checker.label(result.status)} — {result.detail}")

                if result.status != last_status and last_status != checker.UNKNOWN:
                    self._record(probe, notifier, result, now, changed=True)
                elif result.fingerprint and last_fingerprint and (
                    result.fingerprint != last_fingerprint
                ):
                    self.log("Profile image changed.")
                    self._record(probe, notifier, result, now, changed=False)

                if checker.is_visible(result.status) and settings.stop_on_unblock:
                    if last_status in (checker.BLOCKED, checker.UNKNOWN):
                        reason = f"@{settings.target_profile} is visible — stopping."
                        self.log(reason)
                        break

                last_status = result.status
                if result.fingerprint:
                    last_fingerprint = result.fingerprint

                if deadline and datetime.now().timestamp() >= deadline:
                    reason = "Maximum run time reached."
                    self.log(reason)
                    break

                if settings.restart_after_checks and checks % settings.restart_after_checks == 0:
                    try:
                        probe.restart()
                    except checker.LoginFailed as exc:
                        reason = str(exc)
                        self.log(reason)
                        break

                wait = random.randint(
                    settings.interval_min_seconds, settings.interval_max_seconds
                )
                if not self._sleep(wait):
                    break
        finally:
            probe.stop()

        if self.stopping:
            reason = "Stopped."
        self.log(reason)
        return reason

    # ------------------------------------------------------------------
    def _record(
        self,
        probe,
        notifier: notifiers.Notifier,
        result: checker.CheckResult,
        now: datetime,
        changed: bool,
    ) -> None:
        """Persist an event, capture a screenshot, and notify."""
        settings = self.settings
        shot = ""

        if settings.save_screenshots and probe.supports_screenshots:
            filename = f"{now:%Y%m%d_%H%M%S}_{result.status}.png"
            if probe.screenshot(settings.screenshot_dir / filename):
                shot = filename

        event = Event(now, result.status, result.detail, shot)
        self.store.record(event)
        self.on_event(event)

        if changed and checker.is_visible(result.status):
            message = (
                f"@{settings.target_profile} is visible again "
                f"({checker.label(result.status)}) at {event.stamp}."
            )
        elif changed:
            message = (
                f"@{settings.target_profile} changed to "
                f"{checker.label(result.status)} at {event.stamp}."
            )
        else:
            message = f"@{settings.target_profile} changed its profile image at {event.stamp}."

        try:
            if shot:
                notifier.send_photo(settings.screenshot_dir / shot, message)
            else:
                notifier.send(message)
        except Exception as exc:  # noqa: BLE001 - never let a notifier kill the run
            self.log(f"Notification failed: {exc}")
