"""CLI integration tests via Typer's CliRunner (no network downloads)."""

from typer.testing import CliRunner

import pinak.commands.run as run_mod
from pinak.cli import app

runner = CliRunner()


def test_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "usage" in result.output.lower()


def test_invalid_url_rejected():
    result = runner.invoke(app, ["notaurl"])
    assert result.exit_code == 1
    assert "http" in result.output.lower()


def test_invalid_quality_rejected():
    result = runner.invoke(app, ["https://example.com/v", "--quality", "super-hd"])
    assert result.exit_code == 1
    assert "quality" in result.output.lower()


def test_single_command_routing(monkeypatch):
    """Single-command mode must route parsed flags into handle_download (mocked)."""
    calls = {}

    def fake_handle_download(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return {"success": True, "url": url, "files": []}

    monkeypatch.setattr(run_mod, "handle_download", fake_handle_download)
    for args in (
        ["https://example.com/v", "--quality", "720p"],
        ["--quality", "720p", "https://example.com/v"],
    ):
        calls.clear()
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        assert calls["url"] == "https://example.com/v"
        assert calls["quality"] == "720p"
        assert calls["extract_audio"] is False
        assert calls["interactive"] is False


def test_audio_flag_maps_to_extract_audio(monkeypatch):
    calls = {}

    def fake_handle_download(url, **kwargs):
        calls.update(kwargs)
        return {"success": True, "url": url, "files": []}

    monkeypatch.setattr(run_mod, "handle_download", fake_handle_download)
    result = runner.invoke(app, ["https://example.com/v", "--audio"])
    assert result.exit_code == 0, result.output
    assert calls["extract_audio"] is True


def test_version_flag():
    from pinak import __version__

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_failed_download_exits_nonzero(monkeypatch):
    def fake_fail(url, **kwargs):
        return {"success": False, "url": url, "files": [], "errors": ["boom"]}

    monkeypatch.setattr(run_mod, "handle_download", fake_fail)
    result = runner.invoke(app, ["https://example.com/v"])
    assert result.exit_code == 1


def test_dry_run_does_not_download(monkeypatch):
    def explode(url, **kwargs):
        raise AssertionError("must not download during --dry-run")

    monkeypatch.setattr(run_mod, "handle_download", explode)
    monkeypatch.setattr(run_mod, "get_platform", lambda url: "TestTube")
    result = runner.invoke(app, ["https://example.com/v", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "TestTube" in result.output or "example.com" in result.output


def test_dry_run_json_is_machine_readable(monkeypatch):
    import json

    monkeypatch.setattr(run_mod, "get_platform", lambda url: "TestTube")
    result = runner.invoke(app, ["https://example.com/v", "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["url"] == "https://example.com/v"


def test_json_output_shape(monkeypatch, tmp_path):
    import json

    def fake_ok(url, **kwargs):
        return {
            "success": True,
            "url": url,
            "audio": False,
            "quality": "best",
            "info": {"duration": 60},
            "files": [],
            "errors": [],
        }

    monkeypatch.setattr(run_mod, "handle_download", fake_ok)
    monkeypatch.setattr(run_mod, "get_platform", lambda url: "TestTube")
    result = runner.invoke(app, ["https://example.com/v", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["success"] is True
    assert payload["platform"] == "TestTube"


def test_ask_with_esc_fallback_to_input(monkeypatch):
    from pinak.cli import ask_with_esc

    class _BrokenPrompt:
        message = "Prompt:"

        def ask(self, **kwargs):
            raise RuntimeError("Terminal not connected to TTY")

    monkeypatch.setattr("builtins.input", lambda prompt: "fallback-value")
    result = ask_with_esc(_BrokenPrompt())
    assert result == "fallback-value"


def test_cli_any_subcommand_routes(monkeypatch):
    calls = {}

    def fake_handle_download(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return {"success": True, "url": url, "files": []}

    monkeypatch.setattr(run_mod, "handle_download", fake_handle_download)
    result = runner.invoke(app, ["any", "https://example.com/v"])
    assert result.exit_code == 0, result.output
    assert calls["url"] == "https://example.com/v"
    assert calls["is_any_command"] is True


def test_cli_any_option_routes(monkeypatch):
    calls = {}

    def fake_handle_download(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return {"success": True, "url": url, "files": []}

    monkeypatch.setattr(run_mod, "handle_download", fake_handle_download)
    result = runner.invoke(app, ["https://example.com/v", "--any"])
    assert result.exit_code == 0, result.output
    assert calls["url"] == "https://example.com/v"
    assert calls["is_any_command"] is True


def test_cli_any_without_url():
    result = runner.invoke(app, ["any"])
    assert result.exit_code == 1
    assert "url is required" in result.output.lower()


def test_repl_any_commands_dispatch(monkeypatch):
    import pinak.cli as cli_mod

    calls = []

    def fake_handle_download(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return {"success": True, "url": url, "files": []}

    monkeypatch.setattr(cli_mod, "handle_download", fake_handle_download)
    monkeypatch.setitem(cli_mod.config, "username", "tester")
    monkeypatch.setattr(cli_mod, "maybe_print_offline_notice", lambda *a, **k: True)

    inputs = iter(["/any https://example.com/v1", "any https://example.com/v2", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    # Run repl_loop without prompt_toolkit session
    monkeypatch.setattr(cli_mod, "PromptSession", None)
    cli_mod.repl_loop()

    assert len(calls) == 2
    assert calls[0]["url"] == "https://example.com/v1"
    assert calls[0]["is_any_command"] is True
    assert calls[1]["url"] == "https://example.com/v2"
    assert calls[1]["is_any_command"] is True


def test_repl_bare_any_prompts(monkeypatch):
    import pinak.cli as cli_mod

    calls = []

    def fake_handle_download(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return {"success": True, "url": url, "files": []}

    monkeypatch.setattr(cli_mod, "handle_download", fake_handle_download)
    monkeypatch.setitem(cli_mod.config, "username", "tester")
    monkeypatch.setattr(cli_mod, "maybe_print_offline_notice", lambda *a, **k: True)

    inputs = iter(
        [
            "/any",
            "https://example.com/prompted1",
            "any",
            "https://example.com/prompted2",
            "/any",
            "",
            "/exit",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    monkeypatch.setattr(cli_mod, "PromptSession", None)
    cli_mod.repl_loop()

    assert len(calls) == 2
    assert calls[0]["url"] == "https://example.com/prompted1"
    assert calls[0]["is_any_command"] is True
    assert calls[1]["url"] == "https://example.com/prompted2"
    assert calls[1]["is_any_command"] is True


def test_cli_media_command_flags(monkeypatch):
    """Verifies that extra arguments and flags like --window and --standalone are accepted and forwarded."""
    import pinak.commands.media as media_mod

    captured_args = []

    def fake_handle_media(args, **kwargs):
        captured_args.append(list(args))

    monkeypatch.setattr(media_mod, "handle_media_command", fake_handle_media)
    monkeypatch.setattr(media_mod, "handle_play_command", fake_handle_media)

    result = runner.invoke(app, ["media", "sample.mp4", "--window"])
    assert result.exit_code == 0
    assert len(captured_args) == 1
    assert "sample.mp4" in captured_args[0]
    assert "--window" in captured_args[0]

    captured_args.clear()
    result = runner.invoke(app, ["play", "video.mkv", "--standalone", "--gui"])
    assert result.exit_code == 0
    assert len(captured_args) == 1
    assert "video.mkv" in captured_args[0]
    assert "--standalone" in captured_args[0]


def test_cli_ctl_command(monkeypatch):
    """Verifies that pinak ctl routes commands to MediaIPCClient (DEAD-04)."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.send_command.return_value = {"error": "success", "data": 15.5}
    mock_client.seek_relative.return_value = 42.0
    mock_client.get_playback_time.return_value = 15.5

    monkeypatch.setattr("pinak.commands.control.MediaIPCClient", lambda *a, **k: mock_client)

    # 1. ctl pause
    res = runner.invoke(app, ["ctl", "pause"])
    assert res.exit_code == 0
    mock_client.send_command.assert_called_with("set_property", "pause", True)

    # 2. ctl seek +10
    res = runner.invoke(app, ["ctl", "seek", "10"])
    assert res.exit_code == 0
    mock_client.send_command.assert_called_with("seek", 10.0, "relative")

    # 3. ctl time
    res = runner.invoke(app, ["ctl", "time"])
    assert res.exit_code == 0
    mock_client.send_command.assert_called_with("get_property", "playback-time")

    # 4. ctl quit
    res = runner.invoke(app, ["ctl", "quit"])
    assert res.exit_code == 0
    mock_client.send_command.assert_called_with("quit")
