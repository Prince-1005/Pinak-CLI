"""Deeper engine-path tests: instagram entries, summary rendering, ffmpeg setup."""

import pinak.downloader as dl_mod
import pinak.ffmpeg_setup as ff_mod
import pinak.instagram as ig_mod


def _image_entry(slide_id="img1"):
    return {
        "id": slide_id,
        "title": "pic",
        "thumbnails": [{"url": "http://x/img.jpg", "width": 800, "height": 600}],
    }


def test_download_image_entry_end_to_end(tmp_path, monkeypatch):
    from PIL import Image

    src = tmp_path / "src.jpg"
    Image.new("RGB", (8, 8), color="red").save(src)

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return src.read_bytes()

    monkeypatch.setattr(ig_mod, "urlopen", lambda *a, **k: _Resp())

    class _YDL:
        def extract_info(self, *a, **k):
            return {"id": "img1"}

    outdir = tmp_path / "out"
    outdir.mkdir()
    ig_mod._download_entry(_YDL(), _image_entry(), outdir, 1, "", {"id": "1", "title": "t"})
    jpgs = list(outdir.glob("*.jpg"))
    assert len(jpgs) == 1
    assert Image.open(jpgs[0]).size == (8, 8)


def test_download_video_entry_uses_ydl(tmp_path, monkeypatch):
    processed = []

    class _YDL:
        def process_video_result(self, entry, download=True):
            processed.append(entry["id"])
            target = tmp_path / "out" / f"{entry['id']}.mp4"
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(b"v" * 64)

    outdir = tmp_path / "out"
    outdir.mkdir()
    monkeypatch.setattr(ig_mod, "embed_metadata_in_video", lambda p, m: None)
    entry = {"id": "v9", "formats": [{"url": "http://x/v", "vcodec": "h264"}]}
    ig_mod._download_entry(_YDL(), entry, outdir, 1, "", {})
    assert processed == ["v9"]
    assert (outdir / "v9.mp4").exists()


def test_single_info_download_entry(tmp_path, monkeypatch):
    """Non-playlist info takes the single-entry path."""
    seen = []

    class _YDL:
        def process_video_result(self, entry, download=True):
            seen.append(entry["id"])

    monkeypatch.setattr(ig_mod, "embed_metadata_in_video", lambda p, m: None)
    outdir = tmp_path / "out"
    outdir.mkdir()
    entry = {"id": "solo", "formats": [{"url": "http://x/v", "vcodec": "h264"}]}
    ig_mod._download_extracted_info(_YDL(), entry, outdir, "", {})
    assert seen == ["solo"]


def test_single_info_download_entry_ie_result_fallback(tmp_path, monkeypatch):
    """Non-playlist info can use process_ie_result when process_video_result is absent."""
    seen = []

    class _YDL:
        def process_ie_result(self, entry, download=True):
            seen.append(entry["id"])

    monkeypatch.setattr(ig_mod, "embed_metadata_in_video", lambda p, m: None)
    outdir = tmp_path / "out"
    outdir.mkdir()
    entry = {"id": "ie_only", "formats": [{"url": "http://x/v", "vcodec": "h264"}]}
    ig_mod._download_extracted_info(_YDL(), entry, outdir, "", {})
    assert seen == ["ie_only"]


def test_print_download_summary_variants(tmp_path, capsys):
    f1 = tmp_path / "clip.mp4"
    f1.write_bytes(b"x" * 100)
    base = {
        "url": "https://x.com/v",
        "info": {"duration": 61},
        "files": [str(f1)],
        "errors": [],
    }
    dl_mod.print_download_summary({**base, "success": True, "audio": False, "quality": "720p"})
    dl_mod.print_download_summary({**base, "success": False, "audio": True})
    dl_mod.print_download_summary({**base, "success": False, "canceled": True, "files": []})
    assert "SUCCESS" in capsys.readouterr().out


def test_handle_download_duplicate_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(dl_mod, "is_online", lambda timeout=5.0: True)
    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: True)
    monkeypatch.setitem(dl_mod.config, "duplicate_action", "skip")
    result = dl_mod.handle_download("https://x.com/dup", interactive=False)
    assert result["success"] is True and result["files"] == []


def test_is_executable_variants(tmp_path, monkeypatch):
    assert ff_mod._is_executable("") is False
    assert ff_mod._is_executable("/nonexistent/zzz") is False
    binary = tmp_path / "ffmpeg"
    binary.write_bytes(b"x")
    binary.chmod(0o755)
    assert ff_mod._is_executable(str(binary)) is True
    monkeypatch.setattr(ff_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    assert ff_mod._is_executable("ffmpeg") is True


def test_try_static_ffmpeg_without_package(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "static_ffmpeg", None)
    assert ff_mod._try_static_ffmpeg() is False


def test_try_static_ffmpeg_success_with_fake_package(tmp_path, monkeypatch):
    import sys
    import types

    fake_bin = tmp_path / "ffmpeg"
    fake_bin.write_bytes(b"x")
    fake_bin.chmod(0o755)
    fake_mod = types.ModuleType("static_ffmpeg")
    fake_mod.add_paths = lambda: True  # noqa: E731
    monkeypatch.setitem(sys.modules, "static_ffmpeg", fake_mod)
    monkeypatch.setattr(ff_mod.shutil, "which", lambda name: str(fake_bin))
    assert ff_mod._try_static_ffmpeg() is True


def test_ensure_ffmpeg_uses_fetched_binary(tmp_path, monkeypatch):
    import sys
    import types

    fake_bin = tmp_path / "ffmpeg"
    fake_bin.write_bytes(b"x")
    fake_bin.chmod(0o755)
    fake_mod = types.ModuleType("static_ffmpeg")
    fake_mod.add_paths = lambda: True  # noqa: E731
    monkeypatch.setitem(sys.modules, "static_ffmpeg", fake_mod)
    monkeypatch.setattr(ff_mod, "get_ffmpeg_path", lambda: str(fake_bin))
    monkeypatch.setattr(ff_mod.shutil, "which", lambda name: str(fake_bin))
    assert ff_mod.ensure_ffmpeg() == str(fake_bin)


def test_try_static_ffmpeg_broken_package(monkeypatch):
    import sys
    import types

    fake_mod = types.ModuleType("static_ffmpeg")

    def _boom():
        raise RuntimeError("fetch failed")

    fake_mod.add_paths = _boom
    monkeypatch.setitem(sys.modules, "static_ffmpeg", fake_mod)
    assert ff_mod._try_static_ffmpeg() is False


def test_ensure_ffprobe_fetch_path(tmp_path, monkeypatch):
    import sys
    import types

    fake_probe = tmp_path / "ffprobe"
    fake_probe.write_bytes(b"x")
    fake_mod = types.ModuleType("static_ffmpeg")
    fake_mod.add_paths = lambda: True  # noqa: E731
    monkeypatch.setitem(sys.modules, "static_ffmpeg", fake_mod)
    monkeypatch.setattr(ff_mod, "get_ffprobe_path", lambda: "/nonexistent/ffprobe")
    monkeypatch.setattr(ff_mod.shutil, "which", lambda name: None)
    # Nothing fetchable -> falls back to the unresolved path, never raises.
    assert ff_mod.ensure_ffprobe() == "/nonexistent/ffprobe"


def test_ensure_ffprobe_existing(tmp_path, monkeypatch):
    probe = tmp_path / "ffprobe"
    probe.write_bytes(b"x")
    probe.chmod(0o755)
    monkeypatch.setattr(ff_mod, "get_ffprobe_path", lambda: str(probe))
    assert ff_mod.ensure_ffprobe() == str(probe)
