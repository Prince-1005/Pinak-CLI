"""Client configuration generation never clobbers other servers or malformed JSON."""

import json
from pathlib import Path

import pytest

from pinak.mcp_server import setup


def test_preview_does_not_write_and_apply_preserves_others(tmp_path, monkeypatch):
    monkeypatch.setenv("PINAK_MCP_CONFIG", str(tmp_path / "policy.json"))
    target = tmp_path / "client dir" / "config.json"
    preview = setup.configure_client(str(target))
    assert not target.exists() and not preview["applied"]
    target.parent.mkdir()
    original = {
        "other": 42,
        "mcpServers": {"existing": {"command": "keep", "env": {"secret": "keep private"}}},
    }
    target.write_text(json.dumps(original))
    applied = setup.configure_client(str(target), apply=True)
    assert json.loads(Path(applied["backup"]).read_text()) == original
    updated = json.loads(target.read_text())
    assert updated["mcpServers"]["existing"] == original["mcpServers"]["existing"]
    assert updated["other"] == 42
    assert setup.configure_client(str(target), apply=True)["unchanged"]
    assert len(list(target.parent.glob("*.bak"))) == 1


def test_malformed_config_is_not_overwritten(tmp_path):
    target = tmp_path / "bad.json"
    original = "{broken"
    target.write_text(original)
    with pytest.raises(ValueError):
        setup.configure_client(str(target), apply=True)
    assert target.read_text() == original


def test_failed_atomic_replace_retains_original_and_backup(tmp_path, monkeypatch):
    target = tmp_path / "config.json"
    target.write_text("{}")
    monkeypatch.setattr(
        setup.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("injected failure"))
    )
    with pytest.raises(OSError):
        setup.configure_client(str(target), apply=True)
    assert target.read_text() == "{}"
    assert len(list(tmp_path.glob("*.bak"))) == 1
