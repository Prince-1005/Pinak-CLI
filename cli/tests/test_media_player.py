"""Unit tests for pinak.media.player modules."""

from pathlib import Path

import pytest

from pinak.media.player.display_mode import DisplayModeCoordinator
from pinak.media.player.playlist import PlaylistManager
from pinak.media.player.quality import QualityProfileManager
from pinak.media.player.transport import TransportController


@pytest.fixture
def fake_tracks(tmp_path: Path):
    tracks = []
    for i in range(5):
        p = tmp_path / f"track_{i}.mp3"
        p.write_bytes(b"dummy")
        tracks.append(p)
    return tracks


def test_playlist_manager_repeat_and_shuffle(fake_tracks):
    pl = PlaylistManager(fake_tracks, repeat_mode="all")
    assert pl.total_tracks == 5
    assert pl.get_current() == fake_tracks[0]

    # Advance through all tracks
    for i in range(1, 5):
        t = pl.next_track()
        assert t == fake_tracks[i]

    # Under 'all', wraps around to 0
    t = pl.next_track()
    assert t == fake_tracks[0]

    # Repeat 'solo'
    pl.cycle_repeat_mode()
    assert pl.repeat_mode == "solo"
    assert pl.next_track() == fake_tracks[0]

    # Repeat 'none'
    pl.cycle_repeat_mode()
    assert pl.repeat_mode == "none"

    # Shuffle
    pl.toggle_shuffle()
    assert pl.is_shuffled is True

    # Test has_next under different repeat modes
    pl.repeat_mode = "all"
    assert pl.has_next() is True

    pl.repeat_mode = "solo"
    assert pl.has_next() is True

    pl.repeat_mode = "none"
    pl.current_idx = 4  # final track of 5
    assert pl.has_next() is False
    pl.current_idx = 2
    assert pl.has_next() is True

    # Turn off shuffle to verify deterministic track index order
    pl.toggle_shuffle()
    assert pl.is_shuffled is False

    # Test circular prev_track under 'all'
    pl.repeat_mode = "all"
    pl.current_idx = 0
    pl.history_stack.clear()
    assert pl.prev_track() == fake_tracks[4]


def test_transport_controller():
    tc = TransportController(duration_sec=120.0)
    assert tc.is_playing is True
    assert tc.current_pts == 0.0

    tc.toggle_play_pause()
    assert tc.is_playing is False

    # Seek +10s
    tc.seek_relative(10.0)
    assert tc.current_pts == 10.0

    # Seek -10s
    tc.seek_relative(-5.0)
    assert tc.current_pts == 5.0

    # Volume & mute
    tc.volume_up(0.1)
    assert tc.volume == 1.1
    tc.toggle_mute()
    assert tc.is_muted is True

    # Progress bar string
    bar = tc.get_progress_bar(width=40)
    assert "00:05" in bar
    assert "02:00" in bar


def test_quality_profile_manager():
    qm = QualityProfileManager(default_profile="auto")
    assert qm.current_profile.id == "auto"

    dims = qm.get_target_dimensions(80, 24)
    assert dims == (80, 48)

    qm.cycle_profile()
    assert qm.current_profile.id == "1080p"
    assert qm.get_target_dimensions(80, 24) == (1920, 1080)


def test_display_mode_coordinator():
    with pytest.deprecated_call():
        dm = DisplayModeCoordinator()
    assert dm.is_mini_screen is False

    part = dm.partition_terminal(100, 30)
    assert part.canvas_cols == 100
    assert part.sidebar_cols == 0
    assert part.is_mini is False

    # Toggle does not fragment screen into mini mode
    dm.toggle()
    assert dm.is_mini_screen is False
    part2 = dm.partition_terminal(100, 30)
    assert part2.canvas_cols == 100
    assert part2.is_mini is False


def test_coordinator_spacebar_pause_and_freeze_frame(tmp_path: Path, monkeypatch):
    """Verifies that pressing Space toggles pause, freezes master clock, and caches video frame."""
    from unittest.mock import MagicMock

    from pinak.media.core.input_parser import KeyEvent
    from pinak.media.decoders.video_decoder import DecodedVideoFrame
    from pinak.media.player.coordinator import MediaSession

    fake_file = tmp_path / "clip.mp4"
    fake_file.write_bytes(b"dummy_data")

    session = MediaSession([fake_file], enable_consent_prompt=False)
    monkeypatch.setattr(session.master_clock, "get_time", lambda: 0.0)
    session.video_decoder = MagicMock()
    fake_vf = DecodedVideoFrame(pts=0.0, rgb_data=b"\x00" * (16 * 16 * 3), width=16, height=16)
    session.video_decoder.read_frame.return_value = fake_vf

    # Frame 1: playing
    assert session.transport.is_playing is True
    out1 = session._on_tick(0.016, [])
    assert out1 is not None
    assert session.video_decoder.read_frame.call_count == 1
    assert session._last_video_img is not None

    # Press Space: pause
    session._on_tick(0.016, [KeyEvent(key="space")])
    assert session.transport.is_playing is False
    assert session.master_clock._is_paused is True

    # Next frame while paused: read_frame must NOT be called again
    read_count_before = session.video_decoder.read_frame.call_count
    out2 = session._on_tick(0.016, [])
    assert out2 is not None
    assert session.video_decoder.read_frame.call_count == read_count_before  # Frame frozen!

    # Press Space again: resume
    session._on_tick(0.016, [KeyEvent(key="space")])
    assert session.transport.is_playing is True
    assert session.master_clock._is_paused is False


def test_coordinator_q_cycles_quality_and_fft(tmp_path: Path):
    """Verifies that key 'q' cycles video resolution and audio FFT bands."""
    from unittest.mock import MagicMock

    from pinak.media.core.input_parser import KeyEvent
    from pinak.media.decoders.video_decoder import DecodedVideoFrame
    from pinak.media.player.coordinator import MediaSession

    fake_file = tmp_path / "test.mp4"
    fake_file.write_bytes(b"dummy")

    session = MediaSession([fake_file], enable_consent_prompt=False)
    session.video_decoder = MagicMock()
    session.video_decoder.read_frame.return_value = DecodedVideoFrame(
        pts=1.0, rgb_data=b"\x00" * (16 * 16 * 3), width=16, height=16
    )
    assert session.quality_manager.current_profile.id == "native"

    # Press 'q' to cycle video profile
    session._on_tick(0.016, [KeyEvent(key="q")])
    assert session.quality_manager.current_profile.id == "auto"

    # Test audio mode FFT band cycling
    session.video_decoder = None
    session.turntable = MagicMock()
    initial_fft_idx = session.fft_band_idx
    session._on_tick(0.016, [KeyEvent(key="q")])
    assert session.fft_band_idx != initial_fft_idx


def test_kitty_renderer_vertical_spacing():
    """Verifies that KittyRenderer emits vertical newlines so footer does not collide with line 2."""
    from PIL import Image

    from pinak.media.renderers.pixel_kitty import KittyRenderer

    r = KittyRenderer()
    img = Image.new("RGB", (64, 64), color=(255, 0, 0))
    res = r.render_frame(img, target_cols=40, target_rows=20)
    assert "\x1b_Ga=T" in res
    assert res.endswith("\n" * 19)


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_launch_standalone_media_window(monkeypatch, platform):
    """Verifies that launch_standalone_media_window correctly constructs OS console commands."""
    import subprocess
    from unittest.mock import MagicMock

    from pinak.commands.media import launch_standalone_media_window

    mock_popen = MagicMock()
    mock_popen.return_value.wait.return_value = 0
    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    monkeypatch.setattr("sys.platform", platform)
    monkeypatch.setattr("pinak.utils.trusted_which", lambda name: "/usr/bin/xterm")
    success = launch_standalone_media_window(["test.mp4"])
    assert success is True
    assert mock_popen.called
    command = mock_popen.call_args.args[0]
    if platform == "linux":
        assert command[:2] == ["/usr/bin/xterm", "-e"]
    else:
        assert mock_popen.call_args.kwargs["creationflags"]


def test_timeline_scrubber_duration_alignment():
    """Verifies that TransportController progress bar guarantees total time on right with safe margin."""
    from pinak.media.player.transport import TransportController

    tc = TransportController(duration_sec=150.0)  # 02:30
    tc.current_pts = 5.0  # 00:05

    bar = tc.get_progress_bar(width=80)
    assert "00:05" in bar
    assert "02:30" in bar
    assert bar.strip().endswith("02:30")
    assert len(bar) <= 80


def test_coordinator_mouse_click_quality_button(tmp_path: Path):
    """Verifies that clicking the footer [q] Quality/Res button cycles quality."""
    from unittest.mock import MagicMock

    from pinak.media.core.input_parser import MouseEvent
    from pinak.media.decoders.video_decoder import DecodedVideoFrame
    from pinak.media.player.coordinator import MediaSession

    fake_file = tmp_path / "test.mp4"
    fake_file.write_bytes(b"dummy")

    session = MediaSession([fake_file], enable_consent_prompt=False)
    session.video_decoder = MagicMock()
    session.video_decoder.read_frame.return_value = DecodedVideoFrame(
        pts=1.0, rgb_data=b"\x00" * (16 * 16 * 3), width=16, height=16
    )

    assert session.quality_manager.current_profile.id == "native"

    # Click on footer row (row 23) in the region of [q] Quality/Res (col 25)
    click_event = MouseEvent(button=0, col=25, row=23, is_pressed=True)
    session._on_tick(0.016, [click_event])
    assert session.quality_manager.current_profile.id != "native"


def test_coordinator_subtitle_cycling(tmp_path: Path):
    """Verifies that subtitle tracks can be cycled through properly."""
    from pinak.media.player.coordinator import MediaSession
    from pinak.media.subtitles.model import SubtitleTrack

    fake_file = tmp_path / "movie.mp4"
    fake_file.write_bytes(b"dummy")

    session = MediaSession([fake_file], enable_consent_prompt=False)
    assert session.cycle_subtitles() == "No Subtitles"

    # Add 2 subtitle tracks
    session.subtitle_tracks = [
        SubtitleTrack(track_id=0, title="English", language="eng", cues=[]),
        SubtitleTrack(track_id=1, title="Spanish", language="spa", cues=[]),
    ]
    session.active_sub_idx = -1

    # Cycle 1: track 0 (English)
    assert session.cycle_subtitles() == "English"
    assert session.active_sub_idx == 0

    # Cycle 2: track 1 (Spanish)
    assert session.cycle_subtitles() == "Spanish"
    assert session.active_sub_idx == 1

    # Cycle 3: Off (-1)
    assert session.cycle_subtitles() == "Off"
    assert session.active_sub_idx == -1

    # Cycle 4: wraps back to English (0)
    assert session.cycle_subtitles() == "English"
    assert session.active_sub_idx == 0


def test_coordinator_action_keys_and_window(tmp_path: Path, monkeypatch):
    """Verifies action keys: c (subtitles), w (window), space (play/pause), seek, volume."""
    from unittest.mock import MagicMock

    from pinak.media.player.coordinator import MediaSession

    fake_file = tmp_path / "movie.mp4"
    fake_file.write_bytes(b"dummy")

    session = MediaSession([fake_file], enable_consent_prompt=False)
    session.video_decoder = MagicMock()
    session.audio_backend = MagicMock()

    # Test space (play/pause)
    assert session.transport.is_playing is True
    session._handle_action_key("space", 80, 24)
    assert session.transport.is_playing is False
    session._handle_action_key("space", 80, 24)
    assert session.transport.is_playing is True

    # Test seek
    session.transport.current_pts = 20.0
    session._handle_action_key("left", 80, 24)
    assert session.transport.current_pts == 10.0
    session._handle_action_key("right", 80, 24)
    assert session.transport.current_pts == 20.0

    # Test volume & mute: ctrl+m for mute, m for mode cycling
    session._handle_action_key("up", 80, 24)
    assert session.transport.volume == 1.05
    session._handle_action_key("down", 80, 24)
    assert session.transport.volume == 1.0
    session._handle_action_key("ctrl+m", 80, 24)
    assert session.transport.is_muted is True
    session._handle_action_key("ctrl+m", 80, 24)
    assert session.transport.is_muted is False

    # Test 'm' key cycles rendering mode in TUI
    old_mode = session.renderer.mode_name
    session._handle_action_key("m", 80, 24)
    assert session.renderer.mode_name != old_mode

    # Test toggle native window
    def mock_open_fn(self_win):
        self_win.is_open = True
        return True

    monkeypatch.setattr("pinak.media.window.native_window.NativeVideoWindow.open", mock_open_fn)

    opened = session.toggle_native_window()
    assert opened is True
    assert session.native_window is not None
    assert session.native_window.is_open is True
    assert session.native_window.initial_scale == 0.5

    # Toggle again -> closes window
    closed = session.toggle_native_window()
    assert closed is False
    assert session.native_window is None

    # The smaller opening is specific to video; picture windows keep their size.
    session.picture_viewer = MagicMock()
    assert session.toggle_native_window() is True
    assert session.native_window is not None
    assert session.native_window.initial_scale == 1.0
    session.toggle_native_window()


def test_coordinator_ipc_integration(tmp_path):
    """Authenticated socket controls are applied by the session thread."""
    import threading
    import time

    from pinak.media.ipc.client import MediaIPCClient
    from pinak.media.player.coordinator import MediaSession

    path = tmp_path / "movie.mp4"
    path.write_bytes(b"dummy")
    session = MediaSession([path], enable_consent_prompt=False, ipc_port=0)
    session.is_running = True
    port = session.ipc_server.start()
    responses = []

    def remote_control():
        client = MediaIPCClient(port=port, auth_token=session.ipc_server.auth_token)
        responses.append(client.send_command("get_property", "pause"))
        responses.append(client.send_command("set_property", "pause", True))

    worker = threading.Thread(target=remote_control)
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while worker.is_alive() and time.monotonic() < deadline:
            session._on_tick(0.01, [])
            time.sleep(0.005)
        worker.join(timeout=0.2)
        assert not worker.is_alive()
        assert all(r["error"] == "success" for r in responses)
        assert responses[0]["data"] is False
        assert session.transport.is_playing is False
    finally:
        session.is_running = False
        session.ipc_server.stop()


def test_media_command_window_cli_flag(tmp_path: Path, monkeypatch):
    """Verifies that --window, --gui, and -w flags set enable_native_window=True."""
    from unittest.mock import MagicMock

    from pinak.commands.media import _play_or_browse

    mock_session_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.start.return_value = "close_media"
    mock_session_cls.return_value = mock_instance

    monkeypatch.setattr("pinak.commands.media.MediaSession", mock_session_cls)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    fake_file = tmp_path / "video.mp4"
    fake_file.write_bytes(b"dummy")

    _play_or_browse([str(fake_file), "--window"])

    assert mock_session_cls.called
    kwargs = mock_session_cls.call_args[1]
    assert kwargs.get("enable_native_window") is True


def test_audio_thumbnail_blitted_to_gpu_window(tmp_path):
    """Verifies that in audio mode, opening GPU window blits the album thumbnail."""
    from unittest.mock import MagicMock

    from PIL import Image

    from pinak.media.decoders.probe import MediaMetadata
    from pinak.media.player.coordinator import MediaSession

    fake_mp3 = tmp_path / "song.mp3"
    fake_mp3.write_bytes(b"dummy")

    session = MediaSession([fake_mp3])
    session._current_meta = MediaMetadata(
        media_type="audio",
        file_path=fake_mp3,
        file_size_bytes=1000,
        duration_seconds=120.0,
        album_art_bytes=None,
    )
    session.turntable = MagicMock()
    session.turntable.render_turntable.return_value = Image.new("RGB", (200, 200), (80, 40, 20))
    session.audio_decoder = MagicMock()
    session.audio_decoder.get_visualizer_samples.return_value = [0.0] * 1024

    mock_win = MagicMock()
    mock_win.is_open = True
    session.native_window = mock_win

    out = session._render_media_tui(cols=80, rows=24, dt=0.033)
    assert len(out) > 0
    assert mock_win.show_frame.called
    shown_img = mock_win.show_frame.call_args[0][0]
    assert isinstance(shown_img, Image.Image)


def test_video_player_guidance_notification(tmp_path):
    """Verifies that video player notifies user about pressing 'w' for GPU window when viewing in TUI."""
    from unittest.mock import MagicMock

    from pinak.media.decoders.probe import MediaMetadata
    from pinak.media.player.coordinator import MediaSession

    fake_mp4 = tmp_path / "video.mp4"
    fake_mp4.write_bytes(b"dummy")

    session = MediaSession([fake_mp4])
    session._current_meta = MediaMetadata(
        media_type="video",
        file_path=fake_mp4,
        file_size_bytes=5000,
        duration_seconds=60.0,
        width=1920,
        height=1080,
    )
    session.video_decoder = MagicMock()
    session.video_decoder.read_frame.return_value = None
    session.native_window = None  # Native GPU window NOT open

    out = session._render_media_tui(cols=80, rows=24, dt=0.033)
    # The notification tip instructing user to press [w] for GPU window must be visible in TUI
    assert "Press [w]" in out or "[w] GPU" in out
    assert "GPU Window" in out


def test_coordinator_render_with_fallback_degradation(tmp_path: Path):
    """Verifies that MediaSession._render_with_fallback catches render errors and degrades gracefully (FALLBACK-03)."""
    from unittest.mock import MagicMock

    from PIL import Image

    from pinak.media.player.coordinator import MediaSession
    from pinak.media.renderers.pixel_kitty import KittyRenderer

    fake_mp4 = tmp_path / "video.mp4"
    fake_mp4.write_bytes(b"dummy")

    session = MediaSession([fake_mp4], enable_consent_prompt=False)
    kitty = KittyRenderer()
    session.renderer = kitty

    # Mock kitty.render_frame and render_braille to simulate broken escape stream
    session.renderer.render_frame = MagicMock(
        side_effect=RuntimeError("Kitty graphics stream broken")
    )
    session.renderer.render_braille = MagicMock(
        side_effect=RuntimeError("Kitty graphics stream broken")
    )

    img = Image.new("RGB", (64, 32))
    # Should catch error, call FallbackManager.degrade_renderer(), and degrade to halfblock
    res = session._render_with_fallback(img, target_cols=40, target_rows=16)

    assert session.renderer.mode_name == "halfblock"
    assert isinstance(res, str)


def test_coordinator_unknown_duration_eos_advance(tmp_path: Path):
    """Verifies that unknown duration streams (dur <= 0) auto-advance when audio_backend.is_eos is True (FALLBACK-05)."""
    from unittest.mock import MagicMock

    from pinak.media.player.coordinator import MediaSession

    f1 = tmp_path / "track1.mp3"
    f2 = tmp_path / "track2.mp3"
    f1.write_bytes(b"dummy1")
    f2.write_bytes(b"dummy2")

    session = MediaSession([f1, f2], enable_consent_prompt=False)
    session.transport.is_playing = True
    session.transport.duration_sec = 0.0  # Unknown duration / live stream
    session.master_clock.get_time = MagicMock(return_value=1.5)  # master_pts > 0.5

    mock_backend = MagicMock()
    mock_backend.is_eos = True
    session.audio_backend = mock_backend

    # Mock _advance_track
    advanced = []
    session._advance_track = lambda delta: advanced.append(delta)

    session._render_media_tui(80, 24, 0.016)
    assert len(advanced) == 1
    assert advanced[0] == 1


def test_coordinator_video_av_sync_frame_pacing(tmp_path: Path):
    """Verifies that video playback presentation tracks master audio clock with frame pacing and dropping."""
    from unittest.mock import MagicMock

    from pinak.media.decoders.probe import MediaMetadata
    from pinak.media.decoders.video_decoder import DecodedVideoFrame
    from pinak.media.player.coordinator import MediaSession

    fake_mp4 = tmp_path / "sync_test.mp4"
    fake_mp4.write_bytes(b"dummy")

    session = MediaSession([fake_mp4], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="video",
        file_path=fake_mp4,
        file_size_bytes=1000,
        duration_seconds=30.0,
        width=160,
        height=90,
    )
    mock_dec = MagicMock()
    mock_dec.target_fps = 30.0
    mock_dec.target_w = 160
    mock_dec.target_h = 90
    session.video_decoder = mock_dec
    session.transport.is_playing = True

    dummy_rgb = b"\x00" * (160 * 90 * 3)
    frame0 = DecodedVideoFrame(pts=0.000, width=160, height=90, rgb_data=dummy_rgb)
    frame1 = DecodedVideoFrame(pts=0.033, width=160, height=90, rgb_data=b"\x55" * (160 * 90 * 3))
    frame2 = DecodedVideoFrame(pts=0.066, width=160, height=90, rgb_data=b"\xaa" * (160 * 90 * 3))
    frame3 = DecodedVideoFrame(pts=0.100, width=160, height=90, rgb_data=b"\xff" * (160 * 90 * 3))

    frames_queue = [frame0, frame1, frame2, frame3]

    def mock_read():
        if frames_queue:
            return frames_queue.pop(0)
        return DecodedVideoFrame(pts=15.0, width=160, height=90, rgb_data=dummy_rgb)

    mock_dec.read_frame.side_effect = mock_read

    # Tick 1: master_pts = 0.000. frame0 presented
    session.master_clock.get_time = MagicMock(return_value=0.000)
    session._render_media_tui(80, 24, dt=0.016)
    assert session._last_video_img is not None
    assert session._buffered_video_frame == frame0

    # Tick 2: master_pts = 0.010 (audio at 10ms, next frame threshold is 16.5ms)
    # Ahead of audio clock -> MUST hold previous frame, NOT consume next frame
    session.master_clock.get_time = MagicMock(return_value=0.010)
    session._render_media_tui(80, 24, dt=0.016)
    assert session._buffered_video_frame == frame0

    # Tick 3: master_pts = 0.033 (audio catches up to frame1 threshold)
    # Frame 1 read and presented
    session.master_clock.get_time = MagicMock(return_value=0.033)
    session._render_media_tui(80, 24, dt=0.016)
    assert session._buffered_video_frame == frame1

    # Lag spike / frame drop: master_pts jumps to 0.100 (audio is at 100ms, frame2 is at 66ms)
    # Stale frame2 dropped, frame3 presented
    session.master_clock.get_time = MagicMock(return_value=0.100)
    session._render_media_tui(80, 24, dt=0.016)
    assert session._buffered_video_frame == frame3

    # Hard desync: audio clock jumps to 15.0s (> 1.0s difference)
    seek_pts = []
    mock_dec.seek.side_effect = lambda pts: seek_pts.append(pts)
    session._buffered_video_frame = DecodedVideoFrame(
        pts=0.200, width=160, height=90, rgb_data=dummy_rgb
    )
    session.master_clock.get_time = MagicMock(return_value=15.0)
    session._render_media_tui(80, 24, dt=0.016)
    assert 15.0 in seek_pts


def test_coordinator_video_repeat_mode_cycling(tmp_path: Path):
    """Verifies that repeat mode can be toggled with 'r' in video player and reflects in footer and header."""
    from unittest.mock import MagicMock

    from pinak.media.decoders.probe import MediaMetadata
    from pinak.media.player.coordinator import MediaSession

    video_file = tmp_path / "movie.mp4"
    audio_file = tmp_path / "song.mp3"
    video_file.write_bytes(b"dummy_video")
    audio_file.write_bytes(b"dummy_audio")

    session = MediaSession([video_file, audio_file], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="video",
        file_path=video_file,
        file_size_bytes=1000,
        duration_seconds=60.0,
        width=1920,
        height=1080,
    )
    session.video_decoder = MagicMock()

    # Video repeat mode starts at none (OFF)
    session._init_media_components()
    assert session.playlist_manager.repeat_mode == "none"

    # Header and footer checks for video: [r] Repeat must be present
    hdr = session._build_responsive_header(130, "movie.mp4")
    assert "Rep: OFF" in hdr
    ftr = session._build_responsive_footer(130)
    assert "[r] Repeat" in ftr

    # Pressing 'r' in video mode cycles repeat mode: none -> all -> solo -> none
    session._handle_action_key("r", 80, 24)
    assert session.playlist_manager.repeat_mode == "all"
    hdr_all = session._build_responsive_header(130, "movie.mp4")
    assert "Rep: ALL" in hdr_all

    session._handle_action_key("r", 80, 24)
    assert session.playlist_manager.repeat_mode == "solo"
    hdr_solo = session._build_responsive_header(130, "movie.mp4")
    assert "Rep: SOLO" in hdr_solo

    session._handle_action_key("r", 80, 24)
    assert session.playlist_manager.repeat_mode == "none"
    hdr_off = session._build_responsive_header(130, "movie.mp4")
    assert "Rep: OFF" in hdr_off


def test_coordinator_music_visualizer_pause_freeze(tmp_path: Path):
    """Verifies that pausing music freezes the audio visualizer graph and stops animation/decay."""
    import math
    from unittest.mock import MagicMock

    from pinak.media.decoders.probe import MediaMetadata
    from pinak.media.player.coordinator import MediaSession
    from pinak.media.visualizer.turntable import GramophoneTurntable

    audio_file = tmp_path / "track.mp3"
    audio_file.write_bytes(b"dummy")

    session = MediaSession([audio_file], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="audio",
        file_path=audio_file,
        file_size_bytes=1000,
        duration_seconds=120.0,
    )
    session.turntable = GramophoneTurntable(diameter=120)
    session.audio_decoder = MagicMock()
    # Provide 440 Hz sinusoidal PCM samples
    sine_pcm = [0.8 * math.sin(2.0 * math.pi * 440.0 * i / 48000.0) for i in range(1024)]
    session.audio_decoder.get_visualizer_samples.return_value = sine_pcm
    session.master_clock.get_time = MagicMock(return_value=10.0)
    session.transport.is_playing = True

    # Render while playing
    session._render_media_tui(80, 24, dt=0.016)
    assert session._frozen_visualizer_bands is not None
    assert any(b > 0.0 for b in session._frozen_visualizer_bands)

    # Pause playback
    session.transport.is_playing = False

    # Render multiple ticks while paused
    out_paused1 = session._render_media_tui(80, 24, dt=0.016)
    out_paused2 = session._render_media_tui(80, 24, dt=0.016)
    out_paused3 = session._render_media_tui(80, 24, dt=0.100)

    # All paused frames must be strictly identical (frozen graph, no moving waves, no peak decay)
    assert out_paused1 == out_paused2
    assert out_paused2 == out_paused3


def test_coordinator_video_completion_sequence_and_stop_at_first_video(tmp_path: Path, monkeypatch):
    """Verifies that in Repeat OFF, videos continue in sequence, and after all videos finish, TUI leads to first video and stops."""
    from dataclasses import replace
    from unittest.mock import MagicMock

    from pinak.media.decoders.probe import MediaMetadata, MediaProbe
    from pinak.media.player.coordinator import MediaSession

    vid1 = tmp_path / "vid1.mp4"
    vid2 = tmp_path / "vid2.mp4"
    vid1.write_bytes(b"dummy1")
    vid2.write_bytes(b"dummy2")

    session = MediaSession([vid1, vid2], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="video",
        file_path=vid1,
        file_size_bytes=1000,
        duration_seconds=10.0,
        width=160,
        height=90,
    )
    session.video_decoder = MagicMock()
    session.audio_backend = MagicMock()
    session.transport.duration_sec = 10.0
    session.transport.is_playing = True
    session.playlist_manager.current_idx = 0
    assert session.playlist_manager.has_next() is True

    metadata = session._current_meta
    monkeypatch.setattr(MediaProbe, "probe", lambda path: replace(metadata, file_path=path))

    def initialize_components():
        session.video_decoder = MagicMock()
        session.video_decoder.read_frame.return_value = None
        session.audio_backend = MagicMock()
        session.master_clock = MagicMock()
        session.master_clock.get_time.return_value = 0.0

    monkeypatch.setattr(session, "_init_media_components", initialize_components)

    # 1. Simulate completion of vid1: master_pts >= dur
    session.master_clock.get_time = MagicMock(return_value=10.5)
    session._render_media_tui(80, 24, dt=0.016)

    # In Repeat OFF: videos continue in sequence -> auto-advances to vid2!
    assert session.playlist_manager.current_idx == 1

    # 2. Simulate completion of vid2 (the last video in playlist)
    session.transport.duration_sec = 15.0
    session.transport.is_playing = True
    session.master_clock.get_time = MagicMock(return_value=15.5)
    assert session.playlist_manager.has_next() is False

    session._render_media_tui(80, 24, dt=0.016)

    # After playing all videos, TUI leads to first video (index 0) and stops!
    assert session.playlist_manager.current_idx == 0
    assert session.transport.is_playing is False
    session.audio_backend.pause.assert_called_once()

    # User can start playback by clicking space
    session._handle_action_key("space", 80, 24)
    assert session.transport.is_playing is True


def test_coordinator_ctrl_m_mute_toggle(tmp_path: Path):
    """Verifies that Ctrl+M shortcut reliably mutes and unmutes audio in coordinator."""
    from unittest.mock import MagicMock

    from pinak.media.core.input_parser import KeyEvent
    from pinak.media.decoders.probe import MediaMetadata
    from pinak.media.player.coordinator import MediaSession

    song = tmp_path / "song.mp3"
    song.write_bytes(b"dummy")

    session = MediaSession([song], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="audio",
        file_path=song,
        file_size_bytes=1000,
        duration_seconds=60.0,
    )
    session.audio_backend = MagicMock()
    session.transport.volume = 0.8
    session.transport.is_muted = False

    # Dispatch KeyEvent with key="m" and ctrl=True
    session._on_tick(0.016, [KeyEvent(key="m", ctrl=True)])
    assert session.transport.is_muted is True
    session.audio_backend.toggle_mute.assert_called_once()

    # Second press unmutes
    session._on_tick(0.016, [KeyEvent(key="m", ctrl=True)])
    assert session.transport.is_muted is False
    assert session.audio_backend.toggle_mute.call_count == 2


def test_input_parser_ctrl_m_detection():
    """Verifies that InputParser detects Ctrl+M across CSI u sequences and Windows console reads."""
    import ctypes
    from types import SimpleNamespace
    from unittest.mock import Mock, patch

    from pinak.media.core.input_parser import InputParser

    parser = InputParser()

    # 1. CSI u key sequence for Ctrl+M
    ev, consumed = parser._parse_next_event(b"\x1b[109;5u")
    assert ev is not None
    assert ev.key == "m"
    assert ev.ctrl is True

    # 2. Windows Enter with Control held down (GetAsyncKeyState returns high bit set)
    key_state = Mock(return_value=-32767)
    windows_api = SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=key_state))
    with (
        patch("pinak.media.core.input_parser.sys.platform", "win32"),
        patch.object(ctypes, "windll", windows_api, create=True),
    ):
        ev, consumed = parser._parse_next_event(b"\r")
        assert ev is not None
        assert ev.key == "m"
        assert ev.ctrl is True

    # 3. Normal Enter without Control held down
    key_state.return_value = 0
    with (
        patch("pinak.media.core.input_parser.sys.platform", "win32"),
        patch.object(ctypes, "windll", windows_api, create=True),
    ):
        ev, consumed = parser._parse_next_event(b"\r")
        assert ev is not None
        assert ev.key == "enter"
        assert ev.ctrl is False
