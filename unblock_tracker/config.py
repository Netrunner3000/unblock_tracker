"""User settings: everything the monitor needs that isn't a secret.

Secrets (password, bot token, Pushbullet token) live in the Keychain — see
`secrets.py`. This file holds only non-sensitive preferences, and it still
ships empty: the account name and target handle have no defaults, so a fresh
checkout cannot run until someone types them in.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.json"

CHECK_MODE_LOGIN = "login"
CHECK_MODE_ANONYMOUS = "anonymous"

NOTIFIER_NONE = "none"
NOTIFIER_TELEGRAM = "telegram"
NOTIFIER_PUSHBULLET = "pushbullet"

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Brave/1.52.129 Chrome/113.0.0.0 Safari/537.36",
]

DEFAULT_PROXY_SOURCE = (
    "https://api.proxyscrape.com/v2/"
    "?request=getproxies&protocol=http&timeout=3000&country=all"
)


@dataclass
class Settings:
    """Everything the monitor reads. Identity fields deliberately start empty."""

    # --- Identity: no defaults, ever. The user types these in. ---
    instagram_username: str = ""
    target_profile: str = ""
    telegram_chat_id: str = ""

    # --- What kind of check to run ---
    check_mode: str = CHECK_MODE_LOGIN
    notifier: str = NOTIFIER_NONE

    # --- Pacing ---
    interval_min_seconds: int = 10
    interval_max_seconds: int = 20
    max_runtime_minutes: int = 120  # 0 = run until stopped
    stop_on_unblock: bool = True

    night_break_enabled: bool = True
    night_break_start_hour: int = 2
    night_break_end_hour: int = 6

    # --- Browser / detection profile (login mode only) ---
    headless: bool = True
    browser_binary: str = ""  # blank = Selenium's default Chrome
    chromedriver_path: str = ""  # blank = Selenium Manager resolves it
    rotate_user_agent: bool = True
    user_agents: list[str] = field(default_factory=lambda: list(DEFAULT_USER_AGENTS))
    restart_after_checks: int = 100  # 0 = never restart mid-run
    verify_login: bool = True
    login_attempts: int = 3

    # --- Proxies ---
    use_proxy: bool = False
    proxy_source_url: str = DEFAULT_PROXY_SOURCE

    # --- Output ---
    save_screenshots: bool = True
    data_dir: str = "runs"

    # ------------------------------------------------------------------
    # Derived paths
    # ------------------------------------------------------------------
    def resolved_data_dir(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @property
    def csv_path(self) -> Path:
        return self.resolved_data_dir() / "events.csv"

    @property
    def log_path(self) -> Path:
        return self.resolved_data_dir() / "monitor.log"

    @property
    def screenshot_dir(self) -> Path:
        return self.resolved_data_dir() / "screenshots"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self, password: str = "", token: str = "") -> list[str]:
        """Return a list of human-readable problems; empty means good to run."""
        problems: list[str] = []

        if not self.target_profile.strip():
            problems.append("Target profile is required.")

        if self.check_mode == CHECK_MODE_LOGIN:
            if not self.instagram_username.strip():
                problems.append("Instagram username is required for login mode.")
            if not password:
                problems.append("Instagram password is not set in the Keychain.")

        if self.notifier == NOTIFIER_TELEGRAM:
            if not token:
                problems.append("Telegram bot token is not set in the Keychain.")
            if not self.telegram_chat_id.strip():
                problems.append("Telegram chat ID is required.")
        elif self.notifier == NOTIFIER_PUSHBULLET and not token:
            problems.append("Pushbullet token is not set in the Keychain.")

        if self.interval_min_seconds < 1:
            problems.append("Minimum interval must be at least 1 second.")
        if self.interval_max_seconds < self.interval_min_seconds:
            problems.append("Maximum interval must be greater than the minimum.")

        if self.check_mode == CHECK_MODE_LOGIN and not self.user_agents:
            problems.append("At least one user agent is required.")

        if not 0 <= self.night_break_start_hour <= 23:
            problems.append("Night break start hour must be between 0 and 23.")
        if not 0 <= self.night_break_end_hour <= 23:
            problems.append("Night break end hour must be between 0 and 23.")

        return problems


def load(path: Path | None = None) -> Settings:
    """Load settings, falling back to blank defaults when no config exists."""
    path = path or CONFIG_PATH
    if not path.exists():
        return Settings()

    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return Settings()

    known = {f.name for f in fields(Settings)}
    return Settings(**{k: v for k, v in raw.items() if k in known})


def save(settings: Settings, path: Path | None = None) -> None:
    path = path or CONFIG_PATH
    path.write_text(json.dumps(asdict(settings), indent=2) + "\n")
