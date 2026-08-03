"""The Keychain wrapper.

Every test here runs against the in-memory backend installed by conftest, so
nothing touches a developer's real Keychain.
"""

from __future__ import annotations

import keyring
import pytest
from keyring.errors import KeyringError

from unblock_tracker import secrets


def test_absent_secret_reads_as_empty_string():
    assert secrets.get(secrets.INSTAGRAM_PASSWORD, "nobody") == ""


def test_round_trip(isolated_keyring):
    secrets.set(secrets.INSTAGRAM_PASSWORD, "hunter2", "alice")
    assert secrets.get(secrets.INSTAGRAM_PASSWORD, "alice") == "hunter2"
    assert (secrets.SERVICE, "instagram_password:alice") in isolated_keyring.store


def test_secrets_are_scoped_per_account():
    secrets.set(secrets.INSTAGRAM_PASSWORD, "alice-pw", "alice")
    secrets.set(secrets.INSTAGRAM_PASSWORD, "bob-pw", "bob")

    assert secrets.get(secrets.INSTAGRAM_PASSWORD, "alice") == "alice-pw"
    assert secrets.get(secrets.INSTAGRAM_PASSWORD, "bob") == "bob-pw"


def test_different_names_do_not_collide():
    secrets.set(secrets.INSTAGRAM_PASSWORD, "pw", "alice")
    secrets.set(secrets.TELEGRAM_BOT_TOKEN, "tok", "alice")
    secrets.set(secrets.PUSHBULLET_TOKEN, "pb", "alice")

    assert secrets.get(secrets.INSTAGRAM_PASSWORD, "alice") == "pw"
    assert secrets.get(secrets.TELEGRAM_BOT_TOKEN, "alice") == "tok"
    assert secrets.get(secrets.PUSHBULLET_TOKEN, "alice") == "pb"


def test_setting_a_blank_value_deletes_the_entry(isolated_keyring):
    secrets.set(secrets.TELEGRAM_BOT_TOKEN, "tok", "alice")
    secrets.set(secrets.TELEGRAM_BOT_TOKEN, "", "alice")

    assert secrets.get(secrets.TELEGRAM_BOT_TOKEN, "alice") == ""
    assert (secrets.SERVICE, "telegram_bot_token:alice") not in isolated_keyring.store


def test_deleting_something_absent_is_not_an_error():
    secrets.delete(secrets.PUSHBULLET_TOKEN, "never-existed")  # must not raise


def test_a_locked_keychain_reads_as_empty_rather_than_crashing(monkeypatch):
    """secrets.get swallows KeyringError so a locked Keychain cannot crash the app."""

    def explode(*_args, **_kwargs):
        raise KeyringError("keychain is locked")

    monkeypatch.setattr(keyring, "get_password", explode)
    assert secrets.get(secrets.INSTAGRAM_PASSWORD, "alice") == ""


def test_the_real_keychain_is_never_reachable_from_the_suite():
    """Guard the isolation itself.

    If the autouse fixture ever stops applying, this fails loudly rather than
    letting the suite quietly read and delete a developer's real secrets.
    """
    from .conftest import InMemoryKeyring

    assert isinstance(keyring.get_keyring(), InMemoryKeyring), (
        f"tests are talking to {keyring.get_keyring()!r}, not the in-memory backend"
    )
    assert "macOS" not in secrets.backend_name()


@pytest.mark.parametrize(
    ("name", "account", "expected"),
    [
        ("instagram_password", "alice", "instagram_password:alice"),
        ("instagram_password", "", "instagram_password"),
    ],
)
def test_key_layout(name, account, expected):
    assert secrets._key(name, account) == expected
