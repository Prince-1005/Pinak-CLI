"""Reliability tests: integrity verification, FFmpeg fallback, parallel carousels."""

import os

import pinak.downloader as dl_mod
import pinak.ffmpeg_setup as ff_mod
import pinak.instagram as ig_mod


# --- integrity -----------------------------------------------------------
def test_verify_files_filters_bad(tmp_path):
    good = tmp_path / "ok.mp4"
    good.write_bytes(b"x" * 100)
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    missing = str(tmp_path / "ghost.mp4")

    valid, problems = dl_mod.verify_files([str(good), str(empty), missing])
    assert valid == [str(good)]
    assert sorted(problems) == sorted([str(empty), missing])


def test_verify_files_empty_input():
    assert dl_mod.verify_files([]) == ([], [])
    assert dl_mod.verify_files(None) == ([], [])


# --- ffmpeg fallback ------------------------------------------------------
def test_ensure_ffmpeg_prefers_existing(tmp_path, monkeypatch):
    binary = tmp_path / "ffmpeg.exe"
    binary.write_bytes(b"fake")
    monkeypatch.setattr(ff_mod, "get_ffmpeg_path", lambda: str(binary))
    assert ff_mod.ensure_ffmpeg() == str(binary)


def test_ensure_ffmpeg_graceful_without_static_ffmpeg(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "static_ffmpeg", None)
    monkeypatch.setattr(ff_mod, "get_ffmpeg_path", lambda: "/nonexistent/ffmpeg")
    # static-ffmpeg is not installed in test env -> must fall back, never raise.
    assert ff_mod.ensure_ffmpeg() == "/nonexistent/ffmpeg"


# --- parallel carousels ---------------------------------------------------
class _FakeWorkerYDL:
    outdir = ""

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def process_video_result(self, entry, download=True):
        path = os.path.join(type(self).outdir, f"{entry['id']}.mp4")
        with open(path, "wb") as fh:
            fh.write(b"v" * 512)
        return {"id": entry["id"]}


def _video_entry(slide_id):
    return {
        "id": slide_id,
        "formats": [{"url": "http://example.com/x", "vcodec": "h264"}],
    }


def test_parallel_carousel_downloads_all_slides(tmp_path, monkeypatch):
    outdir = tmp_path / "slides"
    outdir.mkdir()
    _FakeWorkerYDL.outdir = str(outdir)
    monkeypatch.setattr(ig_mod.yt_dlp, "YoutubeDL", _FakeWorkerYDL)
    embedded = []
    monkeypatch.setattr(ig_mod, "embed_metadata_in_video", lambda p, m: embedded.append(str(p)))

    info = {
        "_type": "playlist",
        "entries": [_video_entry(f"s{i}") for i in range(1, 4)],
    }
    ig_mod._download_extracted_info(
        None, info, outdir, "", {}, ydl_opts={"quiet": True, "outtmpl": "x"}
    )

    produced = sorted(p.name for p in outdir.iterdir() if p.suffix == ".mp4")
    assert produced == ["s1.mp4", "s2.mp4", "s3.mp4"]
    assert len(embedded) == 3


def test_sequential_fallback_without_opts(tmp_path, monkeypatch):
    """Without ydl_opts the carousel path stays sequential using the given ydl."""
    outdir = tmp_path / "seq"
    outdir.mkdir()
    _FakeWorkerYDL.outdir = str(outdir)

    class _DirectYDL(_FakeWorkerYDL):
        pass

    monkeypatch.setattr(ig_mod, "embed_metadata_in_video", lambda p, m: None)
    info = {"_type": "playlist", "entries": [_video_entry("a"), _video_entry("b")]}
    ig_mod._download_extracted_info(_DirectYDL({}), info, outdir, "", {})
    assert sorted(p.name for p in outdir.iterdir()) == ["a.mp4", "b.mp4"]
