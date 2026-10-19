"""SDK-independent contract and policy tests."""

import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from pinak.mcp_server.models import Add, IDs, Policy, Retry, load_policy
from pinak.mcp_server.policy import ToolFailure, clean, output_path, read_path


def test_import_does_not_import_optional_sdk():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import pinak.mcp_server; assert 'mcp' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0 and result.stdout == "", result.stderr


@pytest.mark.parametrize("ids", [[0], [-1], [True], ["1"], []])
def test_invalid_ids_rejected(ids):
    with pytest.raises(ValidationError):
        IDs(job_ids=ids, request_key="key")


def test_unknown_options_and_ambiguous_targets_rejected():
    with pytest.raises(ValidationError):
        Add(url="https://example.com/media", options={"exec": "shell"}, request_key="key")
    with pytest.raises(ValidationError):
        Retry(job_ids=[1], all_failed=True, request_key="key")


def test_output_and_read_roots(tmp_path):
    root = tmp_path / "downloads"
    policy = Policy(default_output_dir=root)
    assert output_path("nested", policy) == root / "nested"
    with pytest.raises(ToolFailure, match="outside"):
        output_path("../escape", policy)
    with pytest.raises(ToolFailure):
        read_path(str(tmp_path / "secret"), policy)
    try:
        root.mkdir()
        (root / "link").symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        return  # Native junction/symlink coverage also runs in the OS matrix.
    with pytest.raises(ToolFailure):
        output_path("link/escape", policy)


def test_config_and_redaction(tmp_path):
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"default_output_dir": str(tmp_path)}))
    assert load_policy(config).default_output_dir == tmp_path
    value = clean("https://user:password@example.com/video?token=secret#private password=secret")
    assert "secret" not in value and "user:" not in value and "#private" not in value
