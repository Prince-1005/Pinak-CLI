"""An open native window survives track changes while media resources are replaced."""

from io import BytesIO
from unittest.mock import MagicMock

import pytest
from PIL import Image

from pinak.media.decoders.probe import MediaMetadata
from pinak.media.decoders.video_decoder import DecodedVideoFrame
from pinak.media.player import coordinator


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    def make(kinds):
        paths = [
            tmp_path / f"item-{i}.{'mp3' if kind == 'audio' else 'mp4'}"
            for i, kind in enumerate(kinds)
        ]
        metadata = {}
        colors = [(255, 0, 0), (0, 0, 255)]
        for path, kind, color in zip(paths, kinds, colors, strict=True):
            path.write_bytes(b"fixture")
            artwork = BytesIO()
            Image.new("RGB", (16, 16), color).save(artwork, format="PNG")
            metadata[path] = MediaMetadata(
                media_type=kind,
                file_path=path,
                file_size_bytes=7,
                duration_seconds=10.0,
                width=16 if kind == "video" else 0,
                height=16 if kind == "video" else 0,
                album_art_bytes=artwork.getvalue() if kind == "audio" else None,
            )
        monkeypatch.setattr(coordinator.MediaProbe, "probe", lambda path: metadata[path])
        monkeypatch.setattr(
            coordinator, "AudioPlayerBackend", lambda *a: MagicMock(error=None, is_eos=False)
        )
        decoder = MagicMock()
        decoder.get_visualizer_samples.return_value = [0.0] * 1024
        monkeypatch.setattr(coordinator, "AudioDecoder", lambda *a: decoder)

        def video(path, **kwargs):
            color = colors[paths.index(path)]
            result = MagicMock(error=None, eof=False, target_fps=30)
            result.read_frame.return_value = DecodedVideoFrame(0.0, 16, 16, bytes(color) * 256)
            return result

        monkeypatch.setattr(coordinator, "VideoDecoder", video)
        monkeypatch.setattr(
            coordinator, "MasterAudioClock", lambda *a: MagicMock(get_time=lambda: 0.0)
        )
        table = MagicMock()
        table.render_turntable.return_value = Image.new("RGB", (16, 16), "green")
        monkeypatch.setattr(coordinator, "GramophoneTurntable", lambda **kw: table)
        session = coordinator.MediaSession(paths, enable_consent_prompt=False)
        monkeypatch.setattr(session._subtitle_loader, "load", lambda path: None)
        monkeypatch.setattr(session, "_render_with_fallback", lambda *a, **kw: "")
        session._current_meta = metadata[paths[0]]
        session._init_media_components()
        window = MagicMock(is_open=True, is_fullscreen=True)
        window.show_frame.return_value = []
        session.native_window = window
        session.enable_native_window = True
        return session, window, paths

    return make


@pytest.mark.parametrize(
    "kinds", [("audio", "audio"), ("video", "video"), ("audio", "video"), ("video", "audio")]
)
@pytest.mark.parametrize("shuffle", [False, True])
def test_completion_reuses_window_and_displays_next_media(session_factory, kinds, shuffle):
    session, window, paths = session_factory(kinds)
    old_audio, old_video = session.audio_backend, session.video_decoder
    session._cached_audio_thumb = Image.new("RGB", (16, 16), "red")
    session._last_video_img = Image.new("RGB", (16, 16), "red")
    if shuffle:
        session.playlist_manager.toggle_shuffle()
    session.master_clock.get_time = lambda: 10.5
    session._render_media_tui(100, 24, 0.016)
    assert session.playlist_manager.get_current() == paths[1]
    assert session.native_window is window and window.is_open and window.is_fullscreen
    window.close.assert_not_called()
    window.open.assert_not_called()
    window.set_title.assert_called_once()
    assert paths[1].name in window.set_title.call_args.args[0]
    old_audio.stop.assert_called_once()
    if old_video:
        old_video.close.assert_called_once()
    image = window.show_frame.call_args.args[0]
    assert image.getpixel((0, 0)) == (0, 0, 255)
    state = window.show_frame.call_args.kwargs["state"]
    assert state.title == paths[1].name and state.current_pts == 0.0
    session._teardown_media_components()
    window.close.assert_called_once()
    assert session.native_window is None


@pytest.mark.parametrize("mode", ["all", "solo"])
def test_repeat_and_manual_navigation_keep_window(session_factory, mode):
    session, window, paths = session_factory(("video", "video"))
    session.playlist_manager.repeat_mode = mode
    session._advance_track(1)
    assert session.playlist_manager.get_current() == paths[0 if mode == "solo" else 1]
    session._handle_action_key("n", 100, 24)
    session._handle_action_key("p", 100, 24)
    assert session.native_window is window and window.is_open
    window.close.assert_not_called()


def test_playlist_end_keeps_window_open_on_paused_first_video(session_factory):
    session, window, paths = session_factory(("video", "video"))
    session._advance_track(1)
    session.master_clock.get_time = lambda: 10.5
    session._render_media_tui(100, 24, 0.016)
    assert session.playlist_manager.get_current() == paths[0]
    assert not session.transport.is_playing
    assert session.native_window is window
    window.close.assert_not_called()


def test_user_closed_window_is_not_reopened_by_track_change(session_factory):
    session, window, _ = session_factory(("video", "video"))
    window.is_open = False
    session._advance_track(1)
    assert session.native_window is None
    window.open.assert_not_called()
