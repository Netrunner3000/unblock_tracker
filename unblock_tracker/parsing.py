"""Pure parsers for Instagram profile markup.

Everything here takes a string and returns data — no network, no browser. That
is deliberate: fetching a page cannot be tested without a real account, but
*interpreting* one can, so all the fragile knowledge about Instagram's markup
lives in functions that fixtures can pin down.

When Instagram changes its markup, this is the file that breaks and the file
whose tests tell you.
"""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

# "1,234 Followers, 567 Following, 89 Posts - See Instagram photos and video..."
# The meta description has survived many redesigns and is present logged-out,
# which makes it the most reliable source of counts we have.
_META_COUNTS = re.compile(
    r"([\d,.KMkm\s]+)\s+Followers?,\s*"
    r"([\d,.KMkm\s]+)\s+Following,\s*"
    r"([\d,.KMkm\s]+)\s+Posts?",
    re.IGNORECASE,
)

_SUFFIXES = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def parse_compact_number(raw: str) -> int | None:
    """Turn "1,234", "12.3K" or "4M" into an int. None if it isn't a number."""
    text = raw.strip().replace(",", "").replace(" ", "").replace("\xa0", "")
    text = text.replace(" ", "")
    if not text:
        return None

    multiplier = 1
    if text[-1].lower() in _SUFFIXES:
        multiplier = _SUFFIXES[text[-1].lower()]
        text = text[:-1]

    try:
        value = float(text)
    except ValueError:
        return None
    return int(value * multiplier)


def parse_counts(html: str) -> dict[str, int]:
    """Extract follower / following / post counts from a profile page.

    Returns only the keys it could actually find, so a partial parse degrades
    to fewer signals rather than to wrong ones.
    """
    counts: dict[str, int] = {}
    soup = BeautifulSoup(html, "html.parser")

    meta = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", property="og:description"
    )
    content = meta.get("content", "") if meta else ""

    match = _META_COUNTS.search(content)
    if match:
        for key, raw in zip(
            ("followers", "following", "posts"), match.groups(), strict=True
        ):
            value = parse_compact_number(raw)
            if value is not None:
                counts[key] = value

    # Some responses carry a JSON blob instead; prefer it when present since
    # it holds exact numbers rather than the rounded "12.3K" form.
    for exact_key, blob_key in (
        ("followers", "edge_followed_by"),
        ("following", "edge_follow"),
        ("posts", "edge_owner_to_timeline_media"),
    ):
        value = _from_json_blob(html, blob_key)
        if value is not None:
            counts[exact_key] = value

    return counts


def _from_json_blob(html: str, key: str) -> int | None:
    """Pull `{"<key>": {"count": N}}` out of an embedded JSON payload."""
    match = re.search(rf'"{re.escape(key)}"\s*:\s*\{{\s*"count"\s*:\s*(\d+)', html)
    return int(match.group(1)) if match else None


def parse_is_private(html: str) -> bool | None:
    """True/False when the page states privacy, None when it doesn't say."""
    match = re.search(r'"is_private"\s*:\s*(true|false)', html)
    if match:
        return match.group(1) == "true"
    if "This Account is Private" in html or "This account is private" in html:
        return True
    return None


def parse_is_verified(html: str) -> bool | None:
    match = re.search(r'"is_verified"\s*:\s*(true|false)', html)
    return match.group(1) == "true" if match else None


def parse_full_name(html: str) -> str | None:
    match = re.search(r'"full_name"\s*:\s*"([^"]*)"', html)
    if match:
        try:
            return json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            return match.group(1)
    return None


# ----------------------------------------------------------------------
# Handle lists (follower / following dialogs)
# ----------------------------------------------------------------------
_PROFILE_HREF = re.compile(r'href="/([A-Za-z0-9._]{1,30})/?"')

# Paths that look like handles but aren't people.
_NOT_HANDLES = {
    "explore", "reels", "direct", "stories", "accounts", "p", "tv", "about",
    "legal", "privacy", "terms", "developer", "directory", "web", "api",
    "challenge", "emails", "session", "graphql", "ajax", "static", "your_activity",
}


def parse_handles(html: str) -> list[str]:
    """Extract profile handles from a follower/following list fragment.

    Order is preserved and duplicates removed, so the caller can tell "first
    page" from "second page" if it wants to.
    """
    seen: dict[str, None] = {}
    for handle in _PROFILE_HREF.findall(html):
        lowered = handle.lower()
        if lowered in _NOT_HANDLES or lowered.startswith("_u/"):
            continue
        seen.setdefault(handle, None)
    return list(seen)


# ----------------------------------------------------------------------
# Relationship signals
# ----------------------------------------------------------------------
def looks_like_login_wall(html: str) -> bool:
    """True when this is Instagram's sign-in page rather than a profile.

    This matters more than it looks. If a session expires mid-run, navigating
    to a profile lands on the login page — which carries none of the "not
    available" markers, so a naive check reads it as a perfectly visible
    profile and announces that you have been unblocked.
    """
    signals = (
        'name="password"',
        "loginForm",
        "Sign up to see photos and videos from friends",
        "Phone number, username, or email",
    )
    if not any(marker in html for marker in signals):
        return False

    # A profile page can legitimately contain a login prompt in a modal, so
    # require the absence of profile content before calling it a wall.
    profile_markers = ('"edge_followed_by"', 'property="og:description"', "Followers")
    return not any(marker in html for marker in profile_markers)


def parse_close_friends(html: str) -> bool | None:
    """Whether a visible story is a Close Friends story.

    Instagram marks these with a green ring and a badge. There is no stable
    attribute for it, so this looks for the label text Instagram renders for
    accessibility. Returns None when nothing conclusive is present — an
    absent signal must not be reported as "removed from close friends".
    """
    for marker in ("Close Friends", "close_friends", "Close friends"):
        if marker in html:
            return True
    if "story-ring" in html or "Story unavailable" in html:
        return False
    return None


def parse_restricted(html: str) -> bool | None:
    """Whether the viewer appears to be restricted by this account.

    The explicit field is checked before the text markers: the substring
    "restricted_by_viewer" appears in both the true and false forms, so
    matching it as a marker would report a restriction that isn't there.
    """
    match = re.search(r'"restricted_by_viewer"\s*:\s*(true|false)', html)
    if match:
        return match.group(1) == "true"

    for marker in ("You're Restricted", "You are restricted", "You are Restricted"):
        if marker in html:
            return True
    return None
