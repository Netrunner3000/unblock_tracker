"""Instagram unblock monitor — engine and configuration.

Nothing in this package carries a baked-in account, target handle or token.
Every identity value comes from the user's own settings (see `config`) and
every secret comes from the macOS Keychain (see `secrets`).
"""

APP_NAME = "Unblock Tracker"
