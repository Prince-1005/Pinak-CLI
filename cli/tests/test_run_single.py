"""Direct tests for commands.run_single validation and plan building."""

import json

import pinak.commands.run as run_mod


def test_build_plan_audio_branch(monkeypatch):
    monkeypatch.setitem(run_mod.config, "audio_format", "mp3")
    monkeypatch.setitem(run_mod.config, "audio_quality", "320")
    plan = run_mod.build_plan("https://x.com/v", True, "audio", "/tmp/out")
    assert plan["mode"] == "audio"
    assert plan["format"] == "mp3"
    assert "320" in plan["quality"]


def test_build_plan_video_branch():
    plan = run_mod.build_plan("https://x.com/v", False, "720p", "/tmp/out")
    assert plan["mode"] == "video"
    assert plan["quality"] == "720p"


def test_result_to_jsonable_with_files(tmp_path, monkeypatch):
    f1 = tmp_path / "a.mp4"
    f1.write_bytes(b"x" * 10)
    monkeypatch.setattr(run_mod, "get_platform", lambda url: "TestTube")
    payload = run_mod.result_to_jsonable(
        {
            "success": True,
            "canceled": False,
            "url": "https://x.com/v",
            "audio": False,
            "quality": "best",
            "info": {"duration": 30},
            "files": [str(f1), str(tmp_path / "missing.mp4")],
            "errors": [],
        }
    )
    assert payload["success"] is True
    assert payload["files"][0]["size"] == 10
    assert payload["files"][1]["size"] is None


def test_result_to_jsonable_tolerates_stat_errors(monkeypatch):
    monkeypatch.setattr(run_mod, "get_platform", lambda url: "TestTube")

    def _boom(path):
        raise OSError("stat failed")

    monkeypatch.setattr(run_mod.os.path, "getsize", _boom)
    monkeypatch.setattr(run_mod.os.path, "exists", lambda path: True)
    payload = run_mod.result_to_jsonable(
        {
            "success": False,
            "url": "https://x.com/v",
            "audio": True,
            "quality": "audio",
            "info": {},
            "files": ["/some/file.mp4"],
            "errors": ["x"],
        }
    )
    assert payload["files"][0]["size"] is None
    assert payload["error_count"] == 1


def test_run_single_validations():
    assert run_mod.run_single(None, None, False, False, None, False, False, False, False) == 1
    assert run_mod.run_single("notaurl", None, False, False, None, False, False, False, False) == 1
    assert (
        run_mod.run_single(
            "https://x.com/v",
            None,
            False,
            False,
            "garbage-q",
            False,
            False,
            False,
            False,
        )
        == 1
    )


def test_run_single_output_is_temporary(monkeypatch, tmp_path, capsys):
    saved = {}
    monkeypatch.setattr("pinak.config.save_config", lambda: saved.setdefault("ok", True))
    previous_output = run_mod.config["output_dir"]
    monkeypatch.setattr(run_mod, "get_platform", lambda url: "TestTube")
    code = run_mod.run_single(
        "https://x.com/v",
        str(tmp_path),
        False,
        False,
        "best",
        False,
        False,
        True,
        False,
    )
    assert code == 0
    assert not saved
    assert run_mod.config["output_dir"] == previous_output
    assert "Dry Run" in capsys.readouterr().out


def test_render_plan_json(capsys):
    run_mod.render_plan(
        {
            "url": "u",
            "platform": "p",
            "mode": "video",
            "quality": "best",
            "format": "mp4",
            "output_dir": "/o",
        },
        as_json=True,
    )
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
