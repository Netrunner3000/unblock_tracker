#!/usr/bin/env python3
"""Unblock Tracker — entry point.

    python main.py              launch the app
    python main.py --selftest   check a build's wiring and exit

The self-test exists because a packaged .app can fail in ways the source tree
cannot: keyring resolves its backends through entry points, which PyInstaller's
static analysis does not see. Running it against the built binary confirms the
Keychain still works before the app is trusted with a secret.
"""

import sys


def selftest() -> int:
    from unblock_tracker import APP_NAME, asset_path, config, guide_path, secrets

    frozen = getattr(sys, "frozen", False)
    icon = asset_path("icon.icns")
    guide = guide_path()
    backend = secrets.backend_name()

    print(f"{APP_NAME} self-test")
    print(f"  frozen bundle:   {frozen}")
    print(f"  icon asset:      {icon} ({'found' if icon.exists() else 'MISSING'})")
    print(f"  user guide:      {guide} ({'found' if guide.exists() else 'MISSING'})")
    print(f"  config path:     {config.CONFIG_PATH}")
    print(f"  run data:        {config.Settings().resolved_data_dir()}")
    print(f"  keyring backend: {backend}")

    problems = []
    if not icon.exists():
        problems.append("icon asset missing from the bundle")
    if not guide.exists():
        problems.append("user guide missing from the bundle")
    if frozen and ".app/" in str(config.CONFIG_PATH):
        problems.append("config would be written inside the .app bundle")
    if "macOS" not in backend:
        problems.append(f"expected the macOS Keychain backend, got {backend}")

    probe = "__selftest__"
    secrets.set(secrets.INSTAGRAM_PASSWORD, "roundtrip", probe)
    if secrets.get(secrets.INSTAGRAM_PASSWORD, probe) != "roundtrip":
        problems.append("Keychain round-trip failed")
    secrets.delete(secrets.INSTAGRAM_PASSWORD, probe)
    print("  keychain r/w:    ok" if not problems else "  keychain r/w:    FAILED")

    if problems:
        print("\nFAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nOK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())

    from ui.main_window import run

    sys.exit(run())
