"""The monitor loop: transitions, notifications, stopping and scheduling."""

from __future__ import annotations

import threading
import time
from datetime import datetime

import pytest

from unblock_tracker import checker, config, monitor

from .conftest import run_engine
from .fakes import BLOCKED, VISIBLE, DeadProbe, FakeProbe, install


def make_settings(tmp_path, **overrides) -> config.Settings:
    base = dict(
        instagram_username="tester",
        target_profile="watched",
        data_dir=str(tmp_path),
        # No wait between checks: these tests are about the loop's decisions,
        # not its pacing. test_stop_interrupts_a_long_wait sets a real interval.
        interval_min_seconds=0,
        interval_max_seconds=0,
        night_break_enabled=False,
        restart_after_checks=0,
        max_runtime_minutes=0,
    )
    base.update(overrides)
    return config.Settings(**base)


def build_engine(tmp_path, monkeypatch, script, **overrides):
    """Wire an engine to a scripted probe. Returns (engine, probe, notifier, events)."""
    box: list = []
    probe = FakeProbe(script, box)
    notifier = install(monkeypatch, probe)
    events: list[monitor.Event] = []
    engine = monitor.MonitorEngine(
        make_settings(tmp_path, **overrides), "pw", on_event=events.append
    )
    box.append(engine)
    return engine, probe, notifier, events


# ----------------------------------------------------------------------
# Transitions
# ----------------------------------------------------------------------
def test_blocked_to_visible_records_notifies_and_stops(tmp_path, monkeypatch):
    engine, probe, notifier, events = build_engine(
        tmp_path, monkeypatch, [BLOCKED, BLOCKED, VISIBLE, BLOCKED]
    )

    reason = run_engine(engine)

    assert len(events) == 1, f"expected one transition event, got {events}"
    event = events[0]
    assert event.status == checker.VISIBLE_PUBLIC
    assert event.screenshot.endswith(".png")
    assert (engine.settings.screenshot_dir / event.screenshot).exists()

    assert notifier.sent == [("photo", notifier.sent[0][1])]
    assert "visible again" in notifier.sent[0][1]

    assert "visible" in reason
    assert probe.stops >= 1, "the probe should be shut down on the way out"


def test_no_event_before_a_baseline_exists(tmp_path, monkeypatch):
    """The very first check establishes the baseline; it is not a transition."""
    engine, _probe, notifier, events = build_engine(
        tmp_path, monkeypatch, [BLOCKED], stop_on_unblock=False
    )

    run_engine(engine)

    assert events == []
    assert notifier.sent == []


def test_transitions_accumulate_when_stop_on_unblock_is_off(tmp_path, monkeypatch):
    engine, _probe, notifier, events = build_engine(
        tmp_path,
        monkeypatch,
        [BLOCKED, VISIBLE, BLOCKED, VISIBLE, BLOCKED],
        stop_on_unblock=False,
    )

    run_engine(engine)

    # Four changes follow the first (baseline) check.
    assert len(events) == 4, [e.status for e in events]
    assert len(notifier.sent) == 4
    statuses = [e.status for e in events]
    assert statuses == [
        checker.VISIBLE_PUBLIC,
        checker.BLOCKED,
        checker.VISIBLE_PUBLIC,
        checker.BLOCKED,
    ]


def test_repeated_identical_status_records_nothing(tmp_path, monkeypatch):
    engine, _probe, notifier, events = build_engine(
        tmp_path, monkeypatch, [BLOCKED] * 5, stop_on_unblock=False
    )

    run_engine(engine)

    assert events == []
    assert notifier.sent == []


# ----------------------------------------------------------------------
# Event store
# ----------------------------------------------------------------------
def test_event_store_writes_expected_csv_header(tmp_path, monkeypatch):
    engine, _probe, _notifier, _events = build_engine(
        tmp_path, monkeypatch, [BLOCKED, VISIBLE]
    )

    run_engine(engine)

    store = monitor.EventStore(engine.settings)
    rows = store.read_events()
    assert rows, "expected at least one recorded row"
    assert list(rows[0]) == ["Timestamp", "Status", "Detail", "Screenshot"]

    header = engine.settings.csv_path.read_text().splitlines()[0]
    assert header == "Timestamp,Status,Detail,Screenshot"


def test_event_store_appends_without_repeating_the_header(tmp_path):
    settings = make_settings(tmp_path)
    store = monitor.EventStore(settings)
    for index in range(3):
        store.record(
            monitor.Event(datetime.now(), checker.BLOCKED, f"detail {index}", "")
        )

    lines = settings.csv_path.read_text().strip().splitlines()
    assert len(lines) == 4, lines  # one header plus three rows
    assert len(store.read_events()) == 3


def test_read_events_on_a_missing_file_returns_empty(tmp_path):
    assert monitor.EventStore(make_settings(tmp_path)).read_events() == []


# ----------------------------------------------------------------------
# Stopping
# ----------------------------------------------------------------------
def test_stop_interrupts_a_long_wait_promptly(tmp_path, monkeypatch):
    """The loop waits on a threading.Event, so stop() must not wait out the interval."""
    interval = 60
    engine, _probe, _notifier, _events = build_engine(
        tmp_path,
        monkeypatch,
        [BLOCKED] * 50,
        interval_min_seconds=interval,
        interval_max_seconds=interval,
        stop_on_unblock=False,
    )

    finished = threading.Event()

    def target() -> None:
        engine.run()
        finished.set()

    threading.Thread(target=target, daemon=True).start()
    time.sleep(0.5)  # let it get into the wait

    requested = time.monotonic()
    engine.stop()
    assert finished.wait(10), "engine never stopped"
    elapsed = time.monotonic() - requested

    assert elapsed < interval / 10, f"stop took {elapsed:.2f}s with a {interval}s interval"


def test_stop_is_reported_as_the_reason(tmp_path, monkeypatch):
    engine, _probe, _notifier, _events = build_engine(
        tmp_path, monkeypatch, [BLOCKED] * 50, stop_on_unblock=False
    )
    engine.stop()  # already stopping before the first wait

    assert run_engine(engine) == "Stopped."


# ----------------------------------------------------------------------
# Scheduling
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("start", "end", "hour", "expected"),
    [
        (2, 6, 3, True),
        (2, 6, 2, True),  # inclusive at the start
        (2, 6, 6, False),  # exclusive at the end
        (2, 6, 7, False),
        (2, 6, 12, False),
        (22, 6, 23, True),  # window wraps past midnight
        (22, 6, 1, True),
        (22, 6, 22, True),
        (22, 6, 12, False),
        (22, 6, 6, False),
    ],
)
def test_night_break_window(tmp_path, start, end, hour, expected):
    engine = monitor.MonitorEngine(
        make_settings(
            tmp_path,
            night_break_enabled=True,
            night_break_start_hour=start,
            night_break_end_hour=end,
        ),
        "",
    )
    moment = datetime(2026, 1, 1, hour, 30)
    assert engine._in_night_break(moment) is expected


def test_night_break_disabled_is_never_active(tmp_path):
    engine = monitor.MonitorEngine(
        make_settings(tmp_path, night_break_enabled=True, night_break_start_hour=0,
                      night_break_end_hour=0),
        "",
    )
    # A zero-width window must not swallow the whole day.
    assert engine._in_night_break(datetime(2026, 1, 1, 3)) is False


# ----------------------------------------------------------------------
# Failure handling
# ----------------------------------------------------------------------
def test_login_failure_surfaces_as_the_reason(tmp_path, monkeypatch):
    probe = DeadProbe("Could not log in after 3 attempts: bad password")
    install(monkeypatch, probe)
    engine = monitor.MonitorEngine(make_settings(tmp_path), "pw")

    reason = run_engine(engine)

    assert reason == "Could not log in after 3 attempts: bad password"


def test_a_failing_check_restarts_the_browser_rather_than_dying(tmp_path, monkeypatch):
    class FlakyProbe(FakeProbe):
        def check(self):
            if self.starts == 1:
                raise RuntimeError("browser exploded")
            return super().check()

    box: list = []
    probe = FlakyProbe([BLOCKED, VISIBLE], box)
    install(monkeypatch, probe)
    engine = monitor.MonitorEngine(make_settings(tmp_path), "pw")
    box.append(engine)

    run_engine(engine)

    assert probe.starts >= 2, "engine should have restarted the probe"


def test_a_failing_notifier_does_not_kill_the_run(tmp_path, monkeypatch):
    class BrokenNotifier(monitor.notifiers.Notifier):
        def send(self, text):
            raise RuntimeError("telegram is down")

        def send_photo(self, path, caption):
            raise RuntimeError("telegram is down")

        def describe(self):
            return "broken"

    box: list = []
    probe = FakeProbe([BLOCKED, VISIBLE, BLOCKED], box)
    install(monkeypatch, probe, BrokenNotifier())
    events: list = []
    engine = monitor.MonitorEngine(
        make_settings(tmp_path, stop_on_unblock=False), "pw", on_event=events.append
    )
    box.append(engine)

    run_engine(engine)

    # The event is still recorded even though delivery failed.
    assert len(events) == 2
    assert monitor.EventStore(engine.settings).read_events()
