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

from . import checker, config, notifiers, signals


@dataclass
class Event:
    """Something worth recording: a visibility change, or a tracked signal."""

    timestamp: datetime
    status: str
    detail: str
    screenshot: str = ""
    kind: str = "visibility"  # "visibility" | "count" | "flag" | "members"
    signal: str = ""  # which signal, for non-visibility events
    target: str = ""  # which handle this is about

    @property
    def stamp(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def label(self) -> str:
        """What to show in the Status column."""
        if self.kind == "visibility":
            return checker.label(self.status)
        return signals.label(self.signal) if self.signal else self.kind


class EventStore:
    """Appends events to a CSV and a plain-text log inside the run directory."""

    HEADER = ["Timestamp", "Target", "Status", "Detail", "Screenshot"]

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
                [event.stamp, event.target, event.label, event.detail, event.screenshot]
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
        self.snapshots = signals.SnapshotStore(
            settings.resolved_data_dir() / "snapshots.json"
        )
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

    def _backoff(self, failures: int) -> int:
        """Extra seconds to wait after consecutive failures.

        Doubles each time and stops at a ceiling. Failures usually mean rate
        limiting or a dead session, and the worst response to either is to keep
        asking at full speed.
        """
        if failures <= 0:
            return 0
        grown = self.settings.backoff_seconds * (2 ** (failures - 1))
        return min(grown, self.settings.backoff_max_seconds)

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

        targets = settings.targets() or [settings.target_profile]
        watching = ", ".join(f"@{t}" for t in targets)
        self.log(f"Monitoring {watching} — {notifier.describe()}.")

        # Stopping the whole run because one of several accounts became visible
        # would abandon the others, so the setting only applies to a lone target.
        stop_on_unblock = settings.stop_on_unblock and len(targets) == 1
        if settings.stop_on_unblock and not stop_on_unblock:
            self.log(
                "Watching several profiles, so the run continues past the first "
                "one that becomes visible."
            )

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
        last_status: dict[str, str] = dict.fromkeys(targets, checker.UNKNOWN)
        last_fingerprint: dict[str, str] = {}
        checks = 0
        failures = 0
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

                broke_out = False
                for target in targets:
                    if self.stopping:
                        break

                    try:
                        result = probe.check(target)
                    except Exception as exc:  # noqa: BLE001 - browser errors vary
                        self.log(f"Check failed for @{target}: {exc}. Restarting…")
                        try:
                            probe.restart()
                        except checker.LoginFailed as restart_exc:
                            reason = str(restart_exc)
                            self.log(reason)
                            broke_out = True
                        break

                    checks += 1
                    prefix = f"@{target}: " if len(targets) > 1 else ""
                    self.on_status(result.status, f"{prefix}{result.detail}")
                    self.log(f"{prefix}{checker.label(result.status)} — {result.detail}")

                    self._record_signals(notifier, result, now, target)

                    previous = last_status.get(target, checker.UNKNOWN)
                    if result.status != previous and previous != checker.UNKNOWN:
                        self._record(probe, notifier, result, now, True, target)
                    elif result.fingerprint and last_fingerprint.get(target) and (
                        result.fingerprint != last_fingerprint[target]
                    ):
                        self.log(f"{prefix}Profile image changed.")
                        self._record(probe, notifier, result, now, False, target)

                    if checker.is_visible(result.status) and stop_on_unblock:
                        if previous in (checker.BLOCKED, checker.UNKNOWN):
                            reason = f"@{target} is visible — stopping."
                            self.log(reason)
                            broke_out = True
                            break

                    if result.status == checker.ERROR:
                        failures += 1
                    else:
                        failures = 0

                    last_status[target] = result.status
                    if result.fingerprint:
                        last_fingerprint[target] = result.fingerprint

                if broke_out:
                    break

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
                penalty = self._backoff(failures)
                if penalty:
                    self.log(
                        f"{failures} failed check{'s' if failures > 1 else ''} in a row "
                        f"— waiting {penalty}s before trying again."
                    )
                if not self._sleep(wait + penalty):
                    break
        finally:
            probe.stop()

        if self.stopping:
            reason = "Stopped."
        self.log(reason)
        return reason

    # ------------------------------------------------------------------
    def _record_signals(
        self,
        notifier: notifiers.Notifier,
        result: checker.CheckResult,
        now: datetime,
        target: str = "",
    ) -> None:
        """Diff this check's measurements against the last, and record moves.

        The saved snapshot is only replaced with what was actually observed
        merged over what we knew, so a check that failed to read one signal
        does not erase the previous value for it.
        """
        if result.snapshot is None or result.snapshot.is_empty():
            return

        target = target or self.settings.target_profile
        previous = self.snapshots.load(target)
        changes = signals.diff(previous, result.snapshot)

        merged = signals.Snapshot(
            counts={**(previous.counts if previous else {}), **result.snapshot.counts},
            flags={**(previous.flags if previous else {}), **result.snapshot.flags},
            members={
                **(previous.members if previous else {}),
                **result.snapshot.members,
            },
            taken_at=now.isoformat(timespec="seconds"),
        )
        self.snapshots.save(target, merged)

        for change in changes:
            self.log(str(change))
            event = Event(
                timestamp=now,
                status=checker.UNKNOWN,
                detail=change.detail,
                kind=change.kind,
                signal=change.name,
                target=target,
            )
            self.store.record(event)
            self.on_event(event)

            if change.kind not in self.settings.notify_kinds:
                continue  # recorded, just not worth interrupting anyone for

            try:
                notifier.send(f"@{target}: {change.detail}")
            except Exception as exc:  # noqa: BLE001 - never let a notifier kill the run
                self.log(f"Notification failed: {exc}")

    # ------------------------------------------------------------------
    def _record(
        self,
        probe,
        notifier: notifiers.Notifier,
        result: checker.CheckResult,
        now: datetime,
        changed: bool,
        target: str = "",
    ) -> None:
        """Persist an event, capture a screenshot, and notify."""
        settings = self.settings
        target = target or settings.target_profile
        shot = ""

        if settings.save_screenshots and probe.supports_screenshots:
            filename = f"{now:%Y%m%d_%H%M%S}_{result.status}.png"
            if probe.screenshot(settings.screenshot_dir / filename):
                shot = filename

        event = Event(now, result.status, result.detail, shot, target=target)
        self.store.record(event)
        self.on_event(event)

        if changed and checker.is_visible(result.status):
            message = (
                f"@{target} is visible again "
                f"({checker.label(result.status)}) at {event.stamp}."
            )
        elif changed:
            message = (
                f"@{target} changed to "
                f"{checker.label(result.status)} at {event.stamp}."
            )
        else:
            message = f"@{target} changed its profile image at {event.stamp}."

        try:
            if shot:
                notifier.send_photo(settings.screenshot_dir / shot, message)
            else:
                notifier.send(message)
        except Exception as exc:  # noqa: BLE001 - never let a notifier kill the run
            self.log(f"Notification failed: {exc}")
