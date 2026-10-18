"""Preference validation, persistence and interactive subtitle language selection."""

import json
from unittest.mock import Mock

import pytest

from pinak.config import PinakSettings
from pinak.subtitle_preferences import normalize_subtitle_languages, subtitle_language_name


@pytest.mark.parametrize("value", [[], ["en", "hi", "es", "fr"], ["all"], ["en.*"], ["xx"], [1]])
def test_invalid_language_preferences_are_rejected(value):
    with pytest.raises(ValueError):
        PinakSettings(subtitle_languages=value)


def test_language_preferences_normalize_and_preserve_order():
    assert normalize_subtitle_languages("HI,en,hi,pt-br") == ["hi", "en", "pt-BR"]
    assert PinakSettings().subtitle_languages == ["en"]
    languages = ["en", "hi", "es"]
    assert PinakSettings(subtitle_languages=languages).subtitle_languages == languages
    assert subtitle_language_name("hin") == "Hindi"
    assert subtitle_language_name("eng") == "English"


def test_preferences_survive_config_save_and_reload(monkeypatch, tmp_path):
    import pinak.config as cfg

    path = tmp_path / "config.json"
    monkeypatch.setattr(cfg, "CONFIG_FILE", str(path))
    monkeypatch.setattr(cfg, "LOCAL_CONFIG", str(tmp_path / "legacy.json"))
    monkeypatch.setattr(cfg, "config", PinakSettings().model_dump())
    monkeypatch.delenv("PINAK_SUBTITLE_LANGUAGES", raising=False)
    languages = ["hi", "en", "es"]
    assert cfg.save_config({"subtitle_languages": languages, "embed_subs": True})
    assert json.loads(path.read_text())["subtitle_languages"] == languages
    cfg.config.update(PinakSettings().model_dump())
    assert cfg.init_config()["subtitle_languages"] == languages
    assert cfg.config["embed_subs"] is True


def test_language_picker_and_limit(monkeypatch):
    import pinak.cli as cli

    monkeypatch.setitem(cli.config, "subtitle_languages", ["en"])
    save = Mock(return_value=True)
    monkeypatch.setattr(cli, "save_config", save)
    captured = {}

    def checkbox(message, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(cli.questionary, "checkbox", checkbox)
    monkeypatch.setattr(cli, "ask_with_esc", lambda prompt: ["hi", "en"])
    cli.configure_subtitle_languages()
    save.assert_called_once_with({"subtitle_languages": ["hi", "en"]})
    assert captured["validate"](["en", "hi", "es"])
    assert not captured["validate"](["en", "hi", "es", "fr"])
    assert not captured["validate"]([])


def test_language_picker_accepts_real_keyboard_selection(monkeypatch):
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    import pinak.cli as cli

    monkeypatch.setitem(cli.config, "subtitle_languages", ["en"])
    save = Mock(return_value=True)
    monkeypatch.setattr(cli, "save_config", save)
    original_checkbox = cli.questionary.checkbox
    with create_pipe_input() as keyboard:
        monkeypatch.setattr(
            cli.questionary,
            "checkbox",
            lambda *args, **kwargs: original_checkbox(
                *args, **kwargs, input=keyboard, output=DummyOutput()
            ),
        )
        # English is checked initially; move to Hindi, select, then save.
        keyboard.send_text("\x1b[B \r")
        cli.configure_subtitle_languages()
    save.assert_called_once_with({"subtitle_languages": ["en", "hi"]})


def test_invalid_cancelled_and_list_commands_do_not_save(monkeypatch):
    import pinak.cli as cli

    save = Mock()
    monkeypatch.setattr(cli, "save_config", save)
    monkeypatch.setattr(cli.questionary, "checkbox", lambda *a, **kw: object())
    monkeypatch.setattr(cli, "ask_with_esc", lambda prompt: None)
    cli.configure_subtitle_languages()
    cli.configure_subtitle_languages("en hi es fr")
    cli.configure_subtitle_languages("all")
    cli.configure_subtitle_languages("list")
    save.assert_not_called()


def test_failed_save_keeps_previous_preference(monkeypatch):
    import pinak.cli as cli

    monkeypatch.setitem(cli.config, "subtitle_languages", ["en"])

    def fail_save(changes):
        cli.config.update(changes)
        return False

    monkeypatch.setattr(cli, "save_config", fail_save)
    cli.configure_subtitle_languages("hi")
    assert cli.config["subtitle_languages"] == ["en"]


def test_repl_routes_language_preferences_and_explicit_subtitle_toggle(monkeypatch):
    import pinak.cli as cli

    monkeypatch.setitem(cli.config, "username", "tester")
    monkeypatch.setitem(cli.config, "embed_subs", False)
    monkeypatch.setitem(cli.config, "subtitle_languages", ["en"])
    monkeypatch.setattr(cli, "PromptSession", None)
    monkeypatch.setattr(cli, "maybe_print_offline_notice", lambda *a, **kw: True)
    saved = []

    def save(changes=None):
        if changes:
            cli.config.update(changes)
        saved.append((cli.config["embed_subs"], cli.config["subtitle_languages"]))
        return True

    monkeypatch.setattr(cli, "save_config", save)
    commands = iter(["/subs_lang hi en", "/subs on", "/subs on", "/subs off", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *args: next(commands))
    cli.repl_loop()
    assert saved[:4] == [
        (False, ["hi", "en"]),
        (True, ["hi", "en"]),
        (True, ["hi", "en"]),
        (False, ["hi", "en"]),
    ]
