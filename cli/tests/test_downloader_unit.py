"""Unit tests for downloader helpers: classification, resilience, duplicates."""

import pinak.downloader as dl_mod
from pinak.exceptions import DownloadFailedError, NetworkError


def test_classify_network_errors():
    err = dl_mod._classify_download_error(TimeoutError("timed out"), "https://x.com/v")
    assert isinstance(err, NetworkError)


def test_classify_instagram_errors():
    from pinak.exceptions import InstagramPrivateContentError, InstagramRateLimitedError

    assert isinstance(
        dl_mod._classify_download_error(RuntimeError("429"), "https://instagram.com/p/1"),
        InstagramRateLimitedError,
    )
    assert isinstance(
        dl_mod._classify_download_error(RuntimeError("private"), "https://instagram.com/p/1"),
        InstagramPrivateContentError,
    )


def test_classify_generic_error():
    err = dl_mod._classify_download_error(ValueError("weird"), "https://x.com/v")
    assert isinstance(err, DownloadFailedError)


def test_resilience_opts_enable_resume(monkeypatch):
    monkeypatch.setitem(dl_mod.config, "retry_count", 4)
    monkeypatch.setitem(dl_mod.config, "read_timeout", 45.0)
    opts = dl_mod._resilience_opts()
    assert opts["continuedl"] is True
    assert opts["retries"] == 4
    assert opts["fragment_retries"] == 4
    assert opts["socket_timeout"] == 45.0


def test_timeout_helpers_fallback(monkeypatch):
    monkeypatch.setitem(dl_mod.config, "read_timeout", "bogus")
    monkeypatch.setitem(dl_mod.config, "connect_timeout", "bogus")
    monkeypatch.setitem(dl_mod.config, "retry_count", "bogus")
    assert dl_mod._socket_timeout() == 30.0
    assert dl_mod._connect_timeout() == 10.0
    assert dl_mod._retry_count() == 3


def test_ytdl_logger_collects_errors():
    logger = dl_mod.YTDLLogger()
    logger.debug("ignored")
    logger.warning("ignored")
    logger.error("boom")
    assert logger.errors == ["boom"]


def test_progress_hook_finished_state():
    dl_mod.rich_progress = None
    dl_mod.rich_task = None
    # No progress attached: must be a harmless no-op.
    dl_mod.yt_dlp_progress_hook({"status": "finished"})


def test_handle_duplicate_skip_and_download(monkeypatch):
    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: True)
    monkeypatch.setitem(dl_mod.config, "duplicate_action", "skip")
    assert dl_mod.handle_duplicate("https://x.com/v", interactive=False) == "skip"
    monkeypatch.setitem(dl_mod.config, "duplicate_action", "download")
    assert dl_mod.handle_duplicate("https://x.com/v", interactive=False) == "download"


def test_handle_duplicate_unknown_url_always_downloads(monkeypatch):
    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: False)
    assert dl_mod.handle_duplicate("https://x.com/new", interactive=True) == "download"


def test_handle_duplicate_interactive_download_again(monkeypatch):
    import questionary

    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: True)
    monkeypatch.setitem(dl_mod.config, "duplicate_action", "ask")

    class _Q:
        def ask(self, **kwargs):
            return "Download again"

    monkeypatch.setattr(questionary, "select", lambda *a, **k: _Q())
    assert dl_mod.handle_duplicate("https://x.com/v", interactive=True) == "download"


def test_download_media_content_falls_back_to_info_candidate(monkeypatch, tmp_path):
    target_file = tmp_path / "sample.mp4"
    target_file.write_bytes(b"content")

    class _MockYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def extract_info(self, url, download=True):
            return {
                "id": "123",
                "title": "sample",
                "_filename": str(target_file),
            }

        def prepare_filename(self, info):
            return str(target_file)

    monkeypatch.setattr("yt_dlp.YoutubeDL", _MockYDL)
    # Simulate snapshot diff returning empty (e.g. file already existed or resumed)
    monkeypatch.setattr(dl_mod, "changed_files", lambda before, after: [])

    result = dl_mod.download_media_content("https://example.com/video", str(tmp_path))
    assert result["success"] is True
    assert str(target_file) in result["files"]


def test_handle_download_instagram_fallback_on_exception(monkeypatch, tmp_path):
    monkeypatch.setattr(dl_mod, "is_online", lambda *a, **k: True)
    monkeypatch.setattr(dl_mod, "get_platform", lambda url: "Instagram")
    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: False)
    monkeypatch.setitem(dl_mod.config, "output_dir", str(tmp_path))

    def _broken_ig(*a, **k):
        raise RuntimeError("Instagram GraphQL 500 API broken")

    monkeypatch.setattr(dl_mod, "download_instagram_media", _broken_ig)

    def _fallback_generic(url, target_dir, **k):
        return {
            "success": True,
            "url": url,
            "files": [str(tmp_path / "fallback.mp4")],
            "audio": False,
            "quality": "best",
        }

    monkeypatch.setattr(dl_mod, "download_media_content", _fallback_generic)
    result = dl_mod.handle_download("https://www.instagram.com/reel/xyz123", interactive=False)
    assert result["success"] is True
    assert str(tmp_path / "fallback.mp4") in result["files"]


def test_handle_download_instagram_fallback_on_unsuccessful_result(monkeypatch, tmp_path):
    monkeypatch.setattr(dl_mod, "is_online", lambda *a, **k: True)
    monkeypatch.setattr(dl_mod, "get_platform", lambda url: "Instagram")
    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: False)
    monkeypatch.setitem(dl_mod.config, "output_dir", str(tmp_path))

    # Scraper returned success=False (no files scraped)
    monkeypatch.setattr(
        dl_mod,
        "download_instagram_media",
        lambda *a, **k: {
            "success": False,
            "files": [],
            "url": "test",
            "audio": False,
            "quality": "best",
        },
    )

    def _fallback_generic(url, target_dir, **k):
        return {
            "success": True,
            "url": url,
            "files": [str(tmp_path / "from_generic.mp4")],
            "audio": False,
            "quality": "best",
        }

    monkeypatch.setattr(dl_mod, "download_media_content", _fallback_generic)
    result = dl_mod.handle_download("https://www.instagram.com/p/abc456", interactive=False)
    assert result["success"] is True
    assert str(tmp_path / "from_generic.mp4") in result["files"]


def test_classify_unsupported_url_error():
    from pinak.exceptions import UnsupportedLinkTypeError

    err = dl_mod._classify_download_error(
        RuntimeError("ERROR: Unsupported URL: https://google.com/"), "https://google.com/"
    )
    assert isinstance(err, UnsupportedLinkTypeError)
    assert "not an allowed link type" in str(err).lower()


def test_is_url_supported_by_ytdlp(monkeypatch):
    import yt_dlp

    from pinak.utils import is_url_supported_by_ytdlp

    # Dedicated platforms
    ok, platform = is_url_supported_by_ytdlp("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert ok is True
    assert platform.lower() == "youtube"

    # Direct media streams
    ok, platform = is_url_supported_by_ytdlp("https://example.com/media/clip.mp4?query=1")
    assert ok is True
    assert platform == "Direct Media"

    ok, platform = is_url_supported_by_ytdlp("https://example.com/stream.m3u8")
    assert ok is True
    assert platform == "Direct Media"

    # Generic webpage media (e.g. Voicy.network)
    def _mock_extract(self, url, download=False):
        if "voicy.network" in url:
            return {"title": "Sound Clip", "url": "https://files.voicy.network/sound.mp4"}
        raise yt_dlp.utils.DownloadError("Unsupported URL")

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", _mock_extract)

    ok, platform = is_url_supported_by_ytdlp(
        "https://www.voicy.network/sounds/_QemVncVbkOO53I_Wu_akA-mission-failed-well-get-em-next-time"
    )
    assert ok is True
    assert platform == "Voicy.network"

    # Unsupported URLs
    ok, reason = is_url_supported_by_ytdlp("https://google.com")
    assert ok is False
    assert "not supported by yt-dlp" in reason

    ok, reason = is_url_supported_by_ytdlp("ftp://example.com/test.mp4")
    assert ok is False
    assert "http://" in reason or "https://" in reason

    ok, reason = is_url_supported_by_ytdlp("just-random-string")
    assert ok is False

    ok, reason = is_url_supported_by_ytdlp("")
    assert ok is False


def test_handle_download_any_command_supported(monkeypatch, tmp_path):
    monkeypatch.setattr(dl_mod, "is_online", lambda *a, **k: True)
    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: False)
    monkeypatch.setitem(dl_mod.config, "output_dir", str(tmp_path))

    def _mock_dl(url, target_dir, **k):
        return {
            "success": True,
            "url": url,
            "files": [str(tmp_path / "video.mp4")],
            "audio": False,
            "quality": "best",
        }

    monkeypatch.setattr(dl_mod, "download_media_content", _mock_dl)
    result = dl_mod.handle_download(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        interactive=False,
        is_any_command=True,
    )
    assert result["success"] is True


def test_handle_download_any_command_unsupported(monkeypatch, tmp_path):
    monkeypatch.setattr(dl_mod, "is_online", lambda *a, **k: True)
    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: False)
    monkeypatch.setitem(dl_mod.config, "output_dir", str(tmp_path))

    result = dl_mod.handle_download(
        "https://google.com",
        interactive=False,
        is_any_command=True,
    )
    assert result["success"] is False
    assert result.get("error") == "unsupported_link_type"


def test_handle_download_any_command_direct_media(monkeypatch, tmp_path):
    monkeypatch.setattr(dl_mod, "is_online", lambda *a, **k: True)
    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: False)
    monkeypatch.setitem(dl_mod.config, "output_dir", str(tmp_path))

    def _mock_dl(url, target_dir, **k):
        return {
            "success": True,
            "url": url,
            "files": [str(tmp_path / "sample.mp4")],
            "audio": False,
            "quality": "best",
        }

    monkeypatch.setattr(dl_mod, "download_media_content", _mock_dl)
    result = dl_mod.handle_download(
        "https://example.com/sample.mp4",
        interactive=False,
        is_any_command=True,
    )
    assert result["success"] is True
