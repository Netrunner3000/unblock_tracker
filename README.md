# Unblock Tracker

A small PySide6 desktop app that watches whether a given Instagram profile is
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
  **macOS Keychain**, under the service `unblock_tracker`. They are never
  written to a file, so there is nothing to accidentally commit or sync to a
  cloud backup.

## Setup

```bash
uv venv && uv pip install -r requirements.txt
```

Logged-in mode drives a real browser through Selenium. Selenium Manager fetches
a matching driver on its own; set explicit paths in Settings only if you want a
specific browser (for example Brave) or a pinned `chromedriver`.

## Running

```bash
python main.py
```

**Settings** — your account, the profile to watch, notification channel, pacing,
browser and proxy behaviour. Save writes `config.json` and pushes the secrets
into the Keychain.

**Monitor** — Start/Stop, the current status, and a live activity log. Stop
takes effect immediately even mid-wait.

**Events** — every recorded status change with its screenshot, read back from
`runs/events.csv`. This replaces the old Flask dashboard.

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

## Output

Everything a run produces lands in `runs/` (configurable, git-ignored):

- `events.csv` — timestamped status changes
- `monitor.log` — full activity log
- `screenshots/` — one capture per status change

## Layout

```
main.py                  entry point
unblock_tracker/
  config.py              Settings dataclass, JSON load/save, validation
  secrets.py             Keychain wrapper
  checker.py             BrowserChecker (Selenium) and AnonymousChecker
  proxies.py             optional proxy pool
  notifiers.py           Telegram / Pushbullet / off
  monitor.py             the run loop and event store
ui/
  main_window.py         window and tab wiring
  settings_tab.py        the settings form
  monitor_tab.py         live status and log
  events_tab.py          history table and screenshot preview
  worker.py              runs the engine off the GUI thread
```

The engine has no Qt dependency — `MonitorEngine` talks to callers through
plain callbacks, so it can be driven by a test or a headless runner just as
easily as by the GUI.

## Notes

Instagram does not offer an API for this, so checks work by reading the
rendered profile page. That is inherently brittle: page markup changes, and
frequent automated logins can get an account flagged. The pacing defaults
(random 10–20s intervals, quiet hours, periodic browser restarts) exist to keep
the request rate low. Use your own account, and keep the interval sane.
