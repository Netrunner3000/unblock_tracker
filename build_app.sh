#!/bin/bash
# Builds "Unblock Tracker.app" with PyInstaller into dist/.
# Pass --install to also copy it into /Applications.
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="Unblock Tracker"
BUNDLE_ID="com.netrunner3000.unblocktracker"

source .venv/bin/activate
uv pip install -q pyinstaller

# Regenerate the icon so the bundle never ships a stale one.
python assets/make_icon.py

rm -rf build dist

# keyring finds its backends through entry points, which PyInstaller's static
# analysis cannot see — without these the packaged app falls back to a null
# backend and silently loses every stored secret.
pyinstaller --noconfirm --clean --windowed \
  --name "$APP_NAME" \
  --icon assets/icon.icns \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --add-data "assets/icon.icns:assets" \
  --hidden-import keyring.backends.macOS \
  --hidden-import keyring.backends.null \
  --exclude-module PySide6.QtWebEngineCore \
  --exclude-module PySide6.QtWebEngineWidgets \
  --exclude-module PySide6.Qt3DCore \
  --exclude-module PySide6.QtCharts \
  --exclude-module PySide6.QtDataVisualization \
  --exclude-module PySide6.QtMultimedia \
  --exclude-module PySide6.QtQuick3D \
  --exclude-module tkinter \
  main.py

echo
echo "Built: dist/$APP_NAME.app ($(du -sh "dist/$APP_NAME.app" | cut -f1))"

if [[ "${1:-}" == "--install" ]]; then
  rm -rf "/Applications/$APP_NAME.app"
  cp -R "dist/$APP_NAME.app" /Applications/
  touch "/Applications/$APP_NAME.app"  # nudge Finder/Dock to refresh the cached icon
  echo "Installed: /Applications/$APP_NAME.app"
else
  echo "Run '$0 --install' to copy it into /Applications."
fi
