"""Outbound notifications: Telegram, Pushbullet, or nothing at all.

Each notifier is constructed from user-supplied settings; no chat IDs, bot
handles or tokens are hard-coded anywhere in this module.
"""

from __future__ import annotations

from pathlib import Path

import requests

from . import config, secrets

TIMEOUT = 15


class Notifier:
    """No-op base class — also the 'notifications off' implementation."""

    name = "none"

    def send(self, text: str) -> None:
        return None

    def send_photo(self, path: Path, caption: str) -> None:
        """Fall back to a text message when the transport has no photo support."""
        self.send(caption)

    def describe(self) -> str:
        return "Notifications are off"


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def send(self, text: str) -> None:
        requests.post(
            self._url("sendMessage"),
            data={"chat_id": self.chat_id, "text": text},
            timeout=TIMEOUT,
        ).raise_for_status()

    def send_photo(self, path: Path, caption: str) -> None:
        with path.open("rb") as handle:
            requests.post(
                self._url("sendPhoto"),
                data={"chat_id": self.chat_id, "caption": caption},
                files={"photo": handle},
                timeout=TIMEOUT,
            ).raise_for_status()

    def describe(self) -> str:
        return f"Telegram chat {self.chat_id}"


class PushbulletNotifier(Notifier):
    name = "pushbullet"

    def __init__(self, token: str):
        self.token = token

    def send(self, text: str) -> None:
        requests.post(
            "https://api.pushbullet.com/v2/pushes",
            headers={"Access-Token": self.token},
            json={"type": "note", "title": "Unblock Tracker", "body": text},
            timeout=TIMEOUT,
        ).raise_for_status()

    def describe(self) -> str:
        return "Pushbullet"


def build(settings: config.Settings) -> Notifier:
    """Create the notifier named in settings, pulling its token from the Keychain."""
    if settings.notifier == config.NOTIFIER_TELEGRAM:
        return TelegramNotifier(
            token=secrets.get(secrets.TELEGRAM_BOT_TOKEN, settings.instagram_username),
            chat_id=settings.telegram_chat_id,
        )
    if settings.notifier == config.NOTIFIER_PUSHBULLET:
        return PushbulletNotifier(
            token=secrets.get(secrets.PUSHBULLET_TOKEN, settings.instagram_username),
        )
    return Notifier()
