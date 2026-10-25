"""Unit tests for downloader helpers: classification, resilience, duplicates."""

from io import StringIO

import pytest
from rich.console import Console

import pinak.downloader as dl_mod
from pinak.exceptions import DownloadFailedError, NetworkError, RateLimitedError


def test_classify_network_errors():
    err = dl_mod._classify_download_error(TimeoutError("timed out"), "https://x.com/v")
    assert isinstance(err, NetworkError)


def test_classify_rate_limit_separately_from_connection_failure():
    err = dl_mod._classify_download_error(
        RuntimeError("HTTP Error 429: Too Many Requests"), "https://youtu.be/example"
    )
    assert isinstance(err, RateLimitedError)
    assert "cooldown" in err.hint
    assert "internet connection" not in err.hint


@pytest.mark.parametrize(
    ("manual", "automatic", "preferred", "expected"),
    [
        (["hi", "en"], ["ab-ar", "en", "fr"], ["en"], ["en"]),
        ([], ["ab-ar", "en", "fr"], ["en", "hi"], ["en"]),
        (["en-US", "hi"], [], ["en-US", "hi"], ["en-US", "hi"]),
        (["hi"], [], ["en"], []),
        (["hi", "es", "en"], ["en", "fr"], ["hi", "en", "es"], ["hi", "en", "es"]),
        (
            ["en", "hi", "es", "fr", "de", "it", "ja", "ko"],
            ["en", "hi", "es", "fr", "de", "it", "ja", "ko", "ab-ar"],
            ["hi", "en", "es"],
            ["hi", "en", "es"],
        ),
        ([], [], ["en"], []),
    ],
)
def test_subtitles_download_only_available_preferred_languages(
    monkeypatch, tmp_path, manual, automatic, preferred, expected
):
    real_ydl = dl_mod.yt_dlp.YoutubeDL
    selected = []
    target_file = tmp_path / "sample.mp4"
    monkeypatch.setitem(dl_mod.config, "embed_subs", True)
    monkeypatch.setitem(dl_mod.config, "subtitle_languages", preferred)
    monkeypatch.setitem(dl_mod.config, "auto_sort", False)
    monkeypatch.setattr(dl_mod, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(dl_mod, "get_ffmpeg_path", lambda: "ffmpeg")

    class SubtitleYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download=True):
            # Exercise the actual dependency's selection without network I/O.
            track = [{"ext": "vtt", "url": "https://example.com/captions.vtt"}]
            # Keep dependency startup warnings out of the mocked download's
            # error collector; only subtitle selection runs in this instance.
            with real_ydl({**self.opts, "logger": dl_mod.YTDLLogger()}) as ydl:
                subtitles = ydl.process_subtitles(
                    "example", dict.fromkeys(manual, track), dict.fromkeys(automatic, track)
                )
            selected.extend(subtitles or {})
            target_file.write_bytes(b"media")
            return {"id": "example", "title": "sample", "filepath": str(target_file)}

        def prepare_filename(self, info):
            return str(target_file)

    monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", SubtitleYDL)
    result = dl_mod.download_media_content("https://youtu.be/example", str(tmp_path))
    assert selected == expected
    assert result["success"] is True, result["errors"]


def test_subtitle_429_stops_outer_retries(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(dl_mod, "is_online", lambda *a, **k: True)
    monkeypatch.setattr(dl_mod, "get_platform", lambda url: "Youtube")
    monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: False)
    monkeypatch.setattr(dl_mod, "get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(dl_mod, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(dl_mod, "record_download", lambda *a, **k: None)
    monkeypatch.setitem(dl_mod.config, "embed_subs", True)
    monkeypatch.setitem(dl_mod.config, "output_dir", str(tmp_path))
    monkeypatch.setitem(dl_mod.config, "retry_count", 3)

    def unexpected_retry(*args):
        pytest.fail("A rate-limited download must not immediately retry")

    monkeypatch.setattr(dl_mod, "sleep_with_interrupt", unexpected_retry)

    class RateLimitedYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download=True):
            calls.append(url)
            raise RuntimeError(
                "Unable to download video subtitles for 'en': HTTP Error 429: Too Many Requests"
            )

    monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", RateLimitedYDL)
    result = dl_mod.handle_download("https://youtu.be/example", interactive=False)
    assert result["success"] is False
    assert result["rate_limited"] is True
    assert len(calls) == 1


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
    monkeypatch.setitem(dl_mod.config, "connect_timeout", 60.0)
    opts = dl_mod._resilience_opts()
    assert opts["continuedl"] is True
    assert opts["retries"] == 4
    assert opts["fragment_retries"] == 4
    assert opts["socket_timeout"] == 45.0
    monkeypatch.setitem(dl_mod.config, "connect_timeout", 8.0)
    assert dl_mod._resilience_opts()["socket_timeout"] == 8.0


def test_timeout_helpers_fallback(monkeypatch):
    monkeypatch.setitem(dl_mod.config, "read_timeout", "bogus")
    monkeypatch.setitem(dl_mod.config, "connect_timeout", "bogus")
    monkeypatch.setitem(dl_mod.config, "retry_count", "bogus")
    assert dl_mod._socket_timeout() == 10.0
    assert dl_mod._connect_timeout() == 10.0
    assert dl_mod._retry_count() == 3


def test_ytdl_logger_collects_errors():
    logger = dl_mod.YTDLLogger()
    logger.debug("ignored")
    logger.warning("ignored")
    logger.error("boom")
    assert logger.errors == ["boom"]
    assert logger.warnings == ["ignored"]


@pytest.mark.parametrize(
    "notice",
    [
        "Deprecated Feature: Support for Python version 3.10 has been deprecated.",
        "\x1b[0;31mDeprecated Feature:\x1b[0m Support for Python version 3.10 has been deprecated.",
    ],
)
def test_ytdl_deprecation_on_stderr_remains_a_warning(notice):
    logger = dl_mod.YTDLLogger()
    logger.error(notice)
    assert logger.errors == []
    assert logger.warnings == [
        "Deprecated Feature: Support for Python version 3.10 has been deprecated."
    ]
    logger.error("ERROR: Could not download a video titled Deprecated Feature: demo")
    assert logger.errors == ["ERROR: Could not download a video titled Deprecated Feature: demo"]


def test_subtitle_rate_limit_error_keeps_message_without_ansi_fragments(monkeypatch, tmp_path):
    output = StringIO()
    monkeypatch.setattr(dl_mod, "console", Console(file=output, width=200, force_terminal=False))
    monkeypatch.setattr(dl_mod, "get_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(dl_mod, "ffmpeg_available", lambda: False)

    class FailingYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download=True):
            raise RuntimeError(
                "\x1b[0;31mERROR:\x1b[0m Unable to download video subtitles for 'en': "
                "HTTP Error 429: Too Many Requests"
            )

    monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FailingYDL)
    result = dl_mod.download_media_content("https://youtu.be/example", str(tmp_path))

    assert result["success"] is False
    assert (
        "Error: Unable to download video subtitles for 'en': HTTP Error 429: Too Many Requests"
        in output.getvalue()
    )
    assert "Error: ERROR:" not in output.getvalue()
    assert "[0;31m" not in output.getvalue()


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


def test_socket_timeout_honors_strictest_configured_cap(monkeypatch):
    monkeypatch.setattr(
        dl_mod, "active_setting", lambda key, default=None: 15.0 if key == "connect_timeout" else 45.0
    )
    assert dl_mod._socket_timeout() == 15.0

    monkeypatch.setattr(
        dl_mod, "active_setting", lambda key, default=None: 60.0 if key == "connect_timeout" else 20.0
    )
    assert dl_mod._socket_timeout() == 20.0

