"""Cloud archives preserve deployment dotfiles and exclude local secrets."""

from __future__ import annotations

import hashlib
import importlib
import sys
import zipfile
from pathlib import Path

import pytest


def test_cloud_archive_excludes_local_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools = Path(__file__).resolve().parents[1] / "tools"
    monkeypatch.syspath_prepend(str(tools))
    package = importlib.import_module("package_cloud")
    project = tmp_path / "source"
    docs = project / "MCP(cloud)"
    examples = docs / "examples"
    examples.mkdir(parents=True)
    (docs / "README.md").write_text("[Local MCP](<../MCP(Local)/README.md>)", encoding="utf-8")
    for name in package.TEMPLATES:
        (examples / name).write_text("deployment template", encoding="utf-8")
    (examples / ".env").write_text("DO_NOT_DISTRIBUTE=private", encoding="utf-8")
    (examples / "credentials.json").write_text("private", encoding="utf-8")
    (project / "cli").mkdir()
    (project / "cli/requirements-cloud-lock.txt").write_text("lock", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "pinak_cli-2.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for module in (
            "__init__.py",
            "engine.py",
            "queue.py",
            "history.py",
            "mcp_server/__main__.py",
            "mcp_cloud/app.py",
        ):
            archive.writestr("pinak/" + module, "# runtime fixture")
        archive.writestr(
            "pinak_cli-2.0.0.dist-info/METADATA",
            "Name: pinak-cli\nVersion: 2.0.0\nProvides-Extra: mcp\n",
        )
        archive.writestr(
            "pinak_cli-2.0.0.dist-info/entry_points.txt",
            "[console_scripts]\npinak-mcp = pinak.mcp_server.__main__:main\n",
        )
    output, zipped = tmp_path / "bundle", tmp_path / "installer.zip"
    monkeypatch.setattr(package, "__file__", str(project / "cli/tools/package_cloud.py"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "package_cloud.py",
            str(dist),
            "--output",
            str(output),
            "--source-revision",
            "local-test",
            "--archive",
            str(zipped),
        ],
    )
    package.main()
    with zipfile.ZipFile(zipped) as archive:
        names = set(archive.namelist())
        assert b"/MCP%28Local%29/README.md" in archive.read("README.md")
        assert b"../MCP" not in archive.read("README.md")
        assert {".env.example", ".dockerignore", ".gitignore", "SHA256SUMS", wheel.name} <= names
        assert not {".env", "credentials.json"} & names
        assert b"DO_NOT_DISTRIBUTE" not in b"".join(archive.read(name) for name in names)
        for line in archive.read("SHA256SUMS").decode().splitlines():
            expected, name = line.split("  ", 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
    with pytest.raises(FileExistsError):
        package.main()


def test_cloud_archive_refuses_self_inclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    package = importlib.import_module("package_cloud")
    with pytest.raises(ValueError, match="outside"):
        package.write_archive(tmp_path, tmp_path / "installer.zip")
    assert not (tmp_path / "installer.zip").exists()
