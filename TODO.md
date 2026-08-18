# Unblock Tracker — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)

Full reasoning lives in [ROADMAP.md](ROADMAP.md); this is the checklist view.

---

## v2 — current

- [ ] `P0` `bug` `@me` **Validate the scrapers against real pages.** `parse_counts` and `parse_handles` are pinned by hand-written fixtures, not real Instagram output. Save real pages as fixtures the first time you run this for real; treat the current selectors as a starting point. The follower-dialog scroller (`BrowserChecker._scroll_dialog`) is the least likely to hold.
- [ ] `P1` `bug` `@ai` Starting a run against an already-visible profile ends with zero events, notifications and CSV rows — defensible but reads as a broken run. Record a baseline event or say "already visible — nothing to wait for".
- [x] `P1` `security` `@ai` Reuse the login session between runs — repeated automated sign-ins were the biggest detection risk in the design
- [x] `P1` `bug` `@ai` A login page carries none of the "unavailable" markers, so an expired session read as a visible profile and would have announced an unblock that never happened. Now an explicit error.
- [x] `P2` `feature` `@ai` Track counts, follower membership and relationship flags as diffs between persisted snapshots
- [x] `P2` `bug` `@ai` Explicit `WebDriverWait` conditions instead of fixed 3s/5s sleeps
- [x] `P2` `feature` `@ai` Exponential back-off after failures
- [x] `P2` `feature` `@ai` Watch several profiles in one run

## v3 — later

- [ ] `P2` `feature` `@ai` Run unattended — a menu-bar item or a launchd agent driving the engine headlessly. `MonitorEngine` has no Qt dependency, so this is mostly wiring.
- [ ] `P2` `feature` `@ai` Throttle repeated alerts — a flapping status still sends one alert per flip. Minimum gap, or "quiet after N alerts".
- [ ] `P3` `feature` `@ai` Chart the snapshot history — `snapshots.json` accumulates counts and nothing draws them
- [ ] `P3` `infra` `@ai` CI on push. 209 tests that nothing runs automatically; a GitHub Action is ten minutes of work.

## Known limits — not bugs, not fixable here

- 2FA cannot be completed in logged-in mode. Anonymous mode or an account without 2FA are the only options.
- "Blocked" is an inference. A deactivated, renamed or deleted account looks identical.
- Instagram's terms do not permit automated access. Session reuse reduces exposure; it does not remove it.

## Rejected

- Code signing / notarisation — irrelevant for a personal build
- Shrinking the 116 MB bundle — it is almost entirely PySide6
- Leaning harder on the proxy pool — free proxy lists mostly produce failed checks, and routing a login through an anonymous third party is a poor trade
