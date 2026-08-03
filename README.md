# Unblock Tracker

A PySide6 desktop app that watches whether a given Instagram profile is
reachable from your account, records every status change, and can notify you
over Telegram or Pushbullet when it changes.

It replaces the pile of near-identical monitor scripts this project used to be.
Every variant's behaviour survives as a setting: logged-in or anonymous checks,
user-agent rotation, proxy pooling, screenshots, CSV history, quiet hours.

## Nothing is hard-coded

No account name, target handle, chat ID or token appears anywhere in this
repository. A fresh clone opens on the Settings tab with empty fields and
refuses to start until you fill them in.

- **Non-secret settings** → `config.json` (git-ignored; `config.example.json` is
  the committed template, and every identity field in it is blank).
- **Secrets** — Instagram password, Telegram bot token, Pushbullet token →
  **macOS Keychain**, under the service `unblock_tracker`, keyed by account
  name. They are never written to a file, so there is nothing to accidentally
  commit or sync to a cloud backup.

## Setup

```bash
uv venv && uv pip install -r requirements.txt
```

Logged-in mode drives a real browser through Selenium. Selenium Manager fetches
a matching driver on its own; set explicit paths in Settings only if you want a
specific browser (for example Brave) or a pinned `chromedriver`.

## Running

From source, while working on it:

```bash
.venv/bin/python main.py
```

Or build a standalone Mac app and install it:

```bash
./build_app.sh --install
```

`build_app.sh` `cd`s to its own folder, so it works from any directory — only
the `./` prefix requires you to be here. Once installed it's in Launchpad and
Spotlight as **Unblock Tracker**. Without `--install` the app is left in
`dist/`, which every build deletes and recreates, so install it rather than
launching from there.

## The user guide

[`docs/GUIDE.md`](docs/GUIDE.md) is the end-user walkthrough: filling in
settings, what each status means, tuning the schedule, and troubleshooting.

It is reachable in the app from the **How to use** button in the tab bar
corner (or ⌘?), which renders that same file — one copy of the text, readable
both in-app and on disk. `build_app.sh` bundles it, and `--selftest` fails if a
build ships without it.

## First run

The app opens on **Settings** with every field blank. Fill in your username and
password, the handle to watch, and a notification channel if you want one, then
**Save settings**. Until that's done, Start refuses and names exactly what's
missing.

Two things worth knowing:

- macOS prompts for **Keychain access** the first time a secret is read or
  written. Choose *Always Allow* or it asks on every launch.
- The packaged app and the source version keep **separate** settings —
  `~/Library/Application Support/Unblock Tracker/` versus this folder — so
  configuring one does not populate the other. Keychain secrets are shared.

## The three tabs

**Settings** — your account, the profile to watch, notification channel, pacing,
browser and proxy behaviour. Save writes `config.json` and pushes the secrets
into the Keychain. *Send test notification* verifies a channel before you rely
on it.

**Monitor** — Start/Stop, the current status, and a live activity log. Stop
takes effect immediately, even in the middle of a wait.

**Events** — every recorded status change with its screenshot. Replaces the old
Flask dashboard.

## Check modes

| | Logged in | Anonymous |
|---|---|---|
| Credentials | required | none |
| Sees private accounts | yes | no |
| Screenshots | yes | no |
| Detects avatar changes | no | yes |
| Detection risk | higher | lower |

Logged-in mode is the accurate one: only a logged-in session can tell "blocked"
apart from "private". Anonymous mode fetches the public page and hashes the
avatar, which is enough to spot a profile reappearing.

## Where your data lives

| | Running from source | Packaged app |
|---|---|---|
| Settings | `config.json` here | `~/Library/Application Support/Unblock Tracker/config.json` |
| Run output | `runs/` here | `…/Unblock Tracker/runs/` |
| Secrets | macOS Keychain | macOS Keychain |

A bundle must never write inside itself — that breaks the code signature, and
every reinstall would wipe your settings — which is why the frozen build
relocates. The run folder is configurable in Settings either way, and contains:

- `events.csv` — timestamped status changes
- `monitor.log` — full activity log
- `screenshots/` — one capture per status change

All of it is git-ignored: it records activity about the monitored account and
should stay local.

## Tests

```bash
uv pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

69 tests, about two seconds. Nothing in the suite touches the network, a
browser, Instagram, or your real Keychain.

- **`tests/fakes.py`** replaces `checker.build` and `notifiers.build`, the only
  two places the engine reaches outside itself, so the whole monitor loop runs
  against a scripted sequence of results.
- **`tests/conftest.py`** swaps the Keychain for an in-memory backend via an
  autouse fixture, and `test_secrets.py` asserts that swap actually happened.
  That guard is not paranoia: with the fixture disabled the secrets tests
  happily write to the real login Keychain.
- Qt runs offscreen, so the UI tests need no display.

Engine tests run on a worker thread with a timeout, so a loop that fails to
terminate fails the test instead of hanging the suite.

## Verifying a build

```bash
"dist/Unblock Tracker.app/Contents/MacOS/Unblock Tracker" --selftest
```

Confirms the icon shipped, the config path lands outside the bundle, and the
Keychain still reads and writes. That last one is the reason this exists:
`keyring` finds its backends through entry points, which PyInstaller's static
analysis cannot see. Without the `--hidden-import` flags in `build_app.sh` the
packaged app falls back to a null backend — it accepts your password, reports
success, and stores nothing. `--selftest` also works from source, where it
should report `frozen bundle: False`.

If a build fails inside PyInstaller's shared binary cache
(`SystemError: Failed to process binary …`), `--clean` won't help; it only
clears `build/`. Clear the cache itself:

```bash
rm -rf ~/Library/Application\ Support/pyinstaller
```

## Layout

```
main.py                  entry point (--selftest checks a build)
build_app.sh             PyInstaller build; --install copies to /Applications
config.example.json      committed template; every identity field blank
tests/                   pytest suite; fakes.py stubs the browser and notifiers
assets/
  make_icon.py           regenerates icon.icns (run manually; icon.iconset
                         is an intermediate and is git-ignored)
unblock_tracker/
  config.py              Settings dataclass, JSON load/save, validation
  secrets.py             Keychain wrapper
  checker.py             BrowserChecker (Selenium) and AnonymousChecker
  proxies.py             optional proxy pool
  notifiers.py           Telegram / Pushbullet / off
  monitor.py             the run loop and event store
ui/
  theme.py               palette, stylesheet and layout helpers
  main_window.py         window and tab wiring
  settings_tab.py        the settings form
  monitor_tab.py         live status and log
  events_tab.py          history table and screenshot preview
  worker.py              runs the engine off the GUI thread
```

The engine has no Qt dependency — `MonitorEngine` talks to callers through
plain callbacks, so it can be driven by a test or a headless runner just as
easily as by the GUI.

## Interface notes

The app runs on Qt's **Fusion** style, not the native macOS one, and follows
the system light/dark appearance. Fusion is deliberate: native widgets fight a
stylesheet, and macOS defaults `QFormLayout` to `FieldsStayAtSizeHint`, which
pins inputs to their minimum width and elides placeholder text into `...`.
Fusion behaves identically everywhere, so a rendered test matches what ships.

Two consequences worth knowing before editing `ui/theme.py`:

- Styling a subcontrol (`::indicator`, `::drop-down`) hands drawing to the
  stylesheet, which then draws no checkmark or arrow unless given an image.
  Fusion's own drawing isn't a fallback — it derives outlines from the window
  colour, which is near-black in dark mode, so an unchecked box comes out
  invisible. `theme.glyphs()` paints the tick and chevrons with QPainter at
  startup and hands the stylesheet their paths.
- Content sits in a width-capped centred column (`theme.column()`). It uses
  stretch spacers rather than `AlignHCenter`, which would give the column its
  size hint and collapse a sparse tab to a sliver.

## Notes

Instagram does not offer an API for this, so checks work by reading the
rendered profile page. That is inherently brittle: page markup changes, and
frequent automated logins can get an account flagged. The pacing defaults
(random 10–20s intervals, quiet hours, periodic browser restarts) exist to keep
the request rate low. Use your own account, and keep the interval sane.

The run folder records when a specific person's profile became visible to you.
Treat it as personal data: it stays out of git by default, and is worth keeping
out of anything you publish or share.
