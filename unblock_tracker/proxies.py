"""Optional HTTP proxy pool, fetched from a user-configured source URL."""

from __future__ import annotations

import random
from collections.abc import Callable

import requests

FETCH_TIMEOUT = 20
VALIDATE_TIMEOUT = 5
VALIDATE_URL = "https://www.instagram.com/"


class ProxyPool:
    """Fetches a proxy list once, then hands out proxies that actually work.

    Proxies that fail validation are dropped, so a long-running monitor
    gradually narrows the pool to the usable entries instead of retrying
    known-dead ones.
    """

    def __init__(self, source_url: str, log: Callable[[str], None] | None = None):
        self.source_url = source_url
        self.log = log or (lambda _msg: None)
        self._candidates: list[str] = []
        self._fetched = False

    def fetch(self) -> int:
        self.log("Fetching proxy list…")
        try:
            response = requests.get(self.source_url, timeout=FETCH_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            self.log(f"Could not fetch proxies: {exc}")
            self._candidates = []
        else:
            self._candidates = [
                line.strip() for line in response.text.splitlines() if line.strip()
            ]
            random.shuffle(self._candidates)
            self.log(f"Fetched {len(self._candidates)} candidate proxies.")

        self._fetched = True
        return len(self._candidates)

    def _validate(self, proxy: str) -> bool:
        url = proxy if "://" in proxy else f"http://{proxy}"
        try:
            response = requests.get(
                VALIDATE_URL,
                proxies={"http": url, "https": url},
                timeout=VALIDATE_TIMEOUT,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def next_working(self, max_tries: int = 25) -> str | None:
        """Return a validated proxy URL, or None if the pool is exhausted."""
        if not self._fetched:
            self.fetch()

        for _ in range(max_tries):
            if not self._candidates:
                self.log("No working proxies left in the pool.")
                return None
            candidate = self._candidates.pop()
            if self._validate(candidate):
                url = candidate if "://" in candidate else f"http://{candidate}"
                self.log(f"Using proxy {url}")
                return url

        self.log(f"No working proxy found in {max_tries} attempts.")
        return None
