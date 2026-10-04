"""Unit tests for pinak.utils — pure helpers with no network/FFmpeg."""

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


def test_get_file_snapshot_missing_folder(tmp_path):
    missing = str(tmp_path / "does-not-exist")
    assert utils.get_file_snapshot(missing) == {}


def test_get_ffmpeg_path_returns_string():
    # Must never raise; always returns *something* usable.
    path = utils.get_ffmpeg_path()
    assert isinstance(path, str) and len(path) > 0
    probe = utils.get_ffprobe_path()
    assert isinstance(probe, str) and len(probe) > 0
