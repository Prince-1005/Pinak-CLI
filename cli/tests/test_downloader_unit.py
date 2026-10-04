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
