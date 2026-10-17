"""Regression checks for startup, continuous audio pacing and decoder churn."""

from __future__ import annotations

import sys
import threading
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pinak.media.decoders.audio_backend import AudioPlayerBackend
from pinak.media.decoders.video_decoder import DecodedVideoFrame, VideoDecoder
from pinak.media.player.coordinator import MediaSession
from pinak.media.renderers.halfblock import HalfBlockRenderer
from pinak.media.subtitles.loader import SubtitleLoader


def test_terminal_decode_budget_preserves_native_window_detail(tmp_path):
    path = tmp_path / "4k.mp4"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    session.renderer = HalfBlockRenderer()
    width, height = session._video_decode_dimensions(160, 40, 3840, 2160)
    assert width <= 160 and height <= 80
    assert width / height == pytest.approx(3840 / 2160, abs=0.05)
    session.enable_native_window = True
    assert session._video_decode_dimensions(160, 40, 3840, 2160) == (3840, 2160)


def test_resize_restarts_at_presentation_time_not_read_ahead(tmp_path):
    decoder = VideoDecoder(tmp_path / "movie.mp4", 160, 90)
    decoder._current_pts = 8
    with patch.object(decoder, "start") as start:
        decoder.update_dimensions(320, 180, start_time_sec=3)
    start.assert_called_once_with(start_time_sec=3)


def test_hardware_probe_is_cached_and_cpu_fallback_sticks(tmp_path, monkeypatch):
    decoder = VideoDecoder(tmp_path / "movie.mp4")
    monkeypatch.setattr(decoder, "find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(decoder, "_reader_loop", lambda: None)
    detect = MagicMock(return_value="cuda")
    monkeypatch.setattr(decoder, "detect_hw_accel", detect)
    process = MagicMock()
    process.wait.return_value = 0
    with patch(
        "pinak.media.decoders.video_decoder.subprocess.Popen", return_value=process
    ) as spawn:
        try:
            decoder.start()
            decoder.seek(1)
            decoder.start(2, software_only=True)
            decoder.seek(3)
            assert detect.call_count == 1
            assert "-hwaccel" not in spawn.call_args.args[0]
        finally:
            decoder.close()


def test_first_video_frame_shows_while_audio_device_is_opening(tmp_path):
    path = tmp_path / "movie.mp4"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    session.video_decoder = MagicMock(error=None, eof=False, target_fps=30)
    session._buffered_video_frame = DecodedVideoFrame(0, 16, 16, b"\0" * 768)
    session._last_frame_pts = 0
    session.master_clock = MagicMock(get_time=lambda: 0)
    session._render_media_tui(80, 24, 0.01)
    assert session._last_video_img is not None
    session.video_decoder.read_frame.assert_not_called()


def test_render_lag_does_not_restart_decoder_every_frame(tmp_path):
    path = tmp_path / "movie.mp4"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    frame = DecodedVideoFrame(0, 16, 16, b"\0" * 768)
    session._buffered_video_frame = frame
    session._last_frame_pts = 0
    session.video_decoder = MagicMock(error=None, eof=False, target_fps=30)
    session.video_decoder.read_frame.return_value = None
    session.master_clock = MagicMock(get_time=lambda: 0.6)
    for _ in range(3):
        session._render_media_tui(80, 24, 0.01)
    session.video_decoder.seek.assert_not_called()


def test_large_desync_restarts_are_rate_limited(tmp_path):
    path = tmp_path / "movie.mp4"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    frame = DecodedVideoFrame(0, 16, 16, b"\0" * 768)
    session._buffered_video_frame = frame
    session.video_decoder = MagicMock(error=None, eof=False, target_fps=30)
    session.video_decoder.read_frame.return_value = frame
    session.master_clock = MagicMock(get_time=lambda: 5)
    for _ in range(3):
        session._render_media_tui(80, 24, 0.01)
    session.video_decoder.seek.assert_called_once_with(5)
    # Even a broken source repeating a stale timestamp cannot monopolize a tick.
    assert session.video_decoder.read_frame.call_count <= 100


def test_subtitle_loading_does_not_block_and_discards_old_track(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    first, second = tmp_path / "one.mp4", tmp_path / "two.mp4"

    def discover(path):
        calls.append(path)
        if path == first:
            entered.set()
            release.wait(2)
        return [path]

    monkeypatch.setattr(
        "pinak.media.subtitles.loader.SubtitleParser.discover_sibling_subtitles", discover
    )
    monkeypatch.setattr(
        "pinak.media.subtitles.loader.SubtitleParser.extract_embedded_subtitles",
        lambda *a, **kw: [],
    )
    loader = SubtitleLoader()
    try:
        loader.load(first)
        assert entered.wait(1)
        loader.load(second)
        assert loader.poll() is None  # first extraction is still blocked
        release.set()
        for _ in range(200):
            result = loader.poll()
            if result is not None:
                break
            threading.Event().wait(0.005)
        assert result == [second]
        assert calls == [first, second]
    finally:
        release.set()
        loader.close()


def test_audio_pacing_recovers_from_a_slow_block(tmp_path, monkeypatch):
    import pinak.media.decoders.audio_backend as module

    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(48000)
        out.writeframes(b"\0" * (4800 * 4))
    clock = [0.0]
    calls = []
    options = []

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def write(self, pcm):
            clock[0] += 0.05 if not calls else 0.001
            calls.append(pcm)

    def output(**kwargs):
        options.append(kwargs)
        return Stream()

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawOutputStream=output))
    monkeypatch.setattr(module, "time", SimpleNamespace(perf_counter=lambda: clock[0]))
    cancelled = SimpleNamespace(
        is_set=lambda: False, wait=lambda delay: clock.__setitem__(0, clock[0] + delay)
    )
    backend = AudioPlayerBackend(path, driver="sounddevice")
    backend._stream("sounddevice", 0, backend._generation, cancelled)
    assert clock[0] == pytest.approx(0.1)
    assert backend.get_clock() == pytest.approx(0.1)
    assert options[0]["latency"] == "low"
    assert max(map(len, calls)) <= 960 * 4


def test_empty_audio_does_not_open_an_output_device(tmp_path, monkeypatch):
    path = tmp_path / "empty.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(48000)
    open_stream = MagicMock(side_effect=AssertionError("No PCM to play"))
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawOutputStream=open_stream))
    backend = AudioPlayerBackend(path, driver="sounddevice")
    backend._stream("sounddevice", 0, backend._generation, threading.Event())
    assert backend.is_eos
    open_stream.assert_not_called()


def test_constrained_profile_recalibrates_the_throttle_budget(tmp_path):
    path = tmp_path / "movie.mp4"
    path.touch()
    session = MediaSession([path], enable_consent_prompt=False)
    with (
        patch(
            "pinak.media.player.coordinator.MediaProbe.probe",
            return_value=SimpleNamespace(width=640, media_type="video"),
        ),
        patch("pinak.media.player.coordinator.DeviceDiagnosticsProbe.inspect"),
        patch(
            "pinak.media.player.coordinator.CapacityScorer.evaluate",
            return_value=SimpleNamespace(tier="constrained", suggested_fps=24),
        ),
        patch("pinak.media.player.coordinator.TerminalSessionContext"),
        patch("pinak.media.player.coordinator.PrecisionEventLoop"),
        patch.object(session.ipc_server, "start"),
        patch.object(session.ipc_server, "stop"),
        patch.object(session, "_init_media_components"),
    ):
        session.start()
    assert session.throttler.target_frame_time == pytest.approx(1 / 24)
