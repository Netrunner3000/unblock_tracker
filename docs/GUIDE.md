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
- **Also watch** — optional. One extra handle per line to watch alongside the
  main one. Each cycle checks every handle in turn, so more profiles means a
  longer cycle. With more than one, a run keeps going past the first profile
  that becomes visible instead of stopping.

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

Under the channel are three toggles for which tracked signals are worth
interrupting you for. Visibility changes always alert — that is the point of
the app. Follower arrivals/departures and relationship changes are on by
default; raw counts are off, because an active account moves them constantly
and would bury the alerts that matter. Everything is recorded either way.

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
| **Check failed** | The check itself broke: network, browser, or login trouble — including landing on the sign-in page, which means the session expired. Not a statement about the profile. |
| **Unknown** | No check has completed yet. |

An event is recorded when the status *changes*, not on every check. The first
check establishes a baseline and records nothing.

---

## What else gets tracked

Beyond "can I see this profile", each check reads whatever else the page
happens to expose and tells you when it moves:

| Signal | What a change means |
|---|---|
| **followers / following / posts** | The count went up or down. Post counts falling means something was deleted or archived. |
| **who follows** | Named arrivals and departures, when the follower list can be read. |
| **private** | The account switched between public and private. |
| **verified** | A badge appeared or disappeared. |
| **restricted** | You appear to have been restricted, or un-restricted. |
| **close friends** | A story you can see was, or stopped being, a Close Friends story. |

Two rules keep this honest:

- **The first reading is a baseline, never an alert.** Nothing is reported
  until there is something to compare against.
- **A signal that could not be read is silence, not zero.** If a check fails to
  find the follower count, the app says nothing rather than announcing that
  everyone unfollowed you — and the previous value is kept.

Deleted posts are recorded as *that a post went away* (the count dropped), with
a timestamp. The app does not keep a copy of removed content.

Which signals are available depends on the mode and the account: a public
profile in anonymous mode exposes counts, while follower lists and relationship
flags need a logged-in session and an account whose lists you can open.

## 3. Read the history

The **Events** tab lists every recorded change, newest first, with the
screenshot taken at that moment. Select a row to see it. The dot in the
**Shot** column means a screenshot exists, and the **Target** column says which
handle the row is about — useful once you are watching more than one.

**Open run folder** reveals the raw files:

- `events.csv` — the same table, for a spreadsheet
- `monitor.log` — the full activity log, including checks that changed nothing
- `screenshots/` — one image per recorded change
- `snapshots.json` — the last reading per handle, so counts and follower lists
  can be compared across restarts

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
- **Wait after a failure** — after a failed check the app waits this long, and
  doubles it while failures continue. Failures usually mean rate limiting or a
  dead session, and asking harder makes both worse. Watching several handles
  multiplies the request rate, which makes this matter more.
- **Page load timeout** — how long to wait for a page before reading whatever
  arrived.

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

**Proxies** — routes the browser through someone else's IP address instead of
your own. Off by default, and see [When proxies help](#when-proxies-help)
before turning it on: for logged-in mode they usually make things *worse*.

---

## When proxies help

A proxy makes your requests arrive from a different IP address. Instagram sees
that address, not yours.

**The problem a proxy solves.** Instagram counts requests per IP. Check a
profile every 10–20 seconds for hours from one home connection and that address
accumulates a pattern no person produces. The usual result is not a ban but
*rate limiting*: pages start coming back thin or empty. That is worse than it
sounds here, because a throttled page can look exactly like a blocked one — the
app would report "Blocked or unavailable" when nothing about the profile
changed. Spreading requests across addresses keeps any single one below the
threshold.

**Why it usually backfires in logged-in mode.** Instagram does not just count
requests, it scores *where a session logs in from*. A stable home IP is the
least suspicious thing about your account. Signing in from a rotating set of
unfamiliar addresses — often datacentre ranges in other countries, which are
flagged far harder than residential ones — is a much stronger fraud signal than
the request rate you were trying to hide. You would be trading a small problem
for a bigger one, and the likely outcome is a verification challenge that stops
the monitor entirely.

There is also a plain security cost. Traffic to Instagram is encrypted, so an
operator cannot read your password, but they do see which sites you connect to,
and can drop, delay or interfere with connections. A free proxy list is run by
people you know nothing about, and you would be pointing an authenticated
session through it.

**So when is it worth it?**

| | Verdict |
|---|---|
| Logged-in mode, free public list | No. Slow, mostly dead, and rotating login IPs invites a challenge. |
| Logged-in mode, one stable paid residential proxy | Only if your home IP is already rate-limited. Pick one address and keep it — rotation is the harmful part. |
| Anonymous mode | This is the case it fits. No login means no session to make suspicious, so you are only working around per-IP rate limits. |
| Hiding from the person you are watching | Pointless. They never see your requests; only Instagram does. |

The built-in source is a free public list, which is the weakest option of all —
most entries are dead, and the survivors are slow enough to cause failed checks
on their own. Treat the feature as a way to plug in a proxy you already trust,
not a reason to go find one.

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

**Everything says "Check failed" and mentions the session.**
The app landed on Instagram's sign-in page instead of a profile, which means
the session is no longer valid. This is deliberately reported as a failure
rather than a result: a login page carries none of the "unavailable" markers,
so treating it as a normal read would announce that the profile is visible when
nothing of the sort happened. Forget the saved session and sign in again.

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
