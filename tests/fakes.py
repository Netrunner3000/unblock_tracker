"""Stand-ins for the browser and the notification transports.

The engine reaches the outside world through exactly two factories,
`checker.build` and `notifiers.build`. Replacing those is enough to run the
whole loop with no network, no browser and no Instagram.
"""

from __future__ import annotations

from pathlib import Path

from unblock_tracker import checker, notifiers


class FakeProbe:
    """Replays a scripted sequence of check results.

    Once the script runs dry it asks the engine to stop. Without that a test
    with stop_on_unblock disabled and no runtime limit would loop forever.
    """

    supports_screenshots = True

    def __init__(self, script, engine_box: list | None = None):
        self.script = list(script)
        self.engine_box = engine_box if engine_box is not None else []
        self.starts = 0
        self.stops = 0
        self.screenshots: list[str] = []

    def start(self) -> None:
        self.starts += 1

    def restart(self) -> None:
        self.starts += 1

    def stop(self) -> None:
        self.stops += 1

    def check(self) -> checker.CheckResult:
        if self.script:
            return self.script.pop(0)
        if self.engine_box:
            self.engine_box[0].stop()
        return checker.CheckResult(checker.BLOCKED, "script exhausted")

    def screenshot(self, path: Path) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-png")
        self.screenshots.append(path.name)
        return True


class DeadProbe(FakeProbe):
    """A probe that cannot log in."""

    def __init__(self, message: str = "Could not log in after 3 attempts: nope"):
        super().__init__([])
        self.message = message

    def start(self) -> None:
        raise checker.LoginFailed(self.message)


class RecordingNotifier(notifiers.Notifier):
    """Captures what would have been sent."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, text: str) -> None:
        self.sent.append(("text", text))

    def send_photo(self, path: Path, caption: str) -> None:
        self.sent.append(("photo", caption))

    def describe(self) -> str:
        return "recording notifier"


def install(monkeypatch, probe, notifier=None) -> RecordingNotifier:
    """Point the engine's factories at the fakes."""
    from unblock_tracker import monitor

    notifier = notifier or RecordingNotifier()
    monkeypatch.setattr(monitor.checker, "build", lambda *a, **k: probe)
    monkeypatch.setattr(monitor.notifiers, "build", lambda *a, **k: notifier)
    return notifier


BLOCKED = checker.CheckResult(checker.BLOCKED, "blocked")
VISIBLE = checker.CheckResult(checker.VISIBLE_PUBLIC, "visible")
PRIVATE = checker.CheckResult(checker.VISIBLE_PRIVATE, "private")
