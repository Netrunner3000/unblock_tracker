"""The user guide and the Help window that displays it."""

from __future__ import annotations

import re

import pytest

from unblock_tracker import config, guide_path

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(scope="module")
def guide_text() -> str:
    return guide_path().read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# The document
# ----------------------------------------------------------------------
def test_the_guide_ships_with_the_source():
    assert guide_path().exists(), f"{guide_path()} is missing"


def test_the_guide_has_real_content(guide_text):
    assert len(guide_text) > 2000
    assert guide_text.lstrip().startswith("# How to use")


def test_the_guide_covers_each_tab(guide_text):
    for topic in ("Settings", "Monitor", "Events", "Check modes", "Troubleshooting"):
        assert topic in guide_text, f"the guide never mentions {topic}"


def test_the_guide_names_no_real_account_or_token(guide_text):
    """The whole project's rule: no real handles or secrets in the repo."""
    for leaked in ("as.dubs", "ca_lfs", "irene_palma", "1Fucku", "8027216439",
                   "o.cGZEgBLL", "5569721341"):
        assert leaked not in guide_text, f"the guide leaks {leaked!r}"

    # Nothing that looks like a real Telegram bot token.
    assert not re.search(r"\b\d{8,}:[A-Za-z0-9_-]{30,}\b", guide_text)


def test_documented_statuses_match_the_code(guide_text):
    """A guide that describes statuses the app cannot produce is worse than none."""
    from unblock_tracker import checker

    for status in (
        checker.VISIBLE_PUBLIC,
        checker.VISIBLE_PRIVATE,
        checker.BLOCKED,
        checker.ERROR,
        checker.UNKNOWN,
    ):
        assert checker.label(status) in guide_text, (
            f"status {checker.label(status)!r} is undocumented"
        )


def test_documented_settings_labels_exist_in_the_ui(qapp, config_path, guide_text):
    """Catches the guide drifting away from the form it describes."""
    from PySide6.QtWidgets import QCheckBox, QLabel

    from ui.settings_tab import SettingsTab

    tab = SettingsTab(config.Settings())
    shown = {w.text() for w in tab.findChildren(QLabel)}
    shown |= {w.text() for w in tab.findChildren(QCheckBox)}

    for label in ("Check mode", "Target profile", "Wait between checks",
                  "Maximum run time", "Quiet hours", "Send alerts via"):
        assert label in shown, f"the guide references {label!r}, which the UI lacks"
        assert label in guide_text


# ----------------------------------------------------------------------
# The window
# ----------------------------------------------------------------------
def test_dialog_renders_the_guide(qapp):
    from ui.help_dialog import HelpDialog

    dialog = HelpDialog()
    rendered = dialog.browser.toPlainText()

    assert "How to use" in rendered
    assert "Troubleshooting" in rendered
    assert len(rendered) > 1500
    assert dialog.open_button.isEnabled()


def test_dialog_degrades_gracefully_when_the_guide_is_missing(qapp, monkeypatch):
    """A packaged build without the doc should explain itself, not crash."""
    import ui.help_dialog as help_dialog

    monkeypatch.setattr(
        help_dialog, "guide_path", lambda: guide_path().with_name("absent.md")
    )
    dialog = help_dialog.HelpDialog()

    assert "Guide unavailable" in dialog.browser.toPlainText()
    assert not dialog.open_button.isEnabled()


def test_help_is_reachable_from_every_tab(qapp, config_path):
    from ui.main_window import MainWindow

    window = MainWindow()
    corner = window.tabs.cornerWidget()

    assert corner is window.help_button
    for index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(index)
        assert corner.isVisibleTo(window), (
            f"help button hidden on the {window.tabs.tabText(index)} tab"
        )


def test_help_window_is_reused_not_stacked(qapp, config_path):
    from ui.main_window import MainWindow

    window = MainWindow()
    window.show_help()
    first = window.help_window
    window.show_help()

    assert window.help_window is first, "each click created a new window"


def test_help_window_is_non_modal(qapp, config_path):
    """It must be usable alongside the Settings form, not block it."""
    from PySide6.QtCore import Qt

    from ui.main_window import MainWindow

    window = MainWindow()
    window.show_help()

    assert window.help_window.windowModality() == Qt.WindowModality.NonModal
