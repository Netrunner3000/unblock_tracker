"""Snapshots and the diffs between them.

Every tracking feature reduces to the same question: what changed since last
time? Counts (followers, following, posts), set membership (who unfollowed)
and relationship flags (close friends, restricted) all fit that shape, so one
mechanism serves all of them instead of three parallel ones.

Snapshots persist to disk, because a follower diff is worthless if it resets
every time the app restarts.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

# Human-readable names for the things we track.
LABELS = {
    "followers": "followers",
    "following": "following",
    "posts": "posts",
    "close_friends": "close friends",
    "restricted": "restricted",
    "private": "private account",
    "verified": "verified",
}


def label(name: str) -> str:
    return LABELS.get(name, name)


@dataclass
class Snapshot:
    """What one check observed, beyond simple reachability."""

    counts: dict[str, int] = field(default_factory=dict)
    flags: dict[str, bool] = field(default_factory=dict)
    members: dict[str, list[str]] = field(default_factory=dict)
    taken_at: str = ""

    def is_empty(self) -> bool:
        return not (self.counts or self.flags or self.members)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: dict) -> Snapshot:
        return cls(
            counts={k: int(v) for k, v in (raw.get("counts") or {}).items()},
            flags={k: bool(v) for k, v in (raw.get("flags") or {}).items()},
            members={
                k: list(v) for k, v in (raw.get("members") or {}).items()
            },
            taken_at=raw.get("taken_at", ""),
        )


@dataclass
class Change:
    """One difference worth telling the user about."""

    kind: str  # "count" | "flag" | "members"
    name: str  # "followers", "close_friends", …
    detail: str  # human-readable summary
    before: object = None
    after: object = None
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.detail


def _describe_count(name: str, before: int, after: int) -> str:
    delta = after - before
    direction = "+" if delta > 0 else ""
    return f"{label(name)} {before:,} → {after:,} ({direction}{delta:,})"


def diff(previous: Snapshot | None, current: Snapshot) -> list[Change]:
    """What changed between two snapshots.

    A missing value on either side is silence, not a change: an absent signal
    must never be reported as "removed", or a failed scrape would look like
    someone unfollowing you.
    """
    if previous is None:
        return []

    changes: list[Change] = []

    for name, after in current.counts.items():
        before = previous.counts.get(name)
        if before is not None and before != after:
            changes.append(
                Change("count", name, _describe_count(name, before, after), before, after)
            )

    for name, after in current.flags.items():
        before = previous.flags.get(name)
        if before is not None and before != after:
            became = "yes" if after else "no"
            changes.append(
                Change("flag", name, f"{label(name)}: {became}", before, after)
            )

    for name, after_list in current.members.items():
        before_list = previous.members.get(name)
        if before_list is None:
            continue
        before_set, after_set = set(before_list), set(after_list)
        added = sorted(after_set - before_set)
        removed = sorted(before_set - after_set)
        if not added and not removed:
            continue

        parts = []
        if removed:
            parts.append(f"-{len(removed)}")
        if added:
            parts.append(f"+{len(added)}")
        summary = f"{label(name)} {' '.join(parts)}"
        if removed:
            shown = ", ".join(f"@{h}" for h in removed[:5])
            summary += f" — left: {shown}"
            if len(removed) > 5:
                summary += f" and {len(removed) - 5} more"

        changes.append(
            Change("members", name, summary, added=added, removed=removed)
        )

    return changes


class SnapshotStore:
    """Last-seen snapshot per target, persisted as JSON.

    Kept beside the run data rather than in the config: it is observation, not
    preference, and it can grow large once follower lists are involved.
    """

    def __init__(self, path: Path):
        self.path = path

    def _read_all(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def load(self, target: str) -> Snapshot | None:
        raw = self._read_all().get(target)
        return Snapshot.from_json(raw) if raw else None

    def save(self, target: str, snapshot: Snapshot) -> None:
        snapshot.taken_at = snapshot.taken_at or datetime.now().isoformat(
            timespec="seconds"
        )
        everything = self._read_all()
        everything[target] = snapshot.to_json()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(everything, indent=2, sort_keys=True) + "\n")

    def forget(self, target: str) -> bool:
        everything = self._read_all()
        if target not in everything:
            return False
        del everything[target]
        self.path.write_text(json.dumps(everything, indent=2, sort_keys=True) + "\n")
        return True

    def targets(self) -> list[str]:
        return sorted(self._read_all())
