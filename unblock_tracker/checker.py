"""The two ways of asking "can I see this profile?".

`BrowserChecker` logs in with Selenium and reads the rendered profile page —
the accurate option, and the only one that can take screenshots.
`AnonymousChecker` just fetches the public page with `requests`; it needs no
credentials but only sees what a logged-out visitor sees.
"""

from __future__ import annotations

import hashlib
import shutil
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from . import config
from .proxies import ProxyPool

# --- Statuses -----------------------------------------------------------
UNKNOWN = "unknown"
BLOCKED = "blocked"
VISIBLE_PRIVATE = "visible_private"
VISIBLE_PUBLIC = "visible_public"
ERROR = "error"

LABELS = {
    UNKNOWN: "Unknown",
    BLOCKED: "Blocked or unavailable",
    VISIBLE_PRIVATE: "Visible (private account)",
    VISIBLE_PUBLIC: "Visible (public)",
    ERROR: "Check failed",
}

_BLOCKED_MARKERS = (
    "Sorry, this page isn't available.",
    "Sorry, this page isn’t available.",
    "The link you followed may be broken",
)


def is_visible(status: str) -> bool:
    """True when the target profile is reachable from this account."""
    return status in (VISIBLE_PRIVATE, VISIBLE_PUBLIC)


def label(status: str) -> str:
    return LABELS.get(status, status)


@dataclass
class CheckResult:
    status: str
    detail: str = ""
    fingerprint: str = ""  # avatar hash, anonymous mode only


class LoginFailed(RuntimeError):
    pass


class BrowserChecker:
    """Selenium-driven check from inside a logged-in session."""

    supports_screenshots = True

    def __init__(
        self,
        settings: config.Settings,
        password: str,
        log: Callable[[str], None] | None = None,
    ):
        self.settings = settings
        self.password = password
        self.log = log or (lambda _msg: None)
        self.driver: webdriver.Chrome | None = None
        self.reused_session = False
        self.pool = (
            ProxyPool(settings.proxy_source_url, self.log)
            if settings.use_proxy
            else None
        )

    # -- driver lifecycle ------------------------------------------------
    def _options(self, proxy: str | None) -> Options:
        options = Options()
        if self.settings.browser_binary:
            options.binary_location = self.settings.browser_binary
        if self.settings.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        if self.settings.rotate_user_agent and self.settings.user_agents:
            options.add_argument(f"user-agent={random.choice(self.settings.user_agents)}")
        if proxy:
            options.add_argument(f"--proxy-server={proxy}")
        if self.settings.persist_session:
            # A dedicated profile directory, never the user's real Chrome one:
            # Chrome refuses to start against a profile another instance holds.
            session = self.settings.session_dir
            session.mkdir(parents=True, exist_ok=True)
            options.add_argument(f"--user-data-dir={session}")
        return options

    def _new_driver(self, proxy: str | None) -> webdriver.Chrome:
        options = self._options(proxy)
        # A blank chromedriver path lets Selenium Manager resolve the driver,
        # which keeps this working on machines without a Homebrew chromedriver.
        service = (
            Service(self.settings.chromedriver_path)
            if self.settings.chromedriver_path
            else Service()
        )
        return webdriver.Chrome(service=service, options=options)

    def start(self) -> None:
        attempts = max(1, self.settings.login_attempts)
        last_error = "unknown error"

        for attempt in range(1, attempts + 1):
            proxy = self.pool.next_working() if self.pool else None
            if self.pool and not proxy:
                raise LoginFailed("Proxying is on but no working proxy was found.")

            try:
                self.driver = self._new_driver(proxy)
            except WebDriverException as exc:
                last_error = str(exc).strip().splitlines()[0]
                self.log(f"Could not start the browser: {last_error}")
                raise LoginFailed(f"Could not start the browser: {last_error}") from exc

            try:
                # A saved session is the whole point: signing in again on every
                # start (and on every mid-run browser restart) is what gets an
                # account challenged.
                if self.settings.persist_session and self._is_logged_in():
                    self.log("Reused the saved session — no sign-in needed.")
                    self.reused_session = True
                    return

                self._login()
                if not self.settings.verify_login or self._is_logged_in():
                    self.log("Signed in." + (" Session saved for next time."
                                             if self.settings.persist_session else ""))
                    self.reused_session = False
                    return
                last_error = "Instagram did not accept the session."
                self.log(f"Login attempt {attempt}/{attempts} failed.")
            except WebDriverException as exc:
                last_error = str(exc).strip().splitlines()[0]
                self.log(f"Login attempt {attempt}/{attempts} errored: {last_error}")

            self.stop()
            time.sleep(2)

        raise LoginFailed(f"Could not log in after {attempts} attempts: {last_error}")

    def _login(self) -> None:
        assert self.driver is not None
        self.driver.get("https://www.instagram.com/accounts/login/")
        time.sleep(3)
        self.driver.find_element(By.NAME, "username").send_keys(
            self.settings.instagram_username
        )
        password_field = self.driver.find_element(By.NAME, "password")
        password_field.send_keys(self.password)
        password_field.send_keys(Keys.RETURN)
        time.sleep(5)

    def _is_logged_in(self) -> bool:
        assert self.driver is not None
        self.driver.get("https://www.instagram.com/")
        time.sleep(3)
        page = self.driver.page_source
        return 'aria-label="Home"' in page or "profile-tab" in page

    def restart(self) -> None:
        self.log("Restarting the browser…")
        self.stop()
        self.start()

    def stop(self) -> None:
        if self.driver is not None:
            try:
                self.driver.quit()
            except WebDriverException:
                pass
            self.driver = None

    # -- the check itself ------------------------------------------------
    def check(self) -> CheckResult:
        if self.driver is None:
            return CheckResult(ERROR, "Browser is not running.")

        self.driver.get(f"https://www.instagram.com/{self.settings.target_profile}/")
        time.sleep(5)
        page = self.driver.page_source

        if any(marker in page for marker in _BLOCKED_MARKERS):
            return CheckResult(BLOCKED, "Profile page reports it is unavailable.")

        try:
            self.driver.find_element(By.XPATH, "//h2[text()='This Account is Private']")
            return CheckResult(VISIBLE_PRIVATE, "Profile resolves as a private account.")
        except NoSuchElementException:
            pass

        try:
            self.driver.find_element(By.XPATH, "//h1[contains(text(), 'Page Not Found')]")
            return CheckResult(BLOCKED, "Instagram returned Page Not Found.")
        except NoSuchElementException:
            pass

        return CheckResult(VISIBLE_PUBLIC, "Profile page rendered normally.")

    def screenshot(self, path: Path) -> bool:
        if self.driver is None:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            return bool(self.driver.save_screenshot(str(path)))
        except WebDriverException:
            return False


class AnonymousChecker:
    """Logged-out check: fetch the public page and hash the avatar."""

    supports_screenshots = False

    def __init__(
        self,
        settings: config.Settings,
        password: str = "",
        log: Callable[[str], None] | None = None,
    ):
        self.settings = settings
        self.log = log or (lambda _msg: None)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            random.choice(settings.user_agents)
            if settings.user_agents
            else config.DEFAULT_USER_AGENTS[0]
        )

    def start(self) -> None:
        self.log("Anonymous mode: no login, public page only.")

    def restart(self) -> None:
        if self.settings.rotate_user_agent and self.settings.user_agents:
            self.session.headers["User-Agent"] = random.choice(self.settings.user_agents)

    def stop(self) -> None:
        self.session.close()

    def check(self) -> CheckResult:
        url = f"https://www.instagram.com/{self.settings.target_profile}/"
        try:
            response = self.session.get(url, timeout=15)
        except requests.RequestException as exc:
            return CheckResult(ERROR, str(exc))

        if response.status_code == 404 or any(
            marker in response.text for marker in _BLOCKED_MARKERS
        ):
            return CheckResult(BLOCKED, "Public page is unavailable.")

        soup = BeautifulSoup(response.text, "html.parser")
        og_image = soup.find("meta", property="og:image")
        if not og_image or not og_image.get("content"):
            return CheckResult(BLOCKED, "No profile image in the page metadata.")

        return CheckResult(
            VISIBLE_PUBLIC,
            "Public page exposes profile metadata.",
            fingerprint=self._hash_image(og_image["content"]),
        )

    def _hash_image(self, image_url: str) -> str:
        try:
            data = self.session.get(image_url, timeout=15).content
        except requests.RequestException:
            return ""
        return hashlib.sha256(data).hexdigest()[:16]

    def screenshot(self, path: Path) -> bool:
        return False


def has_saved_session(settings: config.Settings) -> bool:
    """True when a browser profile exists for this account."""
    session = settings.session_dir
    return session.is_dir() and any(session.iterdir())


def forget_session(settings: config.Settings) -> bool:
    """Delete the saved session so the next run signs in fresh.

    The escape hatch for a session Instagram has invalidated: without it a bad
    cookie jar would keep failing with no way out from the UI.
    """
    session = settings.session_dir
    if not session.is_dir():
        return False
    shutil.rmtree(session, ignore_errors=True)
    return not session.exists()


def build(settings: config.Settings, password: str, log: Callable[[str], None]):
    if settings.check_mode == config.CHECK_MODE_ANONYMOUS:
        return AnonymousChecker(settings, password, log)
    return BrowserChecker(settings, password, log)
