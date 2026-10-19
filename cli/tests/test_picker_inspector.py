"""Long names remain readable in both panes and duration lookup stays asynchronous."""

import re
import threading
import wave

import pytest
from rich.text import Text

from pinak.media.core.input_parser import KeyEvent
from pinak.media.picker import duration
from pinak.media.picker.scanner import MediaItem
from pinak.media.picker.tui_picker import TUIMediaPicker
from pinak.media.visualizer.spectrum_bars import _visible_len
from pinak.subproc import run_cmd
from pinak.utils import get_ffmpeg_path


@pytest.mark.parametrize("cols,rows", [(48, 18), (65, 20), (80, 24), (130, 30)])
def test_full_name_can_be_read_in_both_panels(tmp_path, cols, rows):
    name = "Opening 你好 🎵 " + "very-long-unbroken-filename-" * 6 + " finale.png"
    picker = TUIMediaPicker(tmp_path)
    picker.visible_items = [MediaItem(tmp_path / "image.png", name, False, "picture", 12)]
    left_names, right_names = "", ""
    for _ in range(20):
        output = picker.render_tui(cols, rows)
        plain = Text.from_ansi(output).plain
        assert all(_visible_len(line) <= cols for line in plain.splitlines())
        body = plain.splitlines()[1:-1]
        left = [line.split("│", 1)[0] for line in body]
        right = [line.split("│", 1)[1].strip(" │") for line in body]
        for line in left:
            line = re.sub(r"^.*\[PIC\] ", "", line)
            line = re.sub(r"\d+\.\d+MB", "", line)
            left_names += line.replace(" ", "")
        start = next(index for index, line in enumerate(right) if line.startswith("Name:")) + 1
        end = next(index for index, line in enumerate(right) if line.startswith("Type:"))
        right_names += "".join(right[start:end]).replace(" ", "")
        if picker._name_page == picker._max_name_page:
            break
        picker.handle_input(KeyEvent("right"))
    expected = name.replace(" ", "")
    assert expected in left_names
    assert expected in right_names
    assert "[Esc] Exit" in plain
    picker.close()


def test_selecting_another_item_resets_name_page(tmp_path):
    picker = TUIMediaPicker(tmp_path)
    picker.visible_items = [
        MediaItem(tmp_path / str(i), "long-name" * 24, False, "picture", 0) for i in range(2)
    ]
    picker.render_tui(48, 18)
    picker.handle_input(KeyEvent("right"))
    assert picker._name_page == 1
    picker.handle_input(KeyEvent("down"))
    picker.render_tui(48, 18)
    assert picker._name_page == 0
    picker.close()


def test_duration_does_not_block_and_never_shows_old_selection(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    paths = [tmp_path / name for name in ("one.mp4", "two.mp4")]
    for path in paths:
        path.write_bytes(b"media")
    calls = []

    def probe(path):
        calls.append(path)
        if path == paths[0]:
            entered.set()
            assert release.wait(5)
        return 65.0 if path == paths[0] else 3661.0

    monkeypatch.setattr(duration, "probe_duration", probe)
    inspector = duration.DurationInspector()
    try:
        assert inspector.read(paths[0]) == "Loading..."
        assert entered.wait(5)
        for _ in range(10):
            assert inspector.read(paths[1]) == "Loading..."
        assert calls == [paths[0]]  # Navigation cannot queue unlimited stale probes.
        release.set()
        inspector._pending[1].result(timeout=5)
        assert inspector.read(paths[1]) == "Loading..."
        inspector._pending[1].result(timeout=5)
        assert inspector.read(paths[1]) == "1:01:01"
        assert inspector.read(paths[0]) == "1:05"
        paths[0].write_bytes(b"changed media")
        assert inspector.read(paths[0]) == "Loading..."
        inspector._pending[1].result(timeout=5)
        assert inspector.read(paths[0]) == "1:05"
    finally:
        release.set()
        inspector.close()


def test_audio_duration_with_missing_ffprobe_uses_real_wav(tmp_path, monkeypatch):
    path = tmp_path / "audio.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x00\x00" * 12000)
    monkeypatch.setattr(duration, "get_ffprobe_path", lambda: str(tmp_path / "missing-ffprobe"))
    assert duration.probe_duration(path) == pytest.approx(1.5)


def test_real_video_duration_and_inspector_label(tmp_path):
    path = tmp_path / "video.mp4"
    result = run_cmd(
        [
            get_ffmpeg_path(),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=16x16:r=10",
            "-t",
            "2",
            "-c:v",
            "mpeg4",
            str(path),
        ],
        timeout=10,
    )
    if result.returncode != 0:
        pytest.skip("FFmpeg video fixture generation unavailable")
    assert duration.probe_duration(path) == pytest.approx(2.0, abs=0.1)
    picker = TUIMediaPicker(tmp_path)
    picker.visible_items = [MediaItem(path, path.name, False, "video", path.stat().st_size)]
    try:
        assert "Length: Loading..." in Text.from_ansi(picker.render_tui(100, 24)).plain
        picker._duration_inspector._pending[1].result(timeout=10)
        assert "Length: 0:02" in Text.from_ansi(picker.render_tui(100, 24)).plain
    finally:
        picker.close()


def test_unreadable_duration_is_explicit_and_cached(tmp_path, monkeypatch):
    path = tmp_path / "broken.mp3"
    path.write_bytes(b"not media")
    monkeypatch.setattr(duration, "probe_duration", lambda path: None)
    inspector = duration.DurationInspector()
    try:
        assert inspector.read(path) == "Loading..."
        inspector._pending[1].result(timeout=5)
        assert inspector.read(path) == "Unavailable"
        assert inspector.read(path) == "Unavailable"
    finally:
        inspector.close()
