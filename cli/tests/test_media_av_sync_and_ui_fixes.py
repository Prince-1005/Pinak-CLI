"""Tests for Video A/V Synchronization, Picture Viewer cleanup, Close Button placement, and Subprocess UTF-8 Resilience."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from pinak.media.core.input_parser import KeyEvent
from pinak.media.decoders.probe import MediaMetadata, MediaProbe
from pinak.media.decoders.video_decoder import DecodedVideoFrame
from pinak.media.picture.viewer import PictureViewer
from pinak.media.player.coordinator import MediaSession
from pinak.subproc import run_cmd


@pytest.fixture
def sample_test_images(tmp_path: Path) -> list[Path]:
    paths = []
    for i in range(3):
        p = tmp_path / f"img_{i}.png"
        im = Image.new("RGB", (64, 64), color=(i * 40, 100, 150))
        im.save(p)
        paths.append(p)
    return paths


def test_close_button_only_in_bottom_navigation_bar(tmp_path: Path):
    """Verifies close button is shown exclusively in bottom navigation bar across all media modes."""
    vid_file = tmp_path / "test.mp4"
    vid_file.write_bytes(b"dummy_video")
    aud_file = tmp_path / "test.mp3"
    aud_file.write_bytes(b"dummy_audio")

    # 1. Video Player
    session_vid = MediaSession([vid_file], enable_consent_prompt=False)
    session_vid._current_meta = MediaMetadata(
        media_type="video",
        file_path=vid_file,
        file_size_bytes=1000,
        duration_seconds=100.0,
        width=1280,
        height=720,
    )
    session_vid.video_decoder = MagicMock()

    header_vid = session_vid._build_responsive_header(cols=100, cur_name="test.mp4")
    assert "[ ✕ Close Media ]" not in header_vid
    assert "[✕]" not in header_vid

    footer_vid = session_vid._build_responsive_footer(cols=100)
    lines_vid = footer_vid.split("\n")
    assert "[ ✕ Close Media ]" in lines_vid[0]
    assert "[ ✕ Close Media ]" not in lines_vid[1]
    assert "[ ✕ ]" not in lines_vid[1]

    # 2. Music Player
    session_aud = MediaSession([aud_file], enable_consent_prompt=False)
    session_aud._current_meta = MediaMetadata(
        media_type="audio",
        file_path=aud_file,
        file_size_bytes=1000,
        duration_seconds=200.0,
    )
    session_aud.video_decoder = None
    session_aud.turntable = MagicMock()

    header_aud = session_aud._build_responsive_header(cols=100, cur_name="test.mp3")
    assert "[ ✕ Close Media ]" not in header_aud
    assert "[✕]" not in header_aud

    footer_aud = session_aud._build_responsive_footer(cols=100)
    lines_aud = footer_aud.split("\n")
    assert "[ ✕ Close Media ]" in lines_aud[0]
    assert "[ ✕ Close Media ]" not in lines_aud[1]
    assert "[ ✕ ]" not in lines_aud[1]


def test_picture_viewer_no_slideshow_and_no_exif(sample_test_images):
    """Verifies slideshow and [i]EXIF features are removed from PictureViewer."""
    viewer = PictureViewer(sample_test_images)

    # State attributes must be removed
    assert not hasattr(viewer, "slideshow_active")
    assert not hasattr(viewer, "slideshow_interval")
    assert not hasattr(viewer, "show_exif")
    assert not hasattr(viewer, "toggle_slideshow")

    # Key inputs for slideshow and exif must not be handled
    assert viewer.handle_input(KeyEvent(key="space")) is False
    assert viewer.handle_input(KeyEvent(key="t")) is False
    assert viewer.handle_input(KeyEvent(key="i")) is False

    # Rendered TUI must not display slideshow or EXIF in header or footer
    for cols in (65, 80, 100, 130):
        tui = viewer.render_tui(cols=cols, rows=24, elapsed_sec=0.0)
        assert "Slideshow" not in tui
        assert "[Space/t]" not in tui
        assert "EXIF" not in tui
        assert "[i]" not in tui

        # Header must NOT contain close button; footer line 1 must have close button
        lines = tui.split("\n")
        assert "[ ✕ Close Image ]" not in lines[0]
        assert "[✕]" not in lines[0]


def test_video_sync_drops_lagging_frames(tmp_path: Path):
    """Verifies that when video lags behind audio clock, stale frames are dropped to catch up."""
    vid_file = tmp_path / "sync_lag.mp4"
    vid_file.write_bytes(b"dummy")

    session = MediaSession([vid_file], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="video",
        file_path=vid_file,
        file_size_bytes=1000,
        duration_seconds=100.0,
        width=1280,
        height=720,
        fps=30.0,
    )
    session.video_decoder = MagicMock()
    session.video_decoder.target_fps = 30.0

    # Stale frame at 0.10s, next frame at 0.15s, on-time frame at 0.20s
    stale_frame_1 = DecodedVideoFrame(
        pts=0.10, rgb_data=b"\x00" * (100 * 50 * 3), width=100, height=50
    )
    stale_frame_2 = DecodedVideoFrame(
        pts=0.15, rgb_data=b"\x00" * (100 * 50 * 3), width=100, height=50
    )
    ontime_frame = DecodedVideoFrame(
        pts=0.20, rgb_data=b"\x00" * (100 * 50 * 3), width=100, height=50
    )
    future_frame = DecodedVideoFrame(
        pts=0.233, rgb_data=b"\x00" * (100 * 50 * 3), width=100, height=50
    )

    session._buffered_video_frame = stale_frame_1
    session.video_decoder.read_frame.side_effect = [stale_frame_2, ontime_frame, future_frame]

    session.master_clock = MagicMock()
    session.master_clock.get_time.return_value = 0.20
    session.transport.is_playing = True

    # Render frame
    session._render_media_tui(cols=80, rows=24, dt=0.016)

    # Frame 1 and 2 should have been dropped; on-time frame presented (last_frame_pts == 0.20)
    assert session._last_frame_pts == 0.20
    assert session._buffered_video_frame == ontime_frame


def test_video_sync_holds_future_frames(tmp_path: Path):
    """Verifies that when video frame is ahead of audio clock, it is held in reserve and not dropped."""
    vid_file = tmp_path / "sync_ahead.mp4"
    vid_file.write_bytes(b"dummy")

    session = MediaSession([vid_file], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="video",
        file_path=vid_file,
        file_size_bytes=1000,
        duration_seconds=100.0,
        width=1280,
        height=720,
        fps=30.0,
    )
    session.video_decoder = MagicMock()
    session.video_decoder.target_fps = 30.0

    # Future frame at 0.50s while master_pts is only 0.30s (drift = +0.20s > sync_window)
    future_frame = DecodedVideoFrame(
        pts=0.50, rgb_data=b"\x00" * (100 * 50 * 3), width=100, height=50
    )
    session._buffered_video_frame = future_frame
    session.video_decoder.read_frame.return_value = None

    session.master_clock = MagicMock()
    session.master_clock.get_time.return_value = 0.30
    session.transport.is_playing = True
    session._last_frame_pts = 0.25

    # Render frame
    session._render_media_tui(cols=80, rows=24, dt=0.016)

    # Future frame must NOT be consumed or dropped; it must remain in _buffered_video_frame
    assert session._buffered_video_frame == future_frame
    assert session._last_frame_pts == 0.25


def test_video_sync_hard_desync_recovery(tmp_path: Path):
    """Verifies that large desync (> 0.35s) triggers decoder seek to master_pts."""
    vid_file = tmp_path / "sync_desync.mp4"
    vid_file.write_bytes(b"dummy")

    session = MediaSession([vid_file], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="video",
        file_path=vid_file,
        file_size_bytes=1000,
        duration_seconds=100.0,
        width=1280,
        height=720,
        fps=30.0,
    )
    session.video_decoder = MagicMock()
    session.video_decoder.target_fps = 30.0

    # Old frame at 0.10s while master_pts jumped to 5.00s (hard drift = -4.90s)
    old_frame = DecodedVideoFrame(pts=0.10, rgb_data=b"\x00" * (100 * 50 * 3), width=100, height=50)
    resynced_frame = DecodedVideoFrame(
        pts=5.00, rgb_data=b"\x00" * (100 * 50 * 3), width=100, height=50
    )

    session._buffered_video_frame = old_frame
    session.video_decoder.read_frame.side_effect = [resynced_frame, None]

    session.master_clock = MagicMock()
    session.master_clock.get_time.return_value = 5.00
    session.transport.is_playing = True

    session._render_media_tui(cols=80, rows=24, dt=0.016)

    # Video decoder must have been sought to 5.00s
    session.video_decoder.seek.assert_called_with(5.00)
    assert session._last_frame_pts == 5.00


def test_video_seek_anchors_master_clock(tmp_path: Path):
    """Verifies that left/right seeking synchronizes master_clock and resets frame points."""
    vid_file = tmp_path / "seek.mp4"
    vid_file.write_bytes(b"dummy")

    session = MediaSession([vid_file], enable_consent_prompt=False)
    session.audio_backend = MagicMock()
    session.video_decoder = MagicMock()
    from pinak.media.sync.clock import MasterAudioClock

    session.master_clock = MasterAudioClock(session.audio_backend)
    session.transport.current_pts = 30.0

    # Seek relative +10s
    session._handle_action_key("right", cols=80, rows=24)

    session.audio_backend.seek.assert_called_once_with(40.0)
    assert session.video_decoder.seek.called
    assert session.master_clock.audio_backend is session.audio_backend
    assert session._buffered_video_frame is None
    assert session._last_video_img is None


def test_probe_and_subproc_invalid_utf8_continuation_resilience(tmp_path: Path):
    """Verifies that subprocess execution does not raise UnicodeDecodeError on invalid UTF-8 bytes."""
    # Simulate a process outputting non-UTF-8 bytes (invalid continuation byte)
    invalid_bytes = b"Video Stream Info: \x80\xff\xfe corrupted tag data Duration: 00:01:23.45"

    with (
        patch.object(MediaProbe, "_find_ffmpeg", return_value="fake_ffmpeg"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffmpeg"],
            returncode=0,
            stdout="{}",
            stderr=invalid_bytes.decode("utf-8", errors="replace"),
        )
        dur = MediaProbe._probe_duration_with_ffmpeg(tmp_path / "dummy.mp4")
        assert dur == 83.45

    # Test run_subprocess handling
    with patch("subprocess.run") as mock_run2:
        mock_run2.return_value = subprocess.CompletedProcess(
            args=["fake_tool"],
            returncode=0,
            stdout=invalid_bytes.decode("utf-8", errors="replace"),
            stderr="",
        )
        res = run_cmd(["fake_tool"])
        assert res.returncode == 0
        assert "\ufffd" in res.stdout


def test_video_player_repeat_modes_and_sequential_playback_stop_at_first(
    tmp_path: Path, monkeypatch
):
    """Verifies that:
    1. Video player displays [r] Repeat in footer navigation bar.
    2. Video player allows cycling repeat modes ('r' key).
    3. Under Repeat OFF, videos continue in sequence.
    4. After all videos finish, TUI leads to the first video and stops (paused).
    5. Pressing Space resumes playback of the first video.
    """
    v1 = tmp_path / "vid_1.mp4"
    v2 = tmp_path / "vid_2.mp4"
    v3 = tmp_path / "vid_3.mp4"
    v1.write_bytes(b"dummy1")
    v2.write_bytes(b"dummy2")
    v3.write_bytes(b"dummy3")

    session = MediaSession([v1, v2, v3], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="video",
        file_path=v1,
        file_size_bytes=1000,
        duration_seconds=10.0,
        width=1280,
        height=720,
    )
    session.video_decoder = MagicMock()
    session.audio_backend = MagicMock()
    session.master_clock = MagicMock()
    session.transport.duration_sec = 10.0
    session.transport.is_playing = True

    # Exercise real playlist transitions while keeping invalid fixture bytes
    # away from host FFmpeg/audio drivers and their asynchronous error paths.
    from dataclasses import replace

    metadata = session._current_meta
    monkeypatch.setattr(MediaProbe, "probe", lambda path: replace(metadata, file_path=path))

    def initialize_components():
        session.video_decoder = MagicMock()
        session.video_decoder.read_frame.return_value = None
        session.audio_backend = MagicMock()
        session.master_clock = MagicMock()
        session.master_clock.get_time.return_value = 0.0
        session.transport.duration_sec = 10.0

    monkeypatch.setattr(session, "_init_media_components", initialize_components)

    # 1. Repeat mode starts at 'none' (OFF), and footer shows [r] Repeat
    assert session.playlist_manager.repeat_mode == "none"
    ftr = session._build_responsive_footer(100)
    assert "[r] Repeat" in ftr
    hdr = session._build_responsive_header(100, "vid_1.mp4")
    assert "Rep: OFF" in hdr

    # 2. Pressing 'r' cycles repeat modes for video player
    session._handle_action_key("r", 100, 24)
    assert session.playlist_manager.repeat_mode == "all"
    hdr_all = session._build_responsive_header(100, "vid_1.mp4")
    assert "Rep: ALL" in hdr_all

    session._handle_action_key("r", 100, 24)
    assert session.playlist_manager.repeat_mode == "solo"

    session._handle_action_key("r", 100, 24)
    assert session.playlist_manager.repeat_mode == "none"

    # 3. Under Repeat OFF: vid_1 finishes -> continues in sequence to vid_2
    session.playlist_manager.current_idx = 0
    session.master_clock.get_time = MagicMock(return_value=10.5)
    session._render_media_tui(100, 24, dt=0.016)
    assert session.playlist_manager.current_idx == 1

    # vid_2 finishes -> continues in sequence to vid_3
    session.transport.duration_sec = 10.0
    session.transport.is_playing = True
    session.master_clock.get_time = MagicMock(return_value=10.5)
    session._render_media_tui(100, 24, dt=0.016)
    assert session.playlist_manager.current_idx == 2

    # vid_3 (last video) finishes -> all videos played! Leads back to first video and stops
    session.transport.duration_sec = 10.0
    session.transport.is_playing = True
    session.master_clock.get_time = MagicMock(return_value=10.5)
    session._render_media_tui(100, 24, dt=0.016)

    assert session.playlist_manager.current_idx == 0
    assert session.transport.is_playing is False

    # 4. User can start video by clicking space
    session._handle_action_key("space", 100, 24)
    assert session.transport.is_playing is True
