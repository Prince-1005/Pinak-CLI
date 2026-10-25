"""Universal-lock audits must include hidden marker branches and fail closed."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools import audit_dependencies


def test_audit_includes_every_marker_and_distinct_version(tmp_path: Path) -> None:
    first = tmp_path / "runtime.txt"
    first.write_text(
        "# universal lock\n"
        'Pillow==13.0.0 ; python_version == "3.11" \\\n'
        "    --hash=sha256:synthetic\n"
        'Pillow==13.1.0 ; python_version >= "3.12"\n'
        'windows-only==1.0 ; sys_platform == "win32"\n'
        'linux_only==2.0 ; sys_platform == "linux"\n',
        encoding="utf-8",
    )
    second = tmp_path / "cloud.txt"
    second.write_text("pillow==13.0.0\n", encoding="utf-8")
    assert audit_dependencies.collect_pins([first, second]) == [
        "linux-only==2.0",
        "pillow==13.0.0",
        "pillow==13.1.0",
        "windows-only==1.0",
    ]


@pytest.mark.parametrize(
    "content",
    ["", "# empty\n", "pillow>=13\n", "pillow==13.*\n", "-r other.txt\n", "not a requirement"],
)
def test_audit_rejects_empty_or_unpinned_inputs(tmp_path: Path, content: str) -> None:
    lock = tmp_path / "bad.txt"
    lock.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        audit_dependencies.collect_pins([lock])


def test_audit_propagates_security_failure_and_disables_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / "lock.txt"
    lock.write_text('pillow==13.0.0 ; sys_platform == "unknown-platform"\n', encoding="utf-8")

    def fail_audit(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "--disable-pip" in command and "--strict" in command
        pins = Path(command[command.index("-r") + 1]).read_text(encoding="utf-8")
        assert pins == "pillow==13.0.0\n"
        Path(command[command.index("--output") + 1]).write_text(
            json.dumps(
                {
                    "dependencies": [
                        {"name": "pillow", "version": "13.0.0", "vulns": [{"id": "test"}]}
                    ]
                }
            )
        )
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(audit_dependencies.subprocess, "run", fail_audit)
    assert audit_dependencies.main([str(lock), "--output", str(tmp_path / "report.json")]) == 1


def test_audit_checks_all_versions_and_combines_batch_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / "lock.txt"
    lock.write_text(
        'numpy==2.4.6 ; python_version == "3.11"\nnumpy==2.5.4 ; python_version >= "3.12"\npillow==13.0.0\n'
    )
    checked: list[str] = []

    def audit(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        pins = Path(command[command.index("-r") + 1]).read_text().splitlines()
        assert len({pin.partition("==")[0] for pin in pins}) == len(pins)
        checked.extend(pins)
        entries = [
            {
                "name": pin.partition("==")[0],
                "version": pin.partition("==")[2],
                "vulns": [{"id": "synthetic"}] if pin == "numpy==2.4.6" else [],
            }
            for pin in pins
        ]
        Path(command[command.index("--output") + 1]).write_text(
            json.dumps({"dependencies": entries, "fixes": []})
        )
        return subprocess.CompletedProcess(
            command, 1 if any(entry["vulns"] for entry in entries) else 0
        )

    monkeypatch.setattr(audit_dependencies.subprocess, "run", audit)
    output = tmp_path / "report.json"
    assert audit_dependencies.main([str(lock), "--output", str(output)]) == 1
    assert sorted(checked) == ["numpy==2.4.6", "numpy==2.5.4", "pillow==13.0.0"]
    report = json.loads(output.read_text())
    assert len(report["dependencies"]) == 3
    assert report["dependencies"][0]["vulns"] == [{"id": "synthetic"}]


@pytest.mark.parametrize("failure", ["exit", "missing", "skipped", "malformed"])
def test_audit_rejects_incomplete_or_failed_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    lock = tmp_path / "lock.txt"
    lock.write_text("pillow==13.0.0\n")

    def audit(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        entries = (
            []
            if failure == "missing"
            else [
                {
                    "name": "pillow",
                    "version": "13.0.0",
                    "skip_reason": "unavailable" if failure == "skipped" else None,
                }
            ]
        )
        Path(command[command.index("--output") + 1]).write_text(
            "not JSON" if failure == "malformed" else json.dumps({"dependencies": entries})
        )
        return subprocess.CompletedProcess(command, 2 if failure == "exit" else 0)

    monkeypatch.setattr(audit_dependencies.subprocess, "run", audit)
    assert audit_dependencies.main([str(lock), "--output", str(tmp_path / "report.json")]) == 2
