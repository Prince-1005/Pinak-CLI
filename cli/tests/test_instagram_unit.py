"""Unit tests for instagram helpers: metadata, thumbnails, retry, errors."""

import pytest

import pinak.instagram as ig_mod


def test_extract_metadata_shapes_data():
    info = {
        "id": "abc",
        "title": "t",
        "description": "d",
        "uploader": "u",
        "uploader_id": "uid",
        "upload_date": "20240101",
        "timestamp": 123,
        "like_count": 5,
        "comment_count": 2,
        "webpage_url": "https://www.instagram.com/p/abc/",
    }
    meta = ig_mod.extract_metadata(info)
    assert meta["id"] == "abc"
    assert meta["webpage_url"].startswith("https://")


def test_best_thumbnail_picks_largest_area():
    entry = {
        "thumbnails": [
            {"url": "http://x/small", "width": 100, "height": 100},
            {"url": "http://x/big", "width": 1080, "height": 1920},
            {"url": "http://x/mid", "width": 640, "height": 640},
        ]
    }
    assert ig_mod._best_thumbnail_url(entry) == "http://x/big"


def test_best_thumbnail_falls_back_to_thumbnail():
    assert ig_mod._best_thumbnail_url({"thumbnail": "http://x/t"}) == "http://x/t"
    assert ig_mod._best_thumbnail_url({}) is None


def test_best_thumbnail_prefers_display_url():
    entry = {
        "display_url": "https://cdninstagram.com/master_1080.jpg",
        "thumbnails": [
            {"url": "https://cdninstagram.com/preview_150.jpg", "width": 150, "height": 150}
        ],
    }
    assert ig_mod._best_thumbnail_url(entry) == "https://cdninstagram.com/master_1080.jpg"


def test_best_thumbnail_infers_dimensions_from_url():
    entry = {
        "thumbnails": [
            {"url": "https://cdninstagram.com/s150x150/preview.jpg"},
            {"url": "https://cdninstagram.com/s1080x1080/full.jpg"},
            {"url": "https://cdninstagram.com/s640x640/medium.jpg"},
        ]
    }
    assert ig_mod._best_thumbnail_url(entry) == "https://cdninstagram.com/s1080x1080/full.jpg"


def test_best_thumbnail_ignores_webpage_urls():
    entry = {
        "url": "https://www.instagram.com/p/ABC123xyz/",
        "thumbnail": "https://cdninstagram.com/actual_thumb.jpg",
    }
    assert ig_mod._best_thumbnail_url(entry) == "https://cdninstagram.com/actual_thumb.jpg"


def test_best_thumbnail_single_image_entry_url():
    entry = {
        "url": "https://cdninstagram.com/direct_post.jpg",
    }
    assert ig_mod._best_thumbnail_url(entry) == "https://cdninstagram.com/direct_post.jpg"


def test_best_thumbnail_prefers_later_thumbnail_on_tie():
    entry = {
        "thumbnails": [
            {"url": "https://cdninstagram.com/first.jpg"},
            {"url": "https://cdninstagram.com/second_higher_quality.jpg"},
        ]
    }
    assert ig_mod._best_thumbnail_url(entry) == "https://cdninstagram.com/second_higher_quality.jpg"


def test_has_video_formats():
    assert ig_mod._has_video_formats({"formats": [{"url": "u", "vcodec": "h264"}]}) is True
    assert ig_mod._has_video_formats({"formats": [{"url": "u", "vcodec": "none"}]}) is False
    assert ig_mod._has_video_formats({}) is False


def test_image_filename_is_sanitized(tmp_path):
    entry = {"id": "abc", "title": 'a<b>c:d"e'}
    name = ig_mod._image_filename(entry, tmp_path, 3, "")
    assert name.suffix == ".jpg"
    assert name.name.startswith("03_abc_")
    assert "<" not in name.name and ">" not in name.name


def test_build_image_exif_roundtrip():
    exif = ig_mod._build_image_exif(
        {
            "id": "1",
            "title": "t",
            "description": "d",
            "uploader": "u",
            "webpage_url": "https://x",
        }
    )
    assert exif is not None
    assert exif[270] == "t"  # ImageDescription


def test_friendly_errors_classify():
    from pinak.exceptions import (
        InstagramError,
        InstagramPrivateContentError,
        InstagramRateLimitedError,
    )

    assert isinstance(
        ig_mod._friendly_instagram_error(RuntimeError("HTTP 429")),
        InstagramRateLimitedError,
    )
    assert isinstance(
        ig_mod._friendly_instagram_error(RuntimeError("private post")),
        InstagramPrivateContentError,
    )
    assert isinstance(ig_mod._friendly_instagram_error(RuntimeError("weird")), InstagramError)


def test_resolve_entry_follows_urls():
    class _YDL:
        def extract_info(self, url, download=False, process=False):
            return {"id": "final", "url": url}

    resolved = ig_mod._resolve_entry(_YDL(), {"_type": "url", "url": "http://x/y"})
    assert resolved["id"] == "final"


def test_resolve_entry_gives_up_gracefully():
    class _YDL:
        def extract_info(self, url, download=False, process=False):
            raise RuntimeError("nope")

    entry = {"_type": "url", "url": "http://x/y"}
    assert ig_mod._resolve_entry(_YDL(), entry) is entry


def test_download_binary_retry_success(tmp_path, monkeypatch):
    target = tmp_path / "img.bin"

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"data"

    monkeypatch.setattr(ig_mod, "urlopen", lambda *a, **k: _Resp())
    ig_mod._download_binary_with_retry("http://x/img", target)
    assert target.read_bytes() == b"data"


def test_download_binary_retry_exhausts(monkeypatch, tmp_path):
    import urllib.error

    monkeypatch.setattr(
        ig_mod,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("down")),
    )
    monkeypatch.setattr(ig_mod.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="failed after"):
        ig_mod._download_binary_with_retry("http://x/img", tmp_path / "img.bin")


def test_download_instagram_media_extract_failure(monkeypatch, tmp_path):
    from yt_dlp.utils import DownloadError

    class _YDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, *a, **k):
            raise DownloadError("blocked", False)

    monkeypatch.setattr(ig_mod.yt_dlp, "YoutubeDL", _YDL)
    from pinak.exceptions import InstagramError

    with pytest.raises(InstagramError):
        ig_mod.download_instagram_media("https://www.instagram.com/p/abc/", str(tmp_path))
