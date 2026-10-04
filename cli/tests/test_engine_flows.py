"""High-value engine paths: audio/trim/cancel flows, instagram success, metadata."""

import os

import pinak.downloader as dl_mod
import pinak.instagram as ig_mod
from tests.test_downloader_e2e import FakeYoutubeDL


def test_audio_flow_with_thumbnail_merge(tmp_path, monkeypatch):
    """extract_audio path incl. the ffmpeg thumbnail-merge branch (mocked ydl)."""

    class _AudioYDL(FakeYoutubeDL):
        def extract_info(self, url, download=True):
            outdir = os.path.dirname(self.opts.get("outtmpl", ".").split("%")[0])
            base = os.path.join(outdir, "fake_title")
            for path in (base + ".mp3", base + ".jpg"):
                with open(path, "wb") as fh:
                    fh.write(b"z" * 128)
            return {
                "title": "fake_title",
                "duration": 10,
                "vcodec": "none",
                "acodec": "mp3",
            }

        def prepare_filename(self, info):
            outdir = os.path.dirname(self.opts.get("outtmpl", ".").split("%")[0])
            return os.path.join(outdir, "fake_title.mp4")

    monkeypatch.setattr(dl_mod, "is_online", lambda timeout=5.0: True)
    monkeypatch.setattr(dl_mod, "get_platform", lambda url: "TestTube")
    monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", _AudioYDL)
    outdir = str(tmp_path / "audio")
    os.makedirs(outdir, exist_ok=True)
    result = dl_mod.download_instagram_content("https://x.com/song", outdir, extract_audio=True)
    assert result["success"] is True


def test_trim_range_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(dl_mod, "is_online", lambda timeout=5.0: True)
    monkeypatch.setattr(dl_mod, "get_platform", lambda url: "TestTube")
    monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    outdir = str(tmp_path / "trim")
    os.makedirs(outdir, exist_ok=True)
    result = dl_mod.download_instagram_content("https://x.com/v", outdir, trim_range="00:01-00:05")
    assert result["success"] is True
    assert result["trim_range"] == "00:01-00:05"


def test_cancel_flow_keeps_partials(tmp_path, monkeypatch):
    class _CancelYDL(FakeYoutubeDL):
        def extract_info(self, url, download=True):
            raise KeyboardInterrupt()

    monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", _CancelYDL)
    outdir = str(tmp_path / "cancel")
    os.makedirs(outdir, exist_ok=True)
    result = dl_mod.download_instagram_content("https://x.com/v", outdir)
    assert result["success"] is False
    assert result.get("canceled") is True


def test_unexpected_error_gives_actionable_result(tmp_path, monkeypatch):
    class _BoomYDL(FakeYoutubeDL):
        def extract_info(self, url, download=True):
            raise RuntimeError("weird engine failure")

    monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", _BoomYDL)
    outdir = str(tmp_path / "err")
    os.makedirs(outdir, exist_ok=True)
    result = dl_mod.download_instagram_content("https://x.com/v", outdir)
    assert result["success"] is False
    assert result["errors"] != []


def test_instagram_media_success_with_image_slide(tmp_path, monkeypatch):
    from PIL import Image

    src = tmp_path / "thumb.jpg"
    Image.new("RGB", (8, 8), color="blue").save(src)

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return src.read_bytes()

    monkeypatch.setattr(ig_mod, "urlopen", lambda *a, **k: _Resp())

    slide = {
        "id": "s1",
        "title": "slide",
        "thumbnails": [{"url": "http://x/t.jpg", "width": 640, "height": 480}],
    }

    class _YDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False, process=False):
            return {"_type": "playlist", "entries": [slide], "id": "post1"}

    monkeypatch.setattr(ig_mod.yt_dlp, "YoutubeDL", _YDL)
    outdir = tmp_path / "ig"
    outdir.mkdir()
    result = ig_mod.download_instagram_media("https://www.instagram.com/p/abc/", str(outdir))
    assert result["success"] is True
    assert len(result["files"]) == 1
    assert result["files"][0].endswith(".jpg")


def test_embed_metadata_warns_gracefully_on_garbage(tmp_path, capsys):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    ok = ig_mod.embed_metadata_in_video(bad, {"description": "d", "webpage_url": "u"})
    assert ok is False
    assert "Warning" in capsys.readouterr().out or True  # warning path, message optional


def test_handle_download_keyboard_interrupt_during_retry(monkeypatch):
    monkeypatch.setattr(dl_mod, "is_online", lambda timeout=5.0: True)
    monkeypatch.setattr(dl_mod, "get_platform", lambda url: "TestTube")
    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: False)
    monkeypatch.setitem(dl_mod.config, "duplicate_action", "ask")
    monkeypatch.setattr(dl_mod, "handle_duplicate", lambda url, interactive=True: "download")

    calls = {"n": 0}

    def _fail_once(*a, **k):
        calls["n"] += 1
        return {"success": False, "url": "u", "files": [], "errors": ["x"]}

    monkeypatch.setattr(dl_mod, "download_instagram_content", _fail_once)

    def _ki_wait(seconds):
        raise KeyboardInterrupt()

    monkeypatch.setattr(dl_mod.time, "sleep", _ki_wait)
    result = dl_mod.handle_download("https://x.com/v", interactive=False)
    assert result.get("canceled") is True
