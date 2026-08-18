# Unblock Tracker — Suggestions

Status: `IDEA` · `CONSIDERING` · `PLANNED` · `DONE` · `REJECTED`

---

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 1 | Headless runner behind a menu-bar item — the real use case is waiting days, and the window must currently stay open | feature | L | PLANNED |
| 2 | Alert throttling: minimum gap between messages, or quiet-after-N | feature | S | PLANNED |
| 3 | Baseline event when the target is already visible, so a run never looks broken | bug | XS | PLANNED |
| 4 | Chart `snapshots.json` over time — the data layer already exists | feature | M | CONSIDERING |
| 5 | GitHub Action running the 209 tests on push | infra | XS | CONSIDERING |
| 6 | Real-page fixtures captured on first live run, replacing the hand-written ones | testing | S | PLANNED |
| 7 | Export the event log as a timeline image worth keeping | design | S | IDEA |
| 8 | Per-target notification profiles, rather than one global set of toggles | feature | M | IDEA |

## Done

| Suggestion | When |
|---|---|
| Session reuse with a per-account browser profile, plus a *Forget saved session* button | Aug 2026 |
| Pure `checker.classify` separated from fetching | Aug 2026 |
| Signal diffing in `signals.py`, parsers isolated in `parsing.py` | Aug 2026 |
| Per-signal notification toggles | Aug 2026 |
| Multi-target watchlist | Aug 2026 |

## Rejected

| Suggestion | Why |
|---|---|
| Notarisation | Personal build, ad-hoc signed, launches fine |
| Bundle slimming | Almost entirely PySide6; obvious excludes already applied |
| Proxy pool | Unreliable, and a poor trade for an authenticated session |
