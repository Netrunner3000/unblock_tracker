"""Instagram unblock monitor — engine and configuration.

Nothing in this package carries a baked-in account, target handle or token.
Every identity value comes from the user's own settings (see `config`) and
every secret comes from the macOS Keychain (see `secrets`).
"""

import sys
from pathlib import Path

APP_NAME = "Unblock Tracker"
BUNDLE_ID = "com.netrunner3000.unblocktracker"


def asset_path(name: str) -> Path:
    """Locate a bundled asset, running from source or from a frozen .app."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "assets" / name
