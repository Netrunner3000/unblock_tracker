"""The user guide, shown in-app.

Rendered from `docs/GUIDE.md` so there is exactly one copy of the text: the
same file is readable on disk and on GitHub. The window is deliberately
non-modal, so it can stay open next to the Settings tab while you work
through it.
"""

from __future__ import annotations

import subprocess

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from unblock_tracker import APP_NAME, guide_path

from . import theme

MISSING = (
    "# Guide unavailable\n\n"
    "`docs/GUIDE.md` could not be found. If you are running a packaged build, "
    "it was not included — rebuild with `build_app.sh`."
)


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — How to use")
        self.resize(820, 760)
        self.setMinimumSize(520, 420)
        # Non-modal: the point is to read it while filling in Settings.
        self.setWindowModality(Qt.WindowModality.NonModal)

        palette = theme.active()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet(
            f"QTextBrowser {{ background: {palette.card};"
            f" border: 1px solid {palette.border};"
            f" border-radius: 10px; padding: 18px 22px; font-size: 14px; }}"
        )
        # The document stylesheet only applies to content set afterwards, so
        # this has to come before setMarkdown or links keep Qt's default blue.
        self.browser.document().setDefaultStyleSheet(
            f"a {{ color: {palette.accent}; text-decoration: none; }}"
            "code { font-family: Menlo, monospace; }"
            "th, td { padding: 4px 10px; }"
            "th { text-align: left; }"
        )
        self.browser.setMarkdown(self._text())
        layout.addWidget(self.browser, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)

        self.open_button = QPushButton("Open in editor")
        self.open_button.setToolTip(str(guide_path()))
        self.open_button.clicked.connect(self._open_externally)
        self.open_button.setEnabled(guide_path().exists())

        close = QPushButton("Close")
        close.setObjectName("primary")
        close.setMinimumWidth(110)
        close.clicked.connect(self.close)

        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _text(self) -> str:
        path = guide_path()
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return MISSING

    def _open_externally(self) -> None:
        path = guide_path()
        if not path.exists():
            return
        # Honours the user's default handler; fall back to `open` if Qt declines.
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            subprocess.run(["open", str(path)], check=False)
