# How to use Unblock Tracker

Unblock Tracker checks, on a schedule, whether a particular Instagram profile
is reachable from your account. When that changes it records the moment, saves
a screenshot, and can message you.

---

## Before you start

You need the handle of the profile you want to watch, and — for the accurate
check mode — the login for an Instagram account of your own.

Nothing is filled in for you. The app opens with empty fields and will not
start until you complete them.

---

## 1. Fill in Settings

Open the **Settings** tab. Work down the cards.

**Your Instagram account**

- **Check mode** — leave on *Logged in* unless you have a reason not to. See
  [Check modes](#check-modes) below.
- **Username** — your own handle. The `@` is optional; it gets stripped.
- **Password** — your Instagram password. It goes into the macOS Keychain, not
  into any file. Use *Show* if you need to confirm what you typed.

**Profile to watch**

- **Target profile** — the handle you want to monitor, without the `@`.

**Notifications** — optional, but the main reason to run this unattended. Pick
a channel under **Send alerts via**:

- *Off* — the app records everything; you check the Events tab yourself.
- *Telegram* — needs a bot token and a chat ID. Message
  [@BotFather](https://t.me/BotFather) on Telegram, create a bot with
  `/newbot`, and it gives you the token. For the chat ID, message your new bot
  once, then open
  `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and read
  `chat.id` out of the response.
- *Pushbullet* — needs an access token from
  [pushbullet.com/account](https://www.pushbullet.com/#settings/account).

Press **Send test notification** before relying on it. It tells you
immediately whether the token and chat ID actually work, rather than letting
you find out by missing the alert you were waiting for.

Then press **Save settings**.

> The first time the app reads or writes a secret, macOS asks for permission to
> use your Keychain. Choose **Always Allow**, or it will ask on every launch.

---

## 2. Start monitoring

Go to the **Monitor** tab and press **Start monitoring**.

If anything required is missing, the app says exactly what — it will not start
half-configured.

While it runs you see:

- the current status in large type,
- a one-line explanation underneath,
- a running count of checks and elapsed time,
- a live activity log.

**Stop** takes effect immediately, even mid-wait. You do not have to wait out
the current interval.

### What the statuses mean

| Status | Meaning |
|---|---|
| **Visible (public)** | The profile page loaded normally. |
| **Visible (private account)** | The profile exists and shows as private — reachable, just not open. |
| **Blocked or unavailable** | Instagram says the page is not available. Blocked, deactivated, renamed, or deleted — the page cannot tell these apart. |
| **Check failed** | The check itself broke: network, browser, or login trouble. Not a statement about the profile. |
| **Unknown** | No check has completed yet. |

An event is recorded when the status *changes*, not on every check. The first
check establishes a baseline and records nothing.

---

## 3. Read the history

The **Events** tab lists every recorded change, newest first, with the
screenshot taken at that moment. Select a row to see it. The dot in the
**Shot** column means a screenshot exists.

**Open run folder** reveals the raw files:

- `events.csv` — the same table, for a spreadsheet
- `monitor.log` — the full activity log, including checks that changed nothing
- `screenshots/` — one image per recorded change

---

## Check modes

| | Logged in | Anonymous |
|---|---|---|
| Credentials | required | none |
| Can see private accounts | yes | no |
| Screenshots | yes | no |
| Detects profile-picture changes | no | yes |
| Risk of tripping Instagram's defences | higher | lower |

**Logged in** drives a real browser. It is the only mode that can tell
"blocked" apart from "private", because a logged-out visitor sees the same
thing either way.

**Anonymous** just fetches the public page and hashes the profile picture. It
needs no password and is far less likely to draw attention, but it only sees
what any logged-out visitor sees.

---

## Tuning the schedule

The defaults are deliberately unhurried. Checking more often does not get you
an answer sooner in any useful sense, and does raise the chance of the account
being flagged.

- **Wait between checks** — a random delay in this range before each check.
  The randomness is the point; a perfectly regular request pattern is a
  signature.
- **Maximum run time** — stop after this long. Set it to *no limit* to run
  until you stop it.
- **Stop the run once the profile becomes visible** — on by default. Turn it
  off to keep logging changes indefinitely.
- **Quiet hours** — pause overnight. Activity at 4am looks less like a person.

---

## Advanced settings

Most people never need these.

**Browser** (logged-in mode only)

- *Run the browser hidden* — off shows you the browser window, which is useful
  when a login is failing and you cannot see why.
- *Stay signed in between runs* — on by default, and worth leaving on. The app
  keeps Instagram's login cookies in its own browser profile and reuses them,
  so it signs in once rather than on every run and every browser restart.
  Repeated automated sign-ins are the likeliest thing to get an account
  challenged, so this meaningfully lowers the risk. The cookies are stored in
  `~/Library/Application Support/Unblock Tracker/sessions/`, separate for each
  account. *Forget saved session* deletes them and forces a fresh sign-in.
- *Rotate the user agent* — varies the browser fingerprint between sessions.
- *Confirm the session is logged in* — verifies the login actually took before
  trusting any result, and retries if not.
- *Restart browser after N checks* — periodically starts fresh.
- *Browser binary* / *chromedriver* — leave blank and the right driver is
  fetched automatically. Set them only to pin a specific browser (Brave, for
  instance) or a specific driver version.

**Proxies** — routes the browser through a proxy fetched from a public list.
Public proxies are slow and unreliable; expect failed checks. Off by default.

---

## Troubleshooting

**It says the login failed.**
Turn off *Run the browser hidden* and start again — you will usually see the
reason on screen: a verification prompt, a suspicious-login challenge, or
two-factor authentication. The app cannot answer those for you. Note that
Instagram tends to challenge logins from an unfamiliar browser profile.

If it used to work and suddenly does not, the saved session has probably been
invalidated. Press **Forget saved session** in Settings and start again — that
clears the stored cookies and signs in from scratch.

**Two-factor authentication is on.**
Logged-in mode cannot complete a 2FA challenge. Use Anonymous mode, or a
separate account without 2FA.

**The test notification failed.**
For Telegram, the most common cause is a chat ID from the wrong conversation,
or not having messaged the bot at least once — a bot cannot open a chat with
you. For Pushbullet, regenerate the token.

**Everything says "Blocked or unavailable".**
Confirm the handle is spelled correctly and has no `@`. Remember that a
deactivated, renamed, or deleted account is indistinguishable from a block.

**macOS keeps asking about the Keychain.**
Choose *Always Allow* rather than *Allow* when the prompt appears.

**The status never changes.**
That is the expected result most of the time. Check `monitor.log` in the run
folder to confirm checks are actually happening.

---

## Where your data is kept

| | Installed app | Running from source |
|---|---|---|
| Settings | `~/Library/Application Support/Unblock Tracker/config.json` | `config.json` in the project folder |
| Events, logs, screenshots | `…/Unblock Tracker/runs/` | `runs/` in the project folder |
| Password and tokens | macOS Keychain | macOS Keychain |
| Saved login session | `…/Unblock Tracker/sessions/` | same |

The saved session is deliberately kept in Application Support in both cases:
login cookies are close enough to a password, and the project folder is under
version control and gets copied to cloud backup.

The two copies keep **separate settings**, so configuring one does not
configure the other. Keychain secrets are shared between them.

Secrets are never written to a file, so there is nothing sensitive to leak
into a backup or a git repository. The run folder is a different matter: it
records when a specific person's profile became visible to you. Treat it as
personal data.

---

## Honest limits

Instagram has no API for this, so every check works by reading the rendered
profile page. That has consequences worth knowing:

- **It can break.** When Instagram changes its markup, checks may start
  failing or misreporting until the detection is updated.
- **"Blocked" is an inference, not a fact.** The page looks identical whether
  you were blocked, or the account was deactivated, renamed, or deleted.
- **Automated logins carry risk.** Instagram's terms do not permit automated
  access, and an account making regular scripted logins can be rate-limited,
  challenged, or disabled. Use an account you can afford to lose, keep the
  interval generous, and leave quiet hours on.
