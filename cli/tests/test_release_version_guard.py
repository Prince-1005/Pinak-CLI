"""Publishing must reject a wrong release identity before building/uploading."""

import json
import runpy
from pathlib import Path

import pytest

validate_release = runpy.run_path(str(Path(__file__).parents[1] / "tools/check_release.py"))[
    "validate_release"
]


@pytest.fixture
def project(tmp_path):
    (tmp_path / "cli/pinak").mkdir(parents=True)
    (tmp_path / "cli/pyproject.toml").write_text('[project]\nversion = "1.4.2"\n')
    (tmp_path / "cli/pinak/__init__.py").write_text('__version__ = "1.4.2"\n')
    (tmp_path / ".release-please-manifest.json").write_text(json.dumps({"cli": "1.4.2"}))
    return tmp_path


@pytest.mark.parametrize(
    "event,tag,requested",
    [("release", "v1.4.2", ""), ("workflow_dispatch", "", "1.4.2")],
)
def test_matching_release_identity_is_accepted(project, event, tag, requested):
    assert validate_release(project, event, tag, requested) == "1.4.2"


@pytest.mark.parametrize(
    "event,tag,requested",
    [
        ("release", "v1.4.3", ""),
        ("release", "1.4.2", ""),
        ("release", "", ""),
        ("workflow_dispatch", "", ""),
        ("workflow_dispatch", "", "1.4.3"),
        ("push", "v1.4.2", "1.4.2"),
    ],
)
def test_incorrect_or_missing_release_identity_is_rejected(project, event, tag, requested):
    with pytest.raises(ValueError):
        validate_release(project, event, tag, requested)


@pytest.mark.parametrize("file", ["cli/pinak/__init__.py", ".release-please-manifest.json"])
def test_version_file_drift_is_rejected(project, file):
    target = project / file
    target.write_text(target.read_text().replace("1.4.2", "1.4.3"))
    with pytest.raises(ValueError, match="must agree"):
        validate_release(project, "release", "v1.4.2")
