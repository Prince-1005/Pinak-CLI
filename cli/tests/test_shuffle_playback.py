"""Shuffle chooses from the correct pool and stops audio/video at exhaustion."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from pinak.media.decoders.probe import MediaMetadata, MediaProbe
from pinak.media.player.coordinator import MediaSession
from pinak.media.player.playlist import PlaylistManager


def tracks(tmp_path, extension="mp3", count=5):
    paths = [tmp_path / f"track-{index}.{extension}" for index in range(count)]
    for path in paths:
        path.write_bytes(b"fixture")
    return paths


def test_shuffle_off_repeat_visits_only_unplayed_even_with_music_wrap(tmp_path, monkeypatch):
    paths = tracks(tmp_path)
    playlist = PlaylistManager(paths, initial_index=2)
    playlist.toggle_shuffle()
    pools = []

    def choose(pool):
        pools.append(list(pool))
        return pool[-1]

    monkeypatch.setattr("pinak.media.player.playlist.random.choice", choose)
    visited = [playlist.get_current()]
    while playlist.has_next():
        visited.append(playlist.next_track(wrap=True))
    assert set(visited) == set(paths) and len(visited) == len(paths)
    assert pools == [[0, 1, 3, 4], [0, 1, 3], [0, 1], [0]]
    last = playlist.get_current()
    assert playlist.next_track(wrap=True, manual=True) is None
    assert playlist.get_current() == last


def test_shuffle_on_repeat_draws_from_full_list_each_time(tmp_path, monkeypatch):
    paths = tracks(tmp_path)
    playlist = PlaylistManager(paths, repeat_mode="all")
    playlist.toggle_shuffle()
    choices = iter([4, 4, 0, 3, 1, 0, 2])

    def choose(pool):
        assert pool == list(range(len(paths)))
        return next(choices)

    monkeypatch.setattr("pinak.media.player.playlist.random.choice", choose)
    assert [playlist.next_track() for _ in range(7)] == [paths[i] for i in [4, 4, 0, 3, 1, 0, 2]]


def test_shuffle_solo_repeats_current_and_toggle_preserves_history(tmp_path, monkeypatch):
    paths = tracks(tmp_path)
    playlist = PlaylistManager(paths, initial_index=1)
    assert playlist.next_track() == paths[2]
    playlist.toggle_shuffle()
    assert playlist.get_current() == paths[2]
    playlist.repeat_mode = "solo"
    monkeypatch.setattr(
        "pinak.media.player.playlist.random.choice",
        lambda pool: pytest.fail("Solo completion must not choose another track"),
    )
    for _ in range(4):
        assert playlist.has_next() and playlist.next_track() == paths[2]
    playlist.repeat_mode = "none"
    assert playlist.prev_track() == paths[1]
    playlist.toggle_shuffle()
    assert playlist.get_current() == paths[1]
    assert playlist.next_track() == paths[2]


@pytest.mark.parametrize("count", [0, 1])
@pytest.mark.parametrize("mode", ["none", "all", "solo"])
def test_empty_and_single_track_shuffle(tmp_path, count, mode):
    paths = tracks(tmp_path, count=count)
    playlist = PlaylistManager(paths, repeat_mode=mode)
    playlist.toggle_shuffle()
    if not paths or mode == "none":
        assert not playlist.has_next()
        assert playlist.next_track(wrap=True) is None
    else:
        assert playlist.has_next()
        assert playlist.next_track() == paths[0]


@pytest.mark.parametrize("media_type,extension", [("audio", "mp3"), ("video", "mp4")])
@pytest.mark.parametrize("mode", ["none", "all", "solo"])
def test_tui_shuffle_controls_and_real_completion_transitions(
    tmp_path, monkeypatch, media_type, extension, mode
):
    paths = tracks(tmp_path, extension, count=3)
    session = MediaSession(paths, enable_consent_prompt=False)
    metadata = MediaMetadata(
        media_type=media_type,
        file_path=paths[0],
        file_size_bytes=7,
        duration_seconds=10.0,
        width=320 if media_type == "video" else 0,
        height=180 if media_type == "video" else 0,
    )
    session._current_meta = metadata
    monkeypatch.setattr(MediaProbe, "probe", lambda path: replace(metadata, file_path=path))
    monkeypatch.setattr(session, "_teardown_media_components", lambda **kwargs: None)

    def initialize():
        session.video_decoder = MagicMock() if media_type == "video" else None
        if session.video_decoder:
            session.video_decoder.read_frame.return_value = None
        session.audio_backend = MagicMock()
        session.audio_backend.is_eos = False
        session.master_clock = MagicMock()
        session.master_clock.get_time.return_value = 0.0
        session.transport.duration_sec = 10.0
        session.transport.is_playing = True

    monkeypatch.setattr(session, "_init_media_components", initialize)
    initialize()
    assert "Shuf: OFF" in session._build_responsive_header(100, paths[0].name)
    session._handle_action_key("s", 100, 24)
    assert session.playlist_manager.is_shuffled
    assert "Shuf: ON" in session._build_responsive_header(100, paths[0].name)
    for width in (48, 80, 130):
        assert "[s] Shuffle" in session._build_responsive_footer(width)
    session.playlist_manager.repeat_mode = mode
    monkeypatch.setattr("pinak.media.player.playlist.random.choice", lambda pool: pool[-1])
    visited = []
    for _ in range(3):
        session.master_clock.get_time.return_value = 10.5
        session._render_media_tui(100, 24, dt=0.016)
        visited.append(session.playlist_manager.get_current())
    if mode == "none":
        assert visited == [paths[2], paths[1], paths[1]]
        assert not session.transport.is_playing
        session.audio_backend.pause.assert_called_once()
        session.master_clock.pause.assert_called_once()
    else:
        assert visited == [paths[0] if mode == "solo" else paths[2]] * 3
        assert session.transport.is_playing
    session._handle_action_key("s", 100, 24)
    assert not session.playlist_manager.is_shuffled
