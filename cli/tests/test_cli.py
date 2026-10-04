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
