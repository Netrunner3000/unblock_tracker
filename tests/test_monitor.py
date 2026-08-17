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
    assert list(rows[0]) == ["Timestamp", "Target", "Status", "Detail", "Screenshot"]

    header = engine.settings.csv_path.read_text().splitlines()[0]
    assert header == "Timestamp,Target,Status,Detail,Screenshot"


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
        def check(self, target: str = ""):
            if self.starts == 1:
                raise RuntimeError("browser exploded")
            return super().check(target)

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


# ----------------------------------------------------------------------
# Tracked signals
# ----------------------------------------------------------------------
def result_with(counts=None, flags=None, members=None, status=checker.BLOCKED):
    from unblock_tracker.signals import Snapshot

    return checker.CheckResult(
        status,
        "detail",
        snapshot=Snapshot(counts=counts or {}, flags=flags or {}, members=members or {}),
    )


def test_the_first_measurement_is_a_baseline_not_an_event(tmp_path, monkeypatch):
    engine, _probe, notifier, events = build_engine(
        tmp_path, monkeypatch, [result_with(counts={"followers": 100})],
        stop_on_unblock=False,
    )

    run_engine(engine)

    assert events == []
    assert notifier.sent == []
    assert engine.snapshots.load("watched").counts == {"followers": 100}


def test_a_follower_count_moving_is_recorded(tmp_path, monkeypatch):
    engine, _probe, notifier, events = build_engine(
        tmp_path,
        monkeypatch,
        [result_with(counts={"followers": 100}), result_with(counts={"followers": 103})],
        stop_on_unblock=False,
    )

    run_engine(engine)

    assert len(events) == 1
    assert events[0].kind == "count"
    assert events[0].signal == "followers"
    assert events[0].target == "watched"
    assert "+3" in events[0].detail
    # Counts are recorded but not announced by default — an active account
    # moves them constantly and would drown the alerts that matter.
    assert notifier.sent == []


def test_counts_are_announced_once_asked_for(tmp_path, monkeypatch):
    engine, _probe, notifier, _events = build_engine(
        tmp_path,
        monkeypatch,
        [result_with(counts={"followers": 100}), result_with(counts={"followers": 103})],
        stop_on_unblock=False,
        notify_kinds=["count"],
    )

    run_engine(engine)

    assert notifier.sent and "watched" in notifier.sent[0][1]


def test_membership_changes_are_announced_by_default(tmp_path, monkeypatch):
    """Someone unfollowing is rare and meaningful, unlike a count ticking."""
    engine, _probe, notifier, _events = build_engine(
        tmp_path,
        monkeypatch,
        [
            result_with(members={"followers": ["alice", "bob"]}),
            result_with(members={"followers": ["alice"]}),
        ],
        stop_on_unblock=False,
    )

    run_engine(engine)

    assert notifier.sent, "membership changes should notify without configuration"


def test_someone_unfollowing_is_recorded_by_name(tmp_path, monkeypatch):
    engine, _probe, _notifier, events = build_engine(
        tmp_path,
        monkeypatch,
        [
            result_with(members={"followers": ["alice", "bob"]}),
            result_with(members={"followers": ["alice"]}),
        ],
        stop_on_unblock=False,
    )

    run_engine(engine)

    assert len(events) == 1
    assert events[0].kind == "members"
    assert "@bob" in events[0].detail


def test_a_check_that_reads_nothing_does_not_erase_what_we_knew(tmp_path, monkeypatch):
    """A failed scrape must not look like the follower count dropping to zero."""
    engine, _probe, _notifier, events = build_engine(
        tmp_path,
        monkeypatch,
        [result_with(counts={"followers": 100}), result_with()],  # second reads nothing
        stop_on_unblock=False,
    )

    run_engine(engine)

    assert events == []
    assert engine.snapshots.load("watched").counts == {"followers": 100}


def test_a_partial_read_keeps_the_signals_it_could_not_see(tmp_path, monkeypatch):
    engine, _probe, _notifier, _events = build_engine(
        tmp_path,
        monkeypatch,
        [
            result_with(counts={"followers": 100, "posts": 10}),
            result_with(counts={"followers": 101}),  # posts not read this time
        ],
        stop_on_unblock=False,
    )

    run_engine(engine)

    stored = engine.snapshots.load("watched").counts
    assert stored == {"followers": 101, "posts": 10}, "posts should survive"


def test_signal_events_reach_the_csv(tmp_path, monkeypatch):
    engine, _probe, _notifier, _events = build_engine(
        tmp_path,
        monkeypatch,
        [result_with(counts={"followers": 1}), result_with(counts={"followers": 2})],
        stop_on_unblock=False,
    )

    run_engine(engine)

    rows = monitor.EventStore(engine.settings).read_events()
    assert any(r["Status"] == "followers" for r in rows), rows


# ----------------------------------------------------------------------
# Multiple targets
# ----------------------------------------------------------------------
def test_every_target_is_checked_each_cycle(tmp_path, monkeypatch):
    seen: list[str] = []

    class RecordingProbe(FakeProbe):
        def check(self, target: str = ""):
            seen.append(target)
            if len(seen) >= 6:
                self.engine_box[0].stop()
            return BLOCKED

    box: list = []
    probe = RecordingProbe([], box)
    install(monkeypatch, probe)
    engine = monitor.MonitorEngine(
        make_settings(tmp_path, target_profile="alpha", watchlist=["beta", "gamma"]), "pw"
    )
    box.append(engine)

    run_engine(engine)

    assert seen[:3] == ["alpha", "beta", "gamma"]
    assert seen[3:6] == ["alpha", "beta", "gamma"], "should cycle in order"


def test_targets_keep_separate_histories(tmp_path, monkeypatch):
    """A change for one handle must not be attributed to another."""
    script = {
        "alpha": [BLOCKED, VISIBLE],
        "beta": [BLOCKED, BLOCKED],
    }

    class PerTargetProbe(FakeProbe):
        def check(self, target: str = ""):
            queue = script[target]
            if not queue:
                self.engine_box[0].stop()
                return BLOCKED
            return queue.pop(0)

    box: list = []
    probe = PerTargetProbe([], box)
    install(monkeypatch, probe)
    events: list = []
    engine = monitor.MonitorEngine(
        make_settings(tmp_path, target_profile="alpha", watchlist=["beta"]),
        "pw",
        on_event=events.append,
    )
    box.append(engine)

    run_engine(engine)

    changed = [e for e in events if e.kind == "visibility"]
    assert changed, "alpha changed and should have been recorded"
    # beta never moved off BLOCKED, so nothing may be attributed to it.
    assert {e.target for e in changed} == {"alpha"}, [e.target for e in changed]


def test_stop_on_unblock_is_ignored_with_several_targets(tmp_path, monkeypatch):
    """Stopping the run would abandon the other profiles being watched."""
    calls = {"n": 0}

    class Probe(FakeProbe):
        def check(self, target: str = ""):
            calls["n"] += 1
            if calls["n"] > 8:
                self.engine_box[0].stop()
            return VISIBLE

    box: list = []
    probe = Probe([], box)
    install(monkeypatch, probe)
    engine = monitor.MonitorEngine(
        make_settings(
            tmp_path, target_profile="alpha", watchlist=["beta"], stop_on_unblock=True
        ),
        "pw",
    )
    box.append(engine)

    assert run_engine(engine) == "Stopped."
    assert calls["n"] > 2, "should have kept going rather than stopping at the first"


def test_a_single_target_still_stops_on_unblock(tmp_path, monkeypatch):
    engine, _probe, _notifier, _events = build_engine(
        tmp_path, monkeypatch, [BLOCKED, VISIBLE], stop_on_unblock=True
    )

    assert "visible" in run_engine(engine)


# ----------------------------------------------------------------------
# Backoff after failures
# ----------------------------------------------------------------------
def test_no_backoff_while_checks_succeed(tmp_path):
    engine = monitor.MonitorEngine(make_settings(tmp_path), "pw")
    assert engine._backoff(0) == 0


def test_backoff_doubles_with_each_consecutive_failure(tmp_path):
    engine = monitor.MonitorEngine(
        make_settings(tmp_path, backoff_seconds=30, backoff_max_seconds=100000), "pw"
    )
    assert [engine._backoff(n) for n in (1, 2, 3, 4)] == [30, 60, 120, 240]


def test_backoff_stops_at_the_ceiling(tmp_path):
    engine = monitor.MonitorEngine(
        make_settings(tmp_path, backoff_seconds=60, backoff_max_seconds=300), "pw"
    )
    assert engine._backoff(10) == 300
    assert engine._backoff(50) == 300, "must not overflow past the cap"


def test_a_failing_check_triggers_a_wait(tmp_path, monkeypatch):
    """Being rate-limited and asking harder is the worst possible response."""
    error = checker.CheckResult(checker.ERROR, "rate limited")
    waits: list[float] = []

    engine, _probe, _notifier, _events = build_engine(
        tmp_path, monkeypatch, [error, error, error],
        stop_on_unblock=False, backoff_seconds=10,
    )
    real_sleep = engine._sleep
    monkeypatch.setattr(
        engine, "_sleep", lambda s: (waits.append(s), real_sleep(0))[1]
    )

    run_engine(engine)

    assert waits, "expected at least one wait"
    assert max(waits) >= 10, f"no backoff applied: {waits}"


def test_backoff_resets_after_a_successful_check(tmp_path, monkeypatch):
    error = checker.CheckResult(checker.ERROR, "transient")
    waits: list[float] = []

    engine, _probe, _notifier, _events = build_engine(
        tmp_path, monkeypatch, [error, BLOCKED, BLOCKED],
        stop_on_unblock=False, backoff_seconds=10,
    )
    real_sleep = engine._sleep
    monkeypatch.setattr(
        engine, "_sleep", lambda s: (waits.append(s), real_sleep(0))[1]
    )

    run_engine(engine)

    assert waits[-1] == 0, f"a success should clear the penalty, got {waits}"
