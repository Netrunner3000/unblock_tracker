"""Shared fixtures.

Two things every test in this suite depends on:

* The Keychain is replaced with an in-memory backend for the whole session, so
  no test can read, overwrite or delete a developer's real stored secrets. This
  is enforced by an autouse fixture rather than left to each test to remember.
* Qt runs on the offscreen platform, so the UI tests need no display.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import pytest

# Must be set before the first QApplication is constructed.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import keyring  # noqa: E402
from keyring.backend import KeyringBackend  # noqa: E402
from keyring.errors import PasswordDeleteError  # noqa: E402


class InMemoryKeyring(KeyringBackend):
    """A Keychain stand-in that lives and dies with the test session."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        try:
            del self.store[(service, username)]
        except KeyError:
            raise PasswordDeleteError(username) from None


@pytest.fixture(autouse=True)
def isolated_keyring():
    """Swap in the fake backend for every test, real Keychain untouched."""
    previous = keyring.get_keyring()
    fake = InMemoryKeyring()
    keyring.set_keyring(fake)
    try:
        yield fake
    finally:
        keyring.set_keyring(previous)


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the session; Qt does not allow more than one."""
    from PySide6.QtWidgets import QApplication

    from ui import theme

    app = QApplication.instance() or QApplication([])
    theme.apply(app, theme.DARK)
    yield app


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    """Point config.save()/load() at a temp file instead of the real one."""
    from unblock_tracker import config

    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    return path


def run_engine(engine, timeout: float = 20.0) -> str:
    """Run an engine on a thread so a hang fails the test instead of wedging it."""
    result: list[str] = []

    def target() -> None:
        result.append(engine.run())

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    assert not thread.is_alive(), f"engine did not finish within {timeout}s"
    return result[0]
