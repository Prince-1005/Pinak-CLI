"""Unit tests for custom exceptions & downloader parsing."""

from pinak import exceptions
from pinak.downloader import parse_download_text


def test_exception_hints_are_actionable():
    for cls in [
        exceptions.InvalidURLError,
        exceptions.NetworkError,
        exceptions.FFmpegNotFoundError,
        exceptions.DownloadFailedError,
        exceptions.InstagramError,
        exceptions.InstagramRateLimitedError,
        exceptions.InstagramPrivateContentError,
        exceptions.ConfigError,
        exceptions.OutputDirError,
    ]:
        exc = cls("msg")
        assert isinstance(exc, exceptions.PinakError)
        assert len(exc.hint) > 20  # must actually tell the user what to do


def test_exception_hierarchy():
    assert issubclass(exceptions.InstagramRateLimitedError, exceptions.InstagramError)
    assert issubclass(exceptions.InstagramError, exceptions.DownloadFailedError)
    assert issubclass(exceptions.DownloadFailedError, exceptions.PinakError)


def test_parse_download_text_video():
    url, audio, force, quality = parse_download_text("/video https://example.com/v --force")
    assert url == "https://example.com/v"
    assert audio is False
    assert force is True


def test_parse_download_text_audio_flag():
    url, audio, force, quality = parse_download_text("https://example.com/v --audio")
    assert audio is True
    assert url == "https://example.com/v"


def test_parse_download_text_quality_equals():
    url, audio, force, quality = parse_download_text("/video https://example.com/v --quality=720p")
    assert quality == "720p"
    assert "quality" not in url


def test_parse_download_text_quality_space():
    url, audio, force, quality = parse_download_text("/video https://example.com/v --quality 1080p")
    assert quality == "1080p"


def test_parse_download_text_plain_url():
    url, audio, force, quality = parse_download_text("https://example.com/v")
    assert url == "https://example.com/v"
    assert force is False
    assert quality is None
