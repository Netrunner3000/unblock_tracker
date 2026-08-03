"""Settings persistence, tolerance of bad files, and validation."""

from __future__ import annotations

import json
from dataclasses import fields

import pytest

from unblock_tracker import config


def test_defaults_carry_no_identity():
    """A fresh checkout must not name an account, a target or a chat."""
    blank = config.Settings()
    assert blank.instagram_username == ""
    assert blank.target_profile == ""
    assert blank.telegram_chat_id == ""
    assert blank.notifier == config.NOTIFIER_NONE


def test_committed_example_config_is_blank():
    example = json.loads((config.PROJECT_ROOT / "config.example.json").read_text())
    for key in ("instagram_username", "target_profile", "telegram_chat_id"):
        assert example[key] == "", f"{key} must ship empty"


def test_round_trip_preserves_every_field(tmp_path):
    path = tmp_path / "config.json"
    original = config.Settings(
        instagram_username="me",
        target_profile="them",
        telegram_chat_id="999",
        check_mode=config.CHECK_MODE_ANONYMOUS,
        notifier=config.NOTIFIER_TELEGRAM,
        interval_min_seconds=5,
        interval_max_seconds=9,
        max_runtime_minutes=0,
        stop_on_unblock=False,
        night_break_enabled=False,
        night_break_start_hour=1,
        night_break_end_hour=7,
        headless=False,
        browser_binary="/somewhere/Brave",
        chromedriver_path="/somewhere/chromedriver",
        rotate_user_agent=False,
        user_agents=["one", "two"],
        restart_after_checks=0,
        verify_login=False,
        login_attempts=7,
        use_proxy=True,
        proxy_source_url="https://example.invalid/proxies",
        save_screenshots=False,
        data_dir="somewhere-else",
    )

    config.save(original, path)
    reloaded = config.load(path)

    assert reloaded == original
    # Every declared field actually survived, not just the ones asserted above.
    for field in fields(config.Settings):
        assert getattr(reloaded, field.name) == getattr(original, field.name), field.name


def test_save_creates_missing_parent_directories(tmp_path):
    path = tmp_path / "nested" / "deeper" / "config.json"
    config.save(config.Settings(target_profile="x"), path)
    assert config.load(path).target_profile == "x"


def test_missing_file_yields_blank_settings(tmp_path):
    assert config.load(tmp_path / "absent.json") == config.Settings()


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"target_profile": "x", "obsolete_setting": 123}')

    loaded = config.load(path)

    assert loaded.target_profile == "x"
    assert not hasattr(loaded, "obsolete_setting")


def test_corrupt_json_falls_back_to_blank_settings(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ this is not json")
    assert config.load(path) == config.Settings()


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------
def test_blank_settings_report_what_is_missing():
    problems = config.Settings().validate()
    assert any("Target profile" in p for p in problems)
    assert any("username" in p for p in problems)
    assert any("password" in p for p in problems)


def test_telegram_requires_both_token_and_chat_id():
    settings = config.Settings(
        target_profile="t",
        instagram_username="u",
        notifier=config.NOTIFIER_TELEGRAM,
        telegram_chat_id="",
    )

    problems = settings.validate(password="pw", token="")

    assert any("Telegram bot token" in p for p in problems)
    assert any("chat ID" in p for p in problems)


def test_telegram_passes_once_both_are_present():
    settings = config.Settings(
        target_profile="t",
        instagram_username="u",
        notifier=config.NOTIFIER_TELEGRAM,
        telegram_chat_id="12345",
    )
    assert settings.validate(password="pw", token="tok") == []


def test_pushbullet_requires_only_a_token():
    settings = config.Settings(
        target_profile="t", instagram_username="u", notifier=config.NOTIFIER_PUSHBULLET
    )

    assert any("Pushbullet" in p for p in settings.validate(password="pw", token=""))
    assert settings.validate(password="pw", token="tok") == []


def test_anonymous_mode_needs_no_credentials():
    settings = config.Settings(
        target_profile="t", check_mode=config.CHECK_MODE_ANONYMOUS
    )
    assert settings.validate() == []


def test_interval_bounds_are_checked():
    settings = config.Settings(
        target_profile="t",
        check_mode=config.CHECK_MODE_ANONYMOUS,
        interval_min_seconds=30,
        interval_max_seconds=10,
    )
    assert any("Maximum interval" in p for p in settings.validate())


@pytest.mark.parametrize(("start", "end"), [(-1, 6), (2, 24), (99, 99)])
def test_night_break_hours_must_be_valid(start, end):
    settings = config.Settings(
        target_profile="t",
        check_mode=config.CHECK_MODE_ANONYMOUS,
        night_break_start_hour=start,
        night_break_end_hour=end,
    )
    assert any("hour" in p for p in settings.validate())


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
def test_relative_data_dir_resolves_under_the_data_root():
    settings = config.Settings(data_dir="runs")
    assert settings.resolved_data_dir() == config.DATA_ROOT / "runs"
    assert settings.csv_path.name == "events.csv"
    assert settings.log_path.name == "monitor.log"
    assert settings.screenshot_dir.name == "screenshots"


def test_absolute_data_dir_is_used_as_given(tmp_path):
    settings = config.Settings(data_dir=str(tmp_path))
    assert settings.resolved_data_dir() == tmp_path
