"""Snapshots and diffs — the mechanism every tracking feature runs on."""

from __future__ import annotations

from unblock_tracker import signals
from unblock_tracker.signals import Snapshot, SnapshotStore, diff


def snap(counts=None, flags=None, members=None) -> Snapshot:
    return Snapshot(counts=counts or {}, flags=flags or {}, members=members or {})


# ----------------------------------------------------------------------
# The rule that matters most
# ----------------------------------------------------------------------
def test_the_first_snapshot_reports_nothing():
    """Baselines are not changes."""
    assert diff(None, snap(counts={"followers": 100})) == []


def test_a_missing_signal_is_silence_not_a_change():
    """A failed scrape must never read as "lost every follower"."""
    before = snap(
        counts={"followers": 100, "posts": 10},
        members={"followers": ["a", "b", "c"]},
        flags={"close_friends": True},
    )
    after = snap()  # scrape returned nothing at all

    assert diff(before, after) == []


def test_a_partial_scrape_only_reports_what_it_saw():
    before = snap(counts={"followers": 100, "following": 50, "posts": 10})
    after = snap(counts={"followers": 101})

    changes = diff(before, after)

    assert len(changes) == 1
    assert changes[0].name == "followers"


def test_a_new_signal_appearing_is_not_a_change():
    before = snap(counts={"followers": 100})
    after = snap(counts={"followers": 100, "posts": 5})
    assert diff(before, after) == []


# ----------------------------------------------------------------------
# Counts
# ----------------------------------------------------------------------
def test_a_rising_count_is_described_with_its_delta():
    changes = diff(snap(counts={"followers": 100}), snap(counts={"followers": 137}))
    assert len(changes) == 1
    assert changes[0].kind == "count"
    assert changes[0].before == 100
    assert changes[0].after == 137
    assert "+37" in changes[0].detail


def test_a_falling_count_shows_a_negative_delta():
    changes = diff(snap(counts={"followers": 100}), snap(counts={"followers": 90}))
    assert "-10" in changes[0].detail


def test_an_unchanged_count_is_not_reported():
    assert diff(snap(counts={"followers": 100}), snap(counts={"followers": 100})) == []


def test_large_numbers_are_formatted_readably():
    changes = diff(
        snap(counts={"followers": 1_000_000}), snap(counts={"followers": 1_000_500})
    )
    assert "1,000,000" in changes[0].detail
    assert "1,000,500" in changes[0].detail


# ----------------------------------------------------------------------
# Membership — the follower diff
# ----------------------------------------------------------------------
def test_someone_unfollowing_is_named():
    changes = diff(
        snap(members={"followers": ["alice", "bob", "carol"]}),
        snap(members={"followers": ["alice", "carol"]}),
    )

    assert len(changes) == 1
    change = changes[0]
    assert change.kind == "members"
    assert change.removed == ["bob"]
    assert change.added == []
    assert "@bob" in change.detail


def test_new_followers_are_counted():
    changes = diff(
        snap(members={"followers": ["alice"]}),
        snap(members={"followers": ["alice", "dave", "erin"]}),
    )
    assert changes[0].added == ["dave", "erin"]
    assert "+2" in changes[0].detail


def test_simultaneous_gains_and_losses_are_both_reported():
    changes = diff(
        snap(members={"followers": ["alice", "bob"]}),
        snap(members={"followers": ["alice", "carol"]}),
    )
    change = changes[0]
    assert change.removed == ["bob"]
    assert change.added == ["carol"]
    assert "-1" in change.detail and "+1" in change.detail


def test_reordering_is_not_a_change():
    """Instagram returns these lists in arbitrary order."""
    assert diff(
        snap(members={"followers": ["alice", "bob", "carol"]}),
        snap(members={"followers": ["carol", "alice", "bob"]}),
    ) == []


def test_a_long_departure_list_is_summarised():
    before = [f"user{n}" for n in range(20)]
    changes = diff(
        snap(members={"followers": before}), snap(members={"followers": before[:5]})
    )
    detail = changes[0].detail
    assert "-15" in detail
    assert "and 10 more" in detail, detail
    assert len(changes[0].removed) == 15


# ----------------------------------------------------------------------
# Flags
# ----------------------------------------------------------------------
def test_flag_changes_are_reported_both_ways():
    on = diff(snap(flags={"close_friends": False}), snap(flags={"close_friends": True}))
    off = diff(snap(flags={"close_friends": True}), snap(flags={"close_friends": False}))

    assert on[0].after is True and "yes" in on[0].detail
    assert off[0].after is False and "no" in off[0].detail


def test_an_unchanged_flag_is_silent():
    assert diff(snap(flags={"restricted": True}), snap(flags={"restricted": True})) == []


# ----------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------
def test_snapshots_survive_a_restart(tmp_path):
    """A follower diff is worthless if it resets every launch."""
    store = SnapshotStore(tmp_path / "snapshots.json")
    original = snap(counts={"followers": 10}, members={"followers": ["alice"]})
    store.save("someone", original)

    reloaded = SnapshotStore(tmp_path / "snapshots.json").load("someone")

    assert reloaded is not None
    assert reloaded.counts == {"followers": 10}
    assert reloaded.members == {"followers": ["alice"]}
    assert reloaded.taken_at, "a saved snapshot should be stamped"


def test_targets_are_stored_separately(tmp_path):
    store = SnapshotStore(tmp_path / "s.json")
    store.save("alice", snap(counts={"followers": 1}))
    store.save("bob", snap(counts={"followers": 2}))

    assert store.load("alice").counts["followers"] == 1
    assert store.load("bob").counts["followers"] == 2
    assert store.targets() == ["alice", "bob"]


def test_an_unknown_target_loads_as_none(tmp_path):
    assert SnapshotStore(tmp_path / "s.json").load("nobody") is None


def test_a_corrupt_store_does_not_crash(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{ not json")
    store = SnapshotStore(path)

    assert store.load("anyone") is None
    store.save("anyone", snap(counts={"followers": 1}))  # must recover
    assert store.load("anyone").counts["followers"] == 1


def test_forgetting_a_target_removes_only_that_one(tmp_path):
    store = SnapshotStore(tmp_path / "s.json")
    store.save("alice", snap(counts={"followers": 1}))
    store.save("bob", snap(counts={"followers": 2}))

    assert store.forget("alice") is True
    assert store.load("alice") is None
    assert store.load("bob") is not None
    assert store.forget("nobody") is False


def test_labels_are_human_readable():
    assert signals.label("close_friends") == "close friends"
    assert signals.label("followers") == "followers"
    assert signals.label("unknown_thing") == "unknown_thing"
