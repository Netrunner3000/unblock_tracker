"""Secret storage backed by the macOS Keychain.

Nothing sensitive is ever written to a file in this project, so there is
nothing for git to commit or for the Google Drive backup to copy. Values are
keyed by account name so several Instagram accounts can coexist.
"""

from __future__ import annotations

import keyring
from keyring.errors import KeyringError

SERVICE = "unblock_tracker"

INSTAGRAM_PASSWORD = "instagram_password"
TELEGRAM_BOT_TOKEN = "telegram_bot_token"
PUSHBULLET_TOKEN = "pushbullet_token"


def _key(name: str, account: str = "") -> str:
    return f"{name}:{account}" if account else name


def get(name: str, account: str = "") -> str:
    """Return the stored secret, or "" if absent or the Keychain is locked."""
    try:
        return keyring.get_password(SERVICE, _key(name, account)) or ""
    except KeyringError:
        return ""


def set(name: str, value: str, account: str = "") -> None:  # noqa: A001
    """Store a secret, or remove it when `value` is blank."""
    if value:
        keyring.set_password(SERVICE, _key(name, account), value)
    else:
        delete(name, account)


def delete(name: str, account: str = "") -> None:
    try:
        keyring.delete_password(SERVICE, _key(name, account))
    except KeyringError:
        pass  # Nothing stored under that key.


def backend_name() -> str:
    try:
        return type(keyring.get_keyring()).__module__
    except KeyringError:
        return "unavailable"
