"""End-to-end download-flow tests with yt-dlp fully mocked (no network)."""

import os

import pinak.downloader as dl_mod


class FakeYoutubeDL:
    """Minimal yt-dlp stand-in: fires progress hooks and drops a media file."""

    def __init__(self, opts):
        self.opts = opts
        for hook in opts.get("progress_hooks", []):
            hook(
                {
                    "status": "downloading",
                    "downloaded_bytes": 512,
                    "total_bytes": 1024,
                    "filename": "fake.mp4",
                }
            )
            hook({"status": "finished"})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=True):
        outtmpl = self.opts.get("outtmpl", "fake_out.%(ext)s")
        target = outtmpl.split("%")[0] + "fake_title.mp4"
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(b"x" * 2048)
        return {
            "title": "fake_title",
            "duration": 60,
            "vcodec": "h264",
            "acodec": "aac",
        }

    def prepare_filename(self, info):
        return os.path.join(self.opts["outtmpl"].split("%")[0], "fake_title.mp4")


def _patch_env(monkeypatch, tmp_path):
    monkeypatch.setattr(dl_mod, "is_online", lambda timeout=5.0: True)
    monkeypatch.setattr(dl_mod, "get_platform", lambda url: "TestTube")
    monkeypatch.setattr(dl_mod.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    outdir = str(tmp_path / "out")
    os.makedirs(outdir, exist_ok=True)
    monkeypatch.setitem(dl_mod.config, "output_dir", outdir)
    return outdir


def test_generic_download_success(monkeypatch, tmp_path, isolated_history_db):
    _patch_env(monkeypatch, tmp_path)
    result = dl_mod.download_instagram_content("https://example.com/v", str(tmp_path / "out"))
    assert result["success"] is True
    assert len(result["files"]) == 1
    assert os.path.getsize(result["files"][0]) == 2048


def test_handle_download_records_history(monkeypatch, tmp_path, isolated_history_db):
    from pinak import history as history_mod

    _patch_env(monkeypatch, tmp_path)
    result = dl_mod.handle_download("https://example.com/v", interactive=False)
    assert result["success"] is True
    rows = history_mod.get_history("")
    assert len(rows) == 1
    assert rows[0]["status"] == "success"


def test_handle_download_offline(monkeypatch):
    monkeypatch.setattr(dl_mod, "is_online", lambda timeout=5.0: False)
    result = dl_mod.handle_download("https://example.com/v", interactive=False)
    assert result["success"] is False


def test_handle_download_bad_url(monkeypatch):
    monkeypatch.setattr(dl_mod, "is_online", lambda timeout=5.0: True)
    result = dl_mod.handle_download("notaurl", interactive=False)
    assert result["success"] is False


def test_handle_download_bad_quality(monkeypatch):
    monkeypatch.setattr(dl_mod, "is_online", lambda timeout=5.0: True)
    result = dl_mod.handle_download("https://example.com/v", quality="ultra-hd", interactive=False)
    assert result["success"] is False
