# Roadmap

Open work, roughly in the order worth doing it. Nothing here is committed to —
it's a list of what would actually improve the app, with the reasoning kept so
future-you doesn't have to re-derive it.

---

## Done

- [x] **Reuse the login session between runs** — the app keeps Instagram's
  cookies in its own browser profile (`~/Library/Application Support/Unblock
  Tracker/sessions/<account>/`) and reuses them, instead of signing in on every
  start and every mid-run browser restart. Repeated automated sign-ins were the
  biggest detection risk in the design. Toggle plus a *Forget saved session*
  button in Settings.

- [x] **Track more than reachability** — counts, follower membership and
  relationship flags, all as diffs between persisted snapshots
  (`signals.py`). Markup knowledge is isolated in pure parsers
  (`parsing.py`) so the fragile half is fixture-testable.
- [x] **Classify pages with a pure function** — `checker.classify` is separate
  from fetching, so the verdict is fixture-testable. Caught a false positive
  along the way: a login page carries none of the "unavailable" markers, so an
  expired session used to read as a visible profile and would have announced an
  unblock that never happened. It is now an explicit error.
- [x] **Explicit waits instead of fixed sleeps** — `WebDriverWait` on real
  conditions; `page_timeout_seconds` replaces the hard-coded 3s/5s pauses.
- [x] **Per-signal notification toggles** — counts are recorded but silent by
  default; membership and relationship changes alert.
- [x] **Back off after failures** — the wait doubles while checks keep failing,
  up to a ceiling. Rate limiting is the usual cause and hammering makes it worse.
- [x] **Watch several profiles in one run** — `Settings.watchlist`; the engine
  cycles targets and keeps per-target history. `stop_on_unblock` applies only
  to a lone target, since stopping would abandon the others.

---

## Next

### 0. Validate the new scrapers against real pages
`parse_counts` and `parse_handles` are pinned by fixtures I wrote, not by real
Instagram output. The meta-description path is the most likely to hold; the
follower-dialog scroller (`BrowserChecker._scroll_dialog`) is the least. Save
real pages as fixtures the first time you run this for real, and treat the
current selectors as a starting point.

### 1. Say something useful when the target is already visible
Starting a run against an already-visible profile stops immediately with
**zero** events, notifications and CSV rows — verified. It is defensible
(nothing *changed*) but reads as a broken run. Either record a baseline event
or say plainly "already visible — nothing to wait for".

---

## Later

### Run unattended
The real use case is waiting days or weeks, but the app has to stay open to do
it. A menu-bar item, or a launchd agent driving the engine headlessly, fits the
job far better than a window you must not close. `MonitorEngine` has no Qt
dependency, so a headless runner is mostly wiring.

### Watch more than one profile
Currently one target per install. The engine is per-`Settings`, so multiple
targets means either multiple engines or a rework of the run loop.

### Throttle notifications
A flapping status will send an alert per flip. A minimum gap between messages,
or a "quiet after N alerts" rule, would stop that.

### Continuous integration
109 tests that nothing runs automatically. A GitHub Action on push is ten
minutes of work and worth it if this repo is ever published.

---

## Considered and rejected

- **Code signing / notarisation** — irrelevant for a personal build; the app is
  ad-hoc signed and launches fine locally. Only worth it if distributed.
- **Shrinking the 116 MB bundle** — it is almost entirely PySide6. The obvious
  excludes are already in `build_app.sh`; further effort buys little.
- **Leaning harder on the proxy pool** — free public proxy lists are unreliable
  enough that they mostly produce failed checks, and routing an Instagram login
  through an anonymous third party is a poor trade. It stays off by default and
  should probably be removed rather than improved.

---

## Known limits (not bugs, not fixable here)

- **2FA cannot be completed** in logged-in mode. Anonymous mode or an account
  without 2FA are the only options.
- **"Blocked" is an inference.** A deactivated, renamed or deleted account
  looks identical to a block. No amount of code changes that.
- **Instagram's terms do not permit automated access.** An account making
  regular scripted logins can be rate-limited, challenged or disabled. Session
  reuse reduces the exposure; it does not remove it.
