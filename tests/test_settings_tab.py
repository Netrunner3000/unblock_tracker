"""The settings form: what it collects, what it persists, and where secrets go."""

from __future__ import annotations

import pytest

from pathlib import Path

from unblock_tracker import config, secrets

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def tab(qapp, config_path):
    from ui.settings_tab import SettingsTab

    return SettingsTab(config.Settings())


def fill(tab, **values) -> None:
    """Type into the form the way a user would."""
    if "username" in values:
        tab.instagram_username.setText(values["username"])
    if "target" in values:
        tab.target_profile.setText(values["target"])
    if "password" in values:
        tab.instagram_password.setText(values["password"])
    if "telegram_token" in values:
        tab.telegram_token.setText(values["telegram_token"])
    if "chat_id" in values:
        tab.telegram_chat_id.setText(values["chat_id"])
    if "notifier" in values:
        tab.notifier.setCurrentIndex(tab.notifier.findData(values["notifier"]))


# ----------------------------------------------------------------------
# Collecting
# ----------------------------------------------------------------------
def test_a_fresh_tab_collects_nothing(tab):
    collected = tab.collect()
    assert collected.instagram_username == ""
    assert collected.target_profile == ""
    assert collected.telegram_chat_id == ""


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("@myhandle", "myhandle"), ("myhandle", "myhandle"), ("  @spaced  ", "spaced")],
)
def test_leading_at_and_whitespace_are_stripped(tab, typed, expected):
    fill(tab, username=typed, target=typed)
    collected = tab.collect()
    assert collected.instagram_username == expected
    assert collected.target_profile == expected


def test_blank_data_dir_falls_back_to_runs(tab):
    tab.data_dir.setText("   ")
    assert tab.collect().data_dir == "runs"


# ----------------------------------------------------------------------
# Persisting
# ----------------------------------------------------------------------
def test_save_persists_settings_to_config_json(tab, config_path):
    fill(tab, username="@myhandle", target="@watched", chat_id="12345")
    tab.interval_min.setValue(7)
    tab.save()

    reloaded = config.load(config_path)
    assert reloaded.instagram_username == "myhandle"
    assert reloaded.target_profile == "watched"
    assert reloaded.telegram_chat_id == "12345"
    assert reloaded.interval_min_seconds == 7


def test_secrets_never_reach_config_json(tab, config_path):
    """The whole point of the Keychain: nothing sensitive is written to disk."""
    fill(
        tab,
        username="myhandle",
        target="watched",
        password="s3cret-password",
        telegram_token="s3cret-token",
        notifier=config.NOTIFIER_TELEGRAM,
        chat_id="12345",
    )
    tab.pushbullet_token.setText("s3cret-pushbullet")
    tab.save()

    raw = config_path.read_text()
    assert "s3cret-password" not in raw
    assert "s3cret-token" not in raw
    assert "s3cret-pushbullet" not in raw

    assert secrets.get(secrets.INSTAGRAM_PASSWORD, "myhandle") == "s3cret-password"
    assert secrets.get(secrets.TELEGRAM_BOT_TOKEN, "myhandle") == "s3cret-token"
    assert secrets.get(secrets.PUSHBULLET_TOKEN, "myhandle") == "s3cret-pushbullet"


def test_save_emits_settings_saved(tab):
    seen = []
    tab.settings_saved.connect(lambda: seen.append(True))
    tab.save()
    assert seen == [True]


def test_renaming_the_account_moves_its_secrets(tab, config_path):
    fill(tab, username="oldname", password="pw", telegram_token="tok")
    tab.pushbullet_token.setText("pb")
    tab.save()
    assert secrets.get(secrets.INSTAGRAM_PASSWORD, "oldname") == "pw"

    fill(tab, username="newname")
    tab.save()

    for name, value in (
        (secrets.INSTAGRAM_PASSWORD, "pw"),
        (secrets.TELEGRAM_BOT_TOKEN, "tok"),
        (secrets.PUSHBULLET_TOKEN, "pb"),
    ):
        assert secrets.get(name, "newname") == value, name
        assert secrets.get(name, "oldname") == "", f"{name} stranded under the old name"


def test_load_repopulates_the_form_from_settings_and_keychain(tab):
    secrets.set(secrets.INSTAGRAM_PASSWORD, "stored-pw", "someone")
    secrets.set(secrets.TELEGRAM_BOT_TOKEN, "stored-tok", "someone")

    tab.load(
        config.Settings(
            instagram_username="someone",
            target_profile="watched",
            telegram_chat_id="42",
            notifier=config.NOTIFIER_TELEGRAM,
            interval_min_seconds=11,
        )
    )

    assert tab.instagram_username.text() == "someone"
    assert tab.target_profile.text() == "watched"
    assert tab.instagram_password.text() == "stored-pw"
    assert tab.telegram_token.text() == "stored-tok"
    assert tab.telegram_chat_id.text() == "42"
    assert tab.interval_min.value() == 11


# ----------------------------------------------------------------------
# Conditional UI
# ----------------------------------------------------------------------
def test_notifier_choice_reveals_only_the_matching_fields(tab):
    tab.show()

    tab.notifier.setCurrentIndex(tab.notifier.findData(config.NOTIFIER_NONE))
    assert not tab.telegram_box.isVisible()
    assert not tab.pushbullet_box.isVisible()
    assert not tab.test_button.isEnabled()

    tab.notifier.setCurrentIndex(tab.notifier.findData(config.NOTIFIER_TELEGRAM))
    assert tab.telegram_box.isVisible()
    assert not tab.pushbullet_box.isVisible()
    assert tab.test_button.isEnabled()

    tab.notifier.setCurrentIndex(tab.notifier.findData(config.NOTIFIER_PUSHBULLET))
    assert not tab.telegram_box.isVisible()
    assert tab.pushbullet_box.isVisible()


def test_anonymous_mode_disables_the_credential_fields(tab):
    tab.check_mode.setCurrentIndex(tab.check_mode.findData(config.CHECK_MODE_ANONYMOUS))
    assert not tab.instagram_username.isEnabled()
    assert not tab.instagram_password.edit.isEnabled()

    tab.check_mode.setCurrentIndex(tab.check_mode.findData(config.CHECK_MODE_LOGIN))
    assert tab.instagram_username.isEnabled()
    assert tab.instagram_password.edit.isEnabled()


def test_secret_field_masks_until_revealed(tab):
    from PySide6.QtWidgets import QLineEdit

    field = tab.instagram_password
    assert field.edit.echoMode() == QLineEdit.EchoMode.Password
    field.toggle.setChecked(True)
    assert field.edit.echoMode() == QLineEdit.EchoMode.Normal
    field.toggle.setChecked(False)
    assert field.edit.echoMode() == QLineEdit.EchoMode.Password


# ----------------------------------------------------------------------
# Layout regression
# ----------------------------------------------------------------------
def test_form_fields_are_allowed_to_grow():
    """Regression: macOS defaults to FieldsStayAtSizeHint, which elides
    placeholder text into "...". The helper must set the policy explicitly."""
    from PySide6.QtWidgets import QFormLayout

    from ui import theme

    assert (
        theme.form().fieldGrowthPolicy()
        == QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
    )


def test_fields_grow_to_fill_the_column(qapp, config_path):
    """The user-visible half of the growth policy.

    Asserting only that no placeholder is clipped is too weak: the fields carry
    a minimum width, so short placeholders fit even when growth is broken. This
    checks that a field actually expands well past that minimum.
    """
    from ui.settings_tab import FIELD_MIN, SettingsTab

    tab = SettingsTab(config.Settings())
    tab.resize(900, 900)
    tab.show()
    qapp.processEvents()

    width = tab.target_profile.width()
    assert width > FIELD_MIN + 100, (
        f"field is {width}px, barely past its {FIELD_MIN}px minimum — "
        "it is sitting at its size hint instead of filling the column"
    )


@pytest.mark.parametrize("width", [760, 1100, 1900])
def test_no_placeholder_is_clipped_at_any_window_width(qapp, config_path, width):
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QLineEdit

    from ui.settings_tab import SettingsTab

    tab = SettingsTab(config.Settings())
    tab.resize(width, 900)
    tab.show()
    qapp.processEvents()

    clipped = []
    for edit in tab.findChildren(QLineEdit):
        text = edit.placeholderText()
        if not text or not edit.isVisible():
            continue
        needed = QFontMetrics(edit.font()).horizontalAdvance(text)
        usable = edit.width() - 20  # horizontal padding from the stylesheet
        if needed > usable:
            clipped.append(f"{text!r} needs {needed}px but has {usable}px")

    assert not clipped, "placeholder text would be elided: " + "; ".join(clipped)


# ----------------------------------------------------------------------
# Browse… starting folder
# ----------------------------------------------------------------------
def test_relative_paths_do_not_send_the_dialog_to_the_filesystem_root(tmp_path):
    """Regression: "runs" is meaningless to QFileDialog, which then opened /."""
    from ui.settings_tab import _existing_dir

    assert _existing_dir("runs", tmp_path) == str(tmp_path)
    assert _existing_dir("", tmp_path) == str(tmp_path)
    assert _existing_dir("   ", tmp_path) == str(tmp_path)


def test_absolute_paths_are_honoured(tmp_path):
    from ui.settings_tab import _existing_dir

    assert _existing_dir(str(tmp_path), Path("/nowhere")) == str(tmp_path)


def test_a_missing_absolute_path_walks_up_to_something_real(tmp_path):
    from ui.settings_tab import _existing_dir

    deep = tmp_path / "not" / "created" / "yet"
    assert _existing_dir(str(deep), tmp_path) == str(tmp_path)


def test_browse_opens_the_configured_run_folder(tab, tmp_path):
    """The reported bug: Browse… landed on Macintosh HD instead of runs/."""
    tab.data_dir.setText(str(tmp_path / "custom-runs"))
    opened = tab._current_data_dir()

    assert opened == tmp_path / "custom-runs"
    assert opened.exists(), "the folder should be created so the dialog opens inside it"


def test_browse_falls_back_to_the_resolved_default_when_relative(tab):
    tab.data_dir.setText("runs")
    opened = tab._current_data_dir()

    assert opened.is_absolute()
    assert opened == config.Settings(data_dir="runs").resolved_data_dir()
