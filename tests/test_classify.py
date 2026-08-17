"""What a profile page means — the classification that drives everything.

This was the last untested piece of the project and the most consequential:
getting it wrong either misses an unblock or announces one that never
happened. Fetching a page needs a real account, so `classify` is pure and
these fixtures stand in for Instagram's markup.

The fixtures are approximations written by hand, not captured from Instagram.
Replace them with real saved pages the first time you run this for real.
"""

from __future__ import annotations

import pytest

from unblock_tracker import checker

PROFILE_META = (
    '<meta name="description" content="1,234 Followers, 567 Following, '
    '89 Posts - See Instagram photos and videos from Someone (@someone)">'
)


def public_page() -> str:
    return f"""<html><head>{PROFILE_META}</head><body>
      <header><h2>someone</h2></header>
      <script>{{"edge_followed_by":{{"count":1234}},"is_private":false}}</script>
    </body></html>"""


def private_page() -> str:
    return f"""<html><head>{PROFILE_META}</head><body>
      <h2>This Account is Private</h2>
      <script>{{"is_private":true}}</script>
    </body></html>"""


def unavailable_page() -> str:
    return """<html><body>
      <h2>Sorry, this page isn't available.</h2>
      <p>The link you followed may be broken, or the page may have been removed.</p>
    </body></html>"""


def not_found_page() -> str:
    return "<html><body><h1>Page Not Found</h1></body></html>"


def login_page() -> str:
    return """<html><body>
      <form id="loginForm">
        <input name="username" placeholder="Phone number, username, or email">
        <input name="password" type="password">
      </form>
      <p>Sign up to see photos and videos from friends</p>
    </body></html>"""


# ----------------------------------------------------------------------
# The four ordinary verdicts
# ----------------------------------------------------------------------
def test_a_public_profile_reads_as_visible():
    result = checker.classify(public_page())
    assert result.status == checker.VISIBLE_PUBLIC
    assert checker.is_visible(result.status)


def test_a_private_profile_reads_as_visible_private():
    """Private still means reachable — it is not a block."""
    result = checker.classify(private_page())
    assert result.status == checker.VISIBLE_PRIVATE
    assert checker.is_visible(result.status)


def test_an_unavailable_page_reads_as_blocked():
    result = checker.classify(unavailable_page())
    assert result.status == checker.BLOCKED
    assert not checker.is_visible(result.status)


def test_a_not_found_page_reads_as_blocked():
    assert checker.classify(not_found_page()).status == checker.BLOCKED


def test_a_404_response_reads_as_blocked_whatever_the_body_says():
    assert checker.classify(public_page(), status_code=404).status == checker.BLOCKED


# ----------------------------------------------------------------------
# The dangerous case
# ----------------------------------------------------------------------
def test_the_sign_in_page_is_an_error_not_a_visible_profile():
    """The false positive that matters most.

    An expired session lands on the login page, which carries none of the
    "unavailable" markers. Without an explicit check it reads as a perfectly
    normal profile — and the app announces that you have been unblocked.
    """
    result = checker.classify(login_page())

    assert result.status == checker.ERROR
    assert not checker.is_visible(result.status)
    assert "session" in result.detail.lower()


def test_a_profile_page_is_not_mistaken_for_a_login_wall():
    """Profile pages can carry a sign-in prompt; that must not block the read."""
    page = public_page().replace("</body>", '<div><input name="password"></div></body>')
    assert checker.classify(page).status == checker.VISIBLE_PUBLIC


# ----------------------------------------------------------------------
# Precedence
# ----------------------------------------------------------------------
def test_unavailable_wins_over_a_private_marker():
    page = unavailable_page() + private_page()
    assert checker.classify(page).status == checker.BLOCKED


def test_blocked_verdicts_carry_no_snapshot():
    """Nothing was legitimately observed, so nothing should be recorded."""
    for page in (unavailable_page(), not_found_page(), login_page()):
        assert checker.classify(page).snapshot is None


# ----------------------------------------------------------------------
# Snapshots ride along
# ----------------------------------------------------------------------
def test_a_visible_verdict_carries_the_measurements():
    result = checker.classify(public_page())
    assert result.snapshot is not None
    assert result.snapshot.counts["followers"] == 1234
    assert result.snapshot.counts["following"] == 567
    assert result.snapshot.counts["posts"] == 89
    assert result.snapshot.flags["private"] is False


def test_a_private_profile_still_reports_its_counts():
    result = checker.classify(private_page())
    assert result.snapshot is not None
    assert result.snapshot.counts["followers"] == 1234
    assert result.snapshot.flags["private"] is True


def test_a_bare_page_yields_an_empty_snapshot_not_zeros():
    result = checker.classify("<html><body><div>hi</div></body></html>")
    assert result.status == checker.VISIBLE_PUBLIC
    assert result.snapshot is not None
    assert result.snapshot.counts == {}, "absent counts must not become zeros"


@pytest.mark.parametrize(
    "marker",
    ["Sorry, this page isn't available.", "Sorry, this page isn’t available."],
)
def test_both_apostrophe_forms_are_recognised(marker):
    """Instagram serves a curly apostrophe; a straight one appears in older copy."""
    assert checker.classify(f"<html><body>{marker}</body></html>").status == checker.BLOCKED
