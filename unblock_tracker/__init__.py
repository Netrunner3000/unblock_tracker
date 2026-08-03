"""Instagram unblock monitor — engine and configuration.

Nothing in this package carries a baked-in account, target handle or token.
Every identity value comes from the user's own settings (see `config`) and
every secret comes from the macOS Keychain (see `secrets`).
"""

import sys
from pathlib import Path

APP_NAME = "Unblock Tracker"
BUNDLE_ID = "com.netrunner3000.unblocktracker"


def resource_path(*parts: str) -> Path:
    """Locate a bundled file, running from source or from a frozen .app."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base.joinpath(*parts)


def asset_path(name: str) -> Path:
    """Locate a bundled asset, running from source or from a frozen .app."""
    return resource_path("assets", name)


def guide_path() -> Path:
    """The user guide shown by the Help button."""
    return resource_path("docs", "GUIDE.md")
