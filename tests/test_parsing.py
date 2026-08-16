"""The fragile half: interpreting Instagram's markup.

Fetching a page needs a real account and cannot be tested here. Parsing one
can, so every piece of markup knowledge lives in pure functions and is pinned
down by fixtures. When Instagram changes its markup, these tests are what tell
you — instead of the app silently reporting nonsense.
"""

from __future__ import annotations

import pytest

from unblock_tracker import parsing

META = (
    '<html><head><meta name="description" content="{content}"></head>'
    "<body></body></html>"
)


def page(content: str) -> str:
    return META.format(content=content)


# ----------------------------------------------------------------------
# Numbers
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234", 1234),
        ("1,234", 1234),
        ("12.3K", 12_300),
        ("12.3k", 12_300),
        ("4M", 4_000_000),
        ("1.5m", 1_500_000),
        ("2B", 2_000_000_000),
        ("0", 0),
        ("  87  ", 87),
        ("1\xa0234", 1234),  # non-breaking space
    ],
)
def test_compact_numbers(raw, expected):
    assert parsing.parse_compact_number(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "abc", "K", "--"])
def test_non_numbers_return_none(raw):
    assert parsing.parse_compact_number(raw) is None


# ----------------------------------------------------------------------
# Counts
# ----------------------------------------------------------------------
def test_counts_from_the_meta_description():
    html = page(
        "1,234 Followers, 567 Following, 89 Posts - See Instagram photos "
        "and videos from Someone (@someone)"
    )
    assert parsing.parse_counts(html) == {
        "followers": 1234,
        "following": 567,
        "posts": 89,
    }


def test_counts_handle_rounded_forms():
    html = page("12.3K Followers, 1,001 Following, 2 Posts - See Instagram")
    counts = parsing.parse_counts(html)
    assert counts["followers"] == 12_300
    assert counts["following"] == 1001
    assert counts["posts"] == 2


def test_singular_wording_still_parses():
    html = page("1 Follower, 1 Following, 1 Post - See Instagram")
    assert parsing.parse_counts(html) == {
        "followers": 1,
        "following": 1,
        "posts": 1,
    }


def test_exact_json_counts_win_over_the_rounded_description():
    """The meta description rounds; the embedded payload does not."""
    html = page("12.3K Followers, 500 Following, 10 Posts - See Instagram")
    html += '<script>{"edge_followed_by":{"count":12345}}</script>'
    counts = parsing.parse_counts(html)
    assert counts["followers"] == 12345, "should prefer the exact figure"
    assert counts["following"] == 500


def test_counts_from_json_alone():
    html = (
        '<html><script>{"edge_followed_by":{"count":42},'
        '"edge_follow":{"count":7},'
        '"edge_owner_to_timeline_media":{"count":3}}</script></html>'
    )
    assert parsing.parse_counts(html) == {
        "followers": 42,
        "following": 7,
        "posts": 3,
    }


def test_a_page_without_counts_yields_nothing_rather_than_zeros():
    """Zeros would read as "lost all followers" — silence is the safe answer."""
    assert parsing.parse_counts("<html><body>nothing here</body></html>") == {}
    assert parsing.parse_counts(page("Log in to Instagram")) == {}


def test_partial_matches_do_not_invent_values():
    assert "posts" not in parsing.parse_counts(page("1,234 Followers only"))


# ----------------------------------------------------------------------
# Flags
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('{"is_private":true}', True),
        ('{"is_private":false}', False),
        ("<h2>This Account is Private</h2>", True),
        ("<html>ordinary page</html>", None),
    ],
)
def test_private_detection(html, expected):
    assert parsing.parse_is_private(html) is expected


@pytest.mark.parametrize(
    ("html", "expected"),
    [('{"is_verified":true}', True), ('{"is_verified":false}', False), ("x", None)],
)
def test_verified_detection(html, expected):
    assert parsing.parse_is_verified(html) is expected


def test_full_name_is_unescaped():
    assert parsing.parse_full_name('{"full_name":"Jos\\u00e9"}') == "José"
    assert parsing.parse_full_name("<html></html>") is None


# ----------------------------------------------------------------------
# Handle lists
# ----------------------------------------------------------------------
def test_handles_are_extracted_in_order_without_duplicates():
    html = """
      <a href="/alpha/">Alpha</a>
      <a href="/beta/">Beta</a>
      <a href="/alpha/">Alpha again</a>
      <a href="/gamma">Gamma</a>
    """
    assert parsing.parse_handles(html) == ["alpha", "beta", "gamma"]


def test_navigation_paths_are_not_mistaken_for_people():
    html = """
      <a href="/explore/">Explore</a>
      <a href="/reels/">Reels</a>
      <a href="/direct/">Direct</a>
      <a href="/accounts/">Accounts</a>
      <a href="/p/">Post</a>
      <a href="/real_person/">A person</a>
    """
    assert parsing.parse_handles(html) == ["real_person"]


def test_handles_allow_dots_and_underscores():
    html = '<a href="/first.last/">x</a><a href="/some_one/">y</a>'
    assert parsing.parse_handles(html) == ["first.last", "some_one"]


def test_no_links_means_no_handles():
    assert parsing.parse_handles("<div>nothing</div>") == []


# ----------------------------------------------------------------------
# Relationship signals
# ----------------------------------------------------------------------
def test_close_friends_detected_when_marked():
    assert parsing.parse_close_friends('<span>Close Friends</span>') is True


def test_close_friends_absent_is_none_not_false():
    """A failed scrape must not read as "removed from close friends"."""
    assert parsing.parse_close_friends("<html>unrelated</html>") is None


def test_close_friends_false_only_with_a_positive_signal():
    assert parsing.parse_close_friends('<div class="story-ring"></div>') is False


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<div>You're Restricted</div>", True),
        ('{"restricted_by_viewer":false}', False),
        ("<html>nothing</html>", None),
    ],
)
def test_restricted_detection(html, expected):
    assert parsing.parse_restricted(html) is expected
