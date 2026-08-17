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
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from . import config, parsing
from .proxies import ProxyPool
from .signals import Snapshot

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
    # Everything measurable the check happened to see. Empty is normal and
    # means "not observed" — never "zero". See signals.diff.
    snapshot: Snapshot | None = None


class LoginFailed(RuntimeError):
    pass


def classify(html: str, status_code: int | None = None) -> CheckResult:
    """Decide what a profile page says, from its markup alone.

    Pure on purpose: fetching a page needs a real account, but interpreting one
    does not, so this is the piece fixtures can pin down. Order matters —
    "unavailable" and "not found" are checked before anything that would read
    the page as a normal profile.
    """
    if status_code == 404:
        return CheckResult(BLOCKED, "Instagram returned 404.")

    if any(marker in html for marker in _BLOCKED_MARKERS):
        return CheckResult(BLOCKED, "Profile page reports it is unavailable.")

    if "Page Not Found" in html:
        return CheckResult(BLOCKED, "Instagram returned Page Not Found.")

    # Must come before the visible verdicts: a login page carries none of the
    # markers above, so without this an expired session reads as "unblocked".
    if parsing.looks_like_login_wall(html):
        return CheckResult(ERROR, "Got the sign-in page — the session is not valid.")

    snapshot = snapshot_from_page(html)

    if parsing.parse_is_private(html) is True:
        return CheckResult(
            VISIBLE_PRIVATE, "Profile resolves as a private account.", snapshot=snapshot
        )

    return CheckResult(
        VISIBLE_PUBLIC, "Profile page rendered normally.", snapshot=snapshot
    )


def snapshot_from_page(html: str) -> Snapshot:
    """Everything measurable on a profile page.

    Only keys that were actually found are included. A signal that could not
    be read is left out rather than defaulted, because `signals.diff` treats a
    missing key as silence and a present one as fact — defaulting to zero
    would announce that someone lost all their followers.
    """
    snapshot = Snapshot(counts=parsing.parse_counts(html))

    for name, value in (
        ("private", parsing.parse_is_private(html)),
        ("verified", parsing.parse_is_verified(html)),
        ("restricted", parsing.parse_restricted(html)),
        ("close_friends", parsing.parse_close_friends(html)),
    ):
        if value is not None:
            snapshot.flags[name] = value

    return snapshot


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

    # -- waiting ---------------------------------------------------------
    def _await_page(self) -> None:
        """Wait for the document to finish rendering.

        Replaces a fixed sleep, which was simultaneously too short on a slow
        connection and wasted time on a fast one. Timing out is not an error:
        the page is classified from whatever did load.
        """
        try:
            WebDriverWait(self.driver, self.settings.page_timeout_seconds).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except WebDriverException:
            return

    def _await_element(self, by, value: str) -> bool:
        try:
            WebDriverWait(self.driver, self.settings.page_timeout_seconds).until(
                EC.presence_of_element_located((by, value))
            )
            return True
        except WebDriverException:
            return False

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
        if not self._await_element(By.NAME, "password"):
            raise LoginFailed("The sign-in form never appeared.")

        self.driver.find_element(By.NAME, "username").send_keys(
            self.settings.instagram_username
        )
        password_field = self.driver.find_element(By.NAME, "password")
        password_field.send_keys(self.password)
        password_field.send_keys(Keys.RETURN)

        # Submitting navigates away; waiting for the form to go is a real
        # signal that something happened, unlike a fixed pause.
        try:
            WebDriverWait(self.driver, self.settings.page_timeout_seconds).until(
                EC.staleness_of(password_field)
            )
        except WebDriverException:
            pass
        self._await_page()

    def _is_logged_in(self) -> bool:
        assert self.driver is not None
        self.driver.get("https://www.instagram.com/")
        self._await_page()
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
    def check(self, target: str = "") -> CheckResult:
        if self.driver is None:
            return CheckResult(ERROR, "Browser is not running.")

        target = target or self.settings.target_profile
        self.driver.get(f"https://www.instagram.com/{target}/")
        self._await_page()
        return classify(self.driver.page_source)

    def screenshot(self, path: Path) -> bool:
        if self.driver is None:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            return bool(self.driver.save_screenshot(str(path)))
        except WebDriverException:
            return False

    # -- follower / following lists --------------------------------------
    def collect_handles(self, account: str, which: str) -> list[str] | None:
        """Scrape one of the follower/following dialogs.

        `which` is "followers" or "following". Returns None when the list
        could not be read at all — the caller must not treat that as an empty
        list, or every follower would look like they left.

        Only usable on an account whose lists you can open, which in practice
        means your own or a public one.
        """
        if self.driver is None:
            return None

        try:
            self.driver.get(f"https://www.instagram.com/{account}/{which}/")
            self._await_element(By.CSS_SELECTOR, "div[role=dialog]")
            handles = self._scroll_dialog()
        except WebDriverException as exc:
            self.log(f"Could not read {which} for @{account}: {exc}")
            return None

        if not handles:
            # Genuinely-zero and could-not-read are indistinguishable from
            # here, so report the safe one.
            self.log(f"No {which} rows found for @{account} — treating as unread.")
            return None
        return handles

    def _scroll_dialog(self, max_scrolls: int = 60) -> list[str]:
        """Scroll the follower dialog until it stops producing new handles."""
        assert self.driver is not None
        seen: dict[str, None] = {}
        stable = 0

        for _ in range(max_scrolls):
            for handle in parsing.parse_handles(self.driver.page_source):
                seen.setdefault(handle, None)

            before = len(seen)
            try:
                self.driver.execute_script(
                    "const d=document.querySelector('div[role=dialog]');"
                    "if(d){const s=d.querySelector('div[style*=overflow]')||d;"
                    "s.scrollTop=s.scrollHeight;}"
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
            except WebDriverException:
                break
            time.sleep(1.5)

            for handle in parsing.parse_handles(self.driver.page_source):
                seen.setdefault(handle, None)

            stable = stable + 1 if len(seen) == before else 0
            if stable >= 3:  # three quiet rounds means the list has ended
                break

        return list(seen)


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

    def check(self, target: str = "") -> CheckResult:
        target = target or self.settings.target_profile
        url = f"https://www.instagram.com/{target}/"
        try:
            response = self.session.get(url, timeout=15)
        except requests.RequestException as exc:
            return CheckResult(ERROR, str(exc))

        verdict = classify(response.text, response.status_code)
        if not is_visible(verdict.status):
            return verdict

        soup = BeautifulSoup(response.text, "html.parser")
        og_image = soup.find("meta", property="og:image")
        if not og_image or not og_image.get("content"):
            return CheckResult(BLOCKED, "No profile image in the page metadata.")

        verdict.fingerprint = self._hash_image(og_image["content"])
        return verdict

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
