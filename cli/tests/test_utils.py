"""Unit tests for pinak.utils — pure helpers with no network/FFmpeg."""

import os

from pinak import utils


def test_human_size_bytes():
    assert utils.human_size(0) == "0 B"
    assert utils.human_size(512) == "512.0 B"
    assert utils.human_size(1024) == "1.0 KB"
    assert utils.human_size(1024 * 1024) == "1.0 MB"


def test_human_size_invalid():
    assert utils.human_size(None) == "0 B"
    assert utils.human_size("not-a-number") == "unknown"


def test_human_duration_seconds():
    assert utils.human_duration(45) == "45s"
    assert utils.human_duration(90) == "1m 30s"
    assert utils.human_duration(3661) == "1h 1m 1s"


def test_human_duration_invalid():
    assert utils.human_duration(None) == "unknown"
    assert utils.human_duration("abc") == "unknown"


def test_normalize_quality_aliases():
    assert utils.normalize_quality("best") == "best"
    assert utils.normalize_quality("worst") == "worst"
    assert utils.normalize_quality("mp3") == "audio"
    assert utils.normalize_quality("audio") == "audio"


def test_normalize_quality_resolution():
    assert utils.normalize_quality("720p") == "720p"
    assert utils.normalize_quality("1080") == "1080p"
    assert utils.normalize_quality("  480P  ") == "480p"


def test_normalize_quality_invalid():
    assert utils.normalize_quality("super-hd") is None
    assert utils.normalize_quality("") == "best"


def test_video_format_for_quality():
    assert utils.video_format_for_quality("best") == "bestvideo+bestaudio/best"
    assert utils.video_format_for_quality("worst") == "worst"
    fmt = utils.video_format_for_quality("720p")
    assert "720" in fmt and "bestaudio" in fmt

    # Fallback when FFmpeg is not installed
    assert utils.video_format_for_quality("best", has_ffmpeg=False) == "best[ext=mp4]/best"
    assert utils.video_format_for_quality("worst", has_ffmpeg=False) == "worst"
    fmt_no_ffmpeg = utils.video_format_for_quality("720p", has_ffmpeg=False)
    assert "720" in fmt_no_ffmpeg and "bestaudio" not in fmt_no_ffmpeg


def test_sanitize_filename_removes_illegal_chars():
    assert utils.sanitize_filename('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"
    assert utils.sanitize_filename("  ") == "untitled"
    assert utils.sanitize_filename("") == "untitled"


def test_sanitize_filename_truncates():
    long_name = "x" * 300
    assert len(utils.sanitize_filename(long_name)) <= 180


def test_changed_files_detects_new_and_modified(tmp_path):
    before = {"/a.mp4": 1.0, "/b.mp4": 2.0}
    after = {"/a.mp4": 1.0, "/b.mp4": 3.0, "/c.mp4": 4.0}
    changed = utils.changed_files(before, after)
    assert changed == ["/b.mp4", "/c.mp4"]


def test_changed_files_detects_size_change_with_same_mtime():
    before = {"/a.mp4": (100.0, 1024)}
    after = {"/a.mp4": (100.0, 4096), "/b.mp4": (100.0, 2048)}
    changed = utils.changed_files(before, after)
    assert changed == ["/a.mp4", "/b.mp4"]


def test_get_all_files_returns_mtime_and_size(tmp_path):
    f = tmp_path / "video.mp4"
    f.write_bytes(b"hello world")
    snap = utils.get_file_snapshot(str(tmp_path))
    assert str(f) in snap
    mtime, size = snap[str(f)]
    assert isinstance(mtime, float)
    assert size == len(b"hello world")


def test_get_file_snapshot_missing_folder(tmp_path):
    missing = str(tmp_path / "does-not-exist")
    assert utils.get_file_snapshot(missing) == {}


def test_get_ffmpeg_path_returns_string():
    # Must never raise; always returns *something* usable.
    path = utils.get_ffmpeg_path()
    assert isinstance(path, str) and len(path) > 0
    probe = utils.get_ffprobe_path()
    assert isinstance(probe, str) and len(probe) > 0


def test_get_platform_candidate_dirs():
    dirs = utils._get_platform_candidate_dirs()
    assert isinstance(dirs, list)
    for d in dirs:
        assert os.path.isdir(d)


def test_resolve_binary_from_candidate_dirs(monkeypatch, tmp_path):
    custom_bin_dir = tmp_path / "custom_tools"
    custom_bin_dir.mkdir()
    fake_ffmpeg = custom_bin_dir / "ffmpeg.exe"
    fake_ffmpeg.write_text("binary", encoding="utf-8")
    fake_ffmpeg.chmod(0o755)

    monkeypatch.setattr(utils.shutil, "which", lambda name: None)
    monkeypatch.setattr(utils, "script_dir", lambda: str(tmp_path / "empty"))
    monkeypatch.setattr(utils, "_get_platform_candidate_dirs", lambda: [str(custom_bin_dir)])

    resolved = utils._resolve_binary(("ffmpeg.exe", "ffmpeg"))
    assert resolved == str(fake_ffmpeg)


def test_trusted_which_ignores_cwd_and_relative_path(tmp_path, monkeypatch):
    cwd = tmp_path / "work"
    cwd.mkdir()
    decoy = cwd / "decoy.exe"
    decoy.write_text("decoy", encoding="utf-8")
    decoy.chmod(0o755)

    rel_dir = cwd / "sub"
    rel_dir.mkdir()
    rel_decoy = rel_dir / "rel_decoy.exe"
    rel_decoy.write_text("rel", encoding="utf-8")
    rel_decoy.chmod(0o755)

    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", f".{os.pathsep}sub{os.pathsep}{str(cwd)}")
    assert utils.trusted_which("decoy.exe") is None
    assert utils.trusted_which("rel_decoy.exe") is None

    safe_dir = tmp_path / "safe_bin"
    safe_dir.mkdir()
    good = safe_dir / "good.exe"
    good.write_text("good", encoding="utf-8")
    good.chmod(0o755)
    monkeypatch.setenv("PATH", str(safe_dir))
    assert utils.trusted_which("good.exe") == str(good)
