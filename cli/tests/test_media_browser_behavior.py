"""Media browser visibility, cursor restoration and music boundary behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pinak.commands.media import handle_media_command
from pinak.media.core.input_parser import KeyEvent
from pinak.media.decoders.probe import MediaMetadata
from pinak.media.picker.fuzzy_search import FuzzyMediaFilter
from pinak.media.picker.scanner import MediaScanner
from pinak.media.picker.tui_picker import TUIMediaPicker
from pinak.media.player.coordinator import MediaSession
from pinak.media.player.playlist import PlaylistManager


def test_picker_shows_every_file_but_opens_only_supported_media(tmp_path: Path) -> None:
    folder = tmp_path / "Folder"
    folder.mkdir()
    for name in ("song.mp3", "film.mp4", "picture.png", "report.docx", ".hidden.txt"):
        (tmp_path / name).write_bytes(b"content")

    picker = TUIMediaPicker(tmp_path)
    names = {item.name for item in picker.all_items}
    assert names.issuperset(
        {"Folder", "song.mp3", "film.mp4", "picture.png", "report.docx", ".hidden.txt"}
    )
    assert len(MediaScanner.scan_directory(tmp_path)) == len(picker.all_items)
    assert [item.name for item in FuzzyMediaFilter.filter_items(picker.all_items, "song")] == [
        ".. [Parent Directory]",
        "song.mp3",
    ]

    unsupported = tmp_path / "report.docx"
    picker.focus_path(unsupported)
    output = picker.render_tui(100, 24)
    assert "[FILE]" in output
    assert "UNSUPPORTED FILE" in output
    assert "cannot be opened" in output
    assert picker.select_current() is None
    assert picker.current_dir == tmp_path

    picker.handle_input(KeyEvent("p"))
    picker.handle_input(KeyEvent(str(unsupported)))
    _, chosen = picker.handle_input(KeyEvent("enter"))
    assert chosen is None
    assert "cannot be opened" in picker.path_error

    for filename in ("song.mp3", "film.mp4", "picture.png"):
        path = tmp_path / filename
        picker.focus_path(path)
        assert picker.select_current() == path


def test_picker_default_scan_does_not_hide_files_after_old_limit(tmp_path: Path) -> None:
    for index in range(2005):
        (tmp_path / f"item{index:04d}.txt").touch()

    items = MediaScanner.scan_directory(tmp_path)
    assert len(items) == 2006  # Parent row and every direct child.
    assert any(item.name == "item2004.txt" for item in items)
    assert not any("Capped at" in item.name for item in items)


def test_picker_restores_folder_and_file_selection(tmp_path: Path) -> None:
    folder = tmp_path / "Album"
    folder.mkdir()
    first = folder / "track1.mp3"
    second = folder / "track2.mp3"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    picker = TUIMediaPicker(tmp_path)
    picker.focus_path(folder)
    assert picker.select_current() is None
    picker.focus_path(second)
    assert picker.visible_items[picker.cursor_idx].path == second

    picker.ascend_directory()
    assert picker.visible_items[picker.cursor_idx].path == folder
    assert picker.select_current() is None
    assert picker.visible_items[picker.cursor_idx].path == second

    picker.cursor_idx = 0  # Parent row uses the same restoration path.
    assert picker.select_current() is None
    assert picker.visible_items[picker.cursor_idx].path == folder


def test_picker_restores_path_input_file_hidden_by_search(tmp_path: Path) -> None:
    selected = tmp_path / "bar.mp3"
    selected.write_bytes(b"song")
    (tmp_path / "foo.mp3").write_bytes(b"song")

    picker = TUIMediaPicker(tmp_path)
    picker.search_query = "foo"
    picker._refresh_directory()
    picker.handle_input(KeyEvent("p"))
    picker.handle_input(KeyEvent(str(selected)))
    _, chosen = picker.handle_input(KeyEvent("enter"))
    assert chosen == selected

    picker.focus_path(chosen)
    assert picker.search_query == ""
    assert picker.visible_items[picker.cursor_idx].path == selected


def test_picker_survives_returning_from_playback(tmp_path: Path) -> None:
    selected = tmp_path / "second.mp3"
    selected.write_bytes(b"song")
    (tmp_path / "first.mp3").write_bytes(b"song")
    seen: list[TUIMediaPicker] = []

    def choose(picker: TUIMediaPicker) -> Path | None:
        seen.append(picker)
        if len(seen) == 1:
            picker.focus_path(selected)
            return picker.select_current()
        assert picker.visible_items[picker.cursor_idx].path == selected
        return None

    with (
        patch("pinak.commands.media._run_picker_loop", side_effect=choose),
        patch("pinak.commands.media.MediaSession"),
        patch("pinak.commands.media.sys.stdin") as stdin,
    ):
        stdin.isatty.return_value = True
        handle_media_command([str(tmp_path)])

    assert len(seen) == 2
    assert seen[0] is seen[1]


def test_direct_file_return_focuses_opened_file(tmp_path: Path) -> None:
    selected = tmp_path / "track.mp3"
    selected.write_bytes(b"song")
    (tmp_path / "another.mp3").write_bytes(b"song")

    def close_picker(picker: TUIMediaPicker) -> None:
        assert picker.visible_items[picker.cursor_idx].path == selected
        return None

    with (
        patch("pinak.commands.media._run_picker_loop", side_effect=close_picker) as run_picker,
        patch("pinak.commands.media.MediaSession") as media_session,
        patch("pinak.commands.media.sys.stdin") as stdin,
    ):
        stdin.isatty.return_value = True
        handle_media_command([str(selected)])
    media_session.assert_called_once()
    run_picker.assert_called_once()


def test_direct_unsupported_file_is_not_played(tmp_path: Path) -> None:
    document = tmp_path / "notes.docx"
    document.write_bytes(b"document")
    with (
        patch("pinak.commands.media.MediaSession") as media_session,
        patch("pinak.commands.media.sys.stdin") as stdin,
    ):
        stdin.isatty.return_value = False
        handle_media_command([str(document)])
    media_session.assert_not_called()


def test_music_playlist_wraps_manual_and_at_completion(tmp_path: Path) -> None:
    tracks = [tmp_path / f"track{i}.mp3" for i in range(3)]
    for track in tracks:
        track.write_bytes(b"song")

    playlist = PlaylistManager(tracks, initial_index=2)
    assert playlist.next_track(wrap=True, manual=True) == tracks[0]
    assert playlist.prev_track(wrap=True) == tracks[2]
    playlist.current_idx = 0
    assert playlist.prev_track(wrap=True) == tracks[2]
    playlist.repeat_mode = "solo"
    assert playlist.next_track(wrap=True, manual=True) == tracks[0]
    assert playlist.next_track(wrap=True) == tracks[0]  # Solo still repeats on completion.

    session = MediaSession(tracks, initial_index=2, enable_consent_prompt=False)
    session._current_meta = MediaMetadata(
        media_type="audio", file_path=tracks[2], file_size_bytes=4, duration_seconds=1.0
    )
    session.transport.duration_sec = 1.0
    session.transport.is_playing = True
    session.master_clock.get_time = MagicMock(return_value=1.1)
    with patch.object(session, "_advance_track") as advance:
        session._handle_action_key("n", 80, 24)
        advance.assert_called_once_with(delta=1, wrap=True, manual=True)
        advance.reset_mock()
        session._handle_action_key("p", 80, 24)
        advance.assert_called_once_with(delta=-1, wrap=True, manual=True)
        advance.reset_mock()
        advance.side_effect = StopIteration
        with pytest.raises(StopIteration):
            session._render_media_tui(80, 24, dt=0.016)
        advance.assert_called_once_with(delta=1, wrap=True)


def test_audio_native_window_opens_compactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    song = tmp_path / "song.mp3"
    song.write_bytes(b"song")
    session = MediaSession([song], enable_consent_prompt=False)
    session._current_meta = MediaMetadata(media_type="audio", file_path=song, file_size_bytes=4)
    session.audio_decoder = MagicMock()

    def open_window(window, initial_size=None):
        window.is_open = True
        return True

    monkeypatch.setattr("pinak.media.window.native_window.NativeVideoWindow.open", open_window)
    assert session.toggle_native_window() is True
    assert session.native_window is not None
    assert session.native_window.initial_scale == 0.5
    session.toggle_native_window()
