"""Saved browser sessions: where they live, when they're reused, how to clear."""

from __future__ import annotations

import pytest

from unblock_tracker import checker, config


@pytest.fixture
def session_root(tmp_path, monkeypatch):
    """Redirect saved sessions into a temp dir for the whole test."""
    root = tmp_path / "sessions"
    monkeypatch.setattr(config, "SESSION_ROOT", root)
    return root


# ----------------------------------------------------------------------
# Where the cookies live
# ----------------------------------------------------------------------
def test_sessions_are_kept_out_of_the_project_folder():
    """Cookies are auth material; the project folder is git-tracked and rsynced."""
    assert config.SESSION_ROOT.is_absolute()
    assert config.PROJECT_ROOT not in config.SESSION_ROOT.parents
    assert config.SESSION_ROOT != config.PROJECT_ROOT
    assert "Application Support" in str(config.SESSION_ROOT)


def test_each_account_gets_its_own_session(session_root):
    alice = config.Settings(instagram_username="alice").session_dir
    bob = config.Settings(instagram_username="bob").session_dir
    assert alice != bob
    assert alice.parent == bob.parent == session_root


@pytest.mark.parametrize(
    ("handle", "expected"),
    [
        ("simple", "simple"),
        ("with.dots", "with.dots"),
        ("with_underscore", "with_underscore"),
        ("../escape", ".._escape"),  # must not climb out of the session root
        ("", "default"),
        # Dots survive sanitising, so these would otherwise traverse upward —
        # and forget_session() rmtree's whatever this resolves to.
        ("..", "default"),
        (".", "default"),
        ("...", "default"),
    ],
)
def test_handles_are_sanitised_into_directory_names(session_root, handle, expected):
    directory = config.Settings(instagram_username=handle).session_dir
    assert directory.name == expected
    assert directory.parent == session_root


@pytest.mark.parametrize(
    "handle", ["../../etc/passwd", "..", ".", "...", "/", "..//..", "  ..  "]
)
def test_no_handle_can_escape_the_session_root(session_root, handle):
    """forget_session() rmtree's this path, so traversal here is destructive."""
    directory = config.Settings(instagram_username=handle).session_dir
    assert directory.resolve().parent == session_root.resolve(), (
        f"{handle!r} escaped to {directory.resolve()}"
    )


# ----------------------------------------------------------------------
# Detecting and clearing
# ----------------------------------------------------------------------
def test_no_saved_session_reported_when_nothing_stored(session_root):
    assert checker.has_saved_session(config.Settings(instagram_username="alice")) is False


def test_an_empty_directory_does_not_count_as_a_session(session_root):
    settings = config.Settings(instagram_username="alice")
    settings.session_dir.mkdir(parents=True)
    assert checker.has_saved_session(settings) is False


def test_a_populated_directory_counts_as_a_session(session_root):
    settings = config.Settings(instagram_username="alice")
    settings.session_dir.mkdir(parents=True)
    (settings.session_dir / "Cookies").write_bytes(b"fake")
    assert checker.has_saved_session(settings) is True


def test_forget_session_removes_it(session_root):
    settings = config.Settings(instagram_username="alice")
    (settings.session_dir / "Default").mkdir(parents=True)
    (settings.session_dir / "Default" / "Cookies").write_bytes(b"fake")

    assert checker.forget_session(settings) is True
    assert not settings.session_dir.exists()
    assert checker.has_saved_session(settings) is False


def test_forget_session_on_nothing_is_harmless(session_root):
    assert checker.forget_session(config.Settings(instagram_username="ghost")) is False


def test_forgetting_one_account_leaves_the_other(session_root):
    alice = config.Settings(instagram_username="alice")
    bob = config.Settings(instagram_username="bob")
    for settings in (alice, bob):
        settings.session_dir.mkdir(parents=True)
        (settings.session_dir / "Cookies").write_bytes(b"fake")

    checker.forget_session(alice)

    assert not alice.session_dir.exists()
    assert checker.has_saved_session(bob) is True


# ----------------------------------------------------------------------
# Chrome options
# ----------------------------------------------------------------------
def _arguments(settings) -> list[str]:
    probe = checker.BrowserChecker(settings, "pw")
    return probe._options(None).arguments


def test_persisting_passes_a_dedicated_profile_to_chrome(session_root):
    settings = config.Settings(instagram_username="alice", persist_session=True)
    flag = f"--user-data-dir={settings.session_dir}"
    assert flag in _arguments(settings)


def test_disabling_persistence_passes_no_profile(session_root):
    settings = config.Settings(instagram_username="alice", persist_session=False)
    assert not any(a.startswith("--user-data-dir") for a in _arguments(settings))
    assert not settings.session_dir.exists(), "nothing should be created when off"


def test_persistence_is_on_by_default():
    assert config.Settings().persist_session is True


# ----------------------------------------------------------------------
# Reuse behaviour
# ----------------------------------------------------------------------
class FakeDriver:
    def __init__(self, logged_in: bool):
        self.logged_in = logged_in
        self.visited: list[str] = []

    def get(self, url):
        self.visited.append(url)

    def execute_script(self, script, *args):
        # The page-ready wait polls document.readyState.
        return "complete"

    @property
    def page_source(self):
        return '<div aria-label="Home">' if self.logged_in else "<div>login</div>"

    def quit(self):
        pass


def _prepared(monkeypatch, settings, logged_in: bool):
    """A BrowserChecker whose driver and sleeps are stubbed out."""
    probe = checker.BrowserChecker(settings, "pw")
    driver = FakeDriver(logged_in)
    monkeypatch.setattr(probe, "_new_driver", lambda _proxy: driver)
    monkeypatch.setattr(checker.time, "sleep", lambda _s: None)
    logged_in_calls: list[str] = []
    original_login = probe._login
    monkeypatch.setattr(
        probe, "_login", lambda: (logged_in_calls.append("login"), original_login)[0]
    )
    return probe, logged_in_calls


def test_a_valid_saved_session_skips_the_sign_in(monkeypatch, session_root):
    settings = config.Settings(instagram_username="alice", persist_session=True)
    probe, logins = _prepared(monkeypatch, settings, logged_in=True)

    probe.start()

    assert logins == [], "should not have signed in with a valid session"
    assert probe.reused_session is True


def test_a_stale_session_falls_back_to_signing_in(monkeypatch, session_root):
    """The session existing is not enough — it has to still be valid."""
    settings = config.Settings(
        instagram_username="alice", persist_session=True, verify_login=False
    )
    probe, logins = _prepared(monkeypatch, settings, logged_in=False)

    probe.start()

    assert logins == ["login"], "a stale session must trigger a real sign-in"
    assert probe.reused_session is False


def test_without_persistence_it_always_signs_in(monkeypatch, session_root):
    settings = config.Settings(
        instagram_username="alice", persist_session=False, verify_login=False
    )
    probe, logins = _prepared(monkeypatch, settings, logged_in=True)

    probe.start()

    assert logins == ["login"], "persistence off means sign in every time"
