"""Library lifecycle, persistence, fallback and command integration."""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

import pytest

from pinak import library
from pinak.commands import library as commands


@pytest.fixture
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "data" / "library.db"
    monkeypatch.setattr(library, "DB_FILE", db)
    return db


def media(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"fixture media")
    return path


def test_scan_search_tags_collections_bookmarks_and_restart(catalog: Path, tmp_path: Path) -> None:
    root = tmp_path / "music 雲"
    first = media(root, "Guitar lesson.mp4")
    second = media(root / "nested", "Rhythm.mp3")
    (root / "text.txt").write_text("ignored", encoding="utf-8")
    assert library.scan(root)[:2] == (2, 0)
    assert library.scan(root)[:2] == (2, 0)
    assert len(library.list_items()) == 2
    item = library.get_by_path(first)
    assert item is not None
    assert library.search("guitar")[0].id == item.id
    library.tag_add(item.id, "Favorites")
    library.tag_add(item.id, "favorites")
    assert library.tags(item.id) == ["Favorites"]
    assert library.search("", tag="favorites")[0].id == item.id
    assert library.search("favorites")[0].id == item.id
    cid = library.collection_create("Course")
    other = library.get_by_path(second)
    assert other is not None
    library.collection_add(cid, item.id)
    library.collection_add(cid, other.id)
    library.collection_add(cid, other.id)
    assert [x.id for x in library.collection_items(cid)] == [item.id, other.id]
    library.collection_move(cid, other.id, item.id)
    library.collection_move(cid, item.id, item.id)
    assert [x.id for x in library.collection_items(cid)] == [other.id, item.id]
    bid = library.bookmark_add(item.id, 75, "Intro")
    library.save_position(first, 40, 180)
    assert library.bookmark_get(bid)[1:] == (75, "Intro")
    assert library.get(item.id).position == 40
    # A new connection sees saved organization and position.
    assert catalog.is_file()
    assert library.collection_list() == [(cid, "Course", 2)]
    assert library.bookmark_list(item.id) == [(bid, 75, "Intro")]
    library.save_position(first, 175, 180)
    assert library.get(item.id).position == 0


def test_download_indexing_and_scan_all_survive_missing_and_relink(
    catalog: Path, tmp_path: Path
) -> None:
    root = tmp_path / "saved"
    first = media(root, "song.wav")
    assert library.add_files((str(first), str(first))) == (2, 0)
    assert len(library.list_items()) == 1
    item = library.get_by_path(first)
    assert item is not None
    library.tag_add(item.id, "Keep")
    library.scan(root)
    first.unlink()
    assert library.scan_all()[:2] == (0, 0)
    assert not library.get(item.id).available
    assert library.tags(item.id) == ["Keep"]
    replacement = media(tmp_path / "moved", "song.wav")
    library.relink(item.id, replacement)
    assert library.get(item.id).available
    assert library.tags(item.id) == ["Keep"]
    library.forget(item.id)
    assert replacement.is_file()
    assert library.list_items() == []


def test_scan_symlink_and_partial_failure_preserve_records(
    catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    file = media(root, "keep.mp4")
    library.scan(root)
    item = library.get_by_path(file)
    assert item is not None
    outside = media(tmp_path / "outside", "escape.mp4")
    with contextlib.suppress(OSError, NotImplementedError):
        (root / "linked.mp4").symlink_to(outside)
    original = library._upsert

    def fail_once(conn: sqlite3.Connection, path: str | Path) -> int:
        if str(path).endswith("keep.mp4"):
            raise OSError("temporary read failure")
        return original(conn, path)

    monkeypatch.setattr(library, "_upsert", fail_once)
    assert library.scan(root)[1] == 1
    assert library.get(item.id).available
    assert len(library.list_items()) == 1
    with pytest.raises(ValueError):
        library.scan(root / "linked.mp4")


def test_search_falls_back_when_fts_is_unavailable(
    catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = media(tmp_path, "Film about Python.mp4")
    library.add_files((str(file),))
    original = library._connect

    class WithoutFTS:
        def __init__(self) -> None:
            self.connection = original()

        def execute(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Cursor:
            if "media_fts MATCH" in sql:
                raise sqlite3.OperationalError("no such module: fts5")
            return self.connection.execute(sql, params)

        def close(self) -> None:
            self.connection.close()

    monkeypatch.setattr(library, "_connect", WithoutFTS)
    assert len(library.search("Python")) == 1
    assert library.search("No match") == []


def test_existing_fts_triggers_are_disabled_without_fts_support(
    catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = media(tmp_path, "first.mp3")
    second = media(tmp_path, "second.mp3")
    library.add_files((str(first),))
    original = sqlite3.connect

    class WithoutFTS:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.connection = original(*args, **kwargs)

        def __getattr__(self, name: str) -> object:
            return getattr(self.connection, name)

        def __setattr__(self, name: str, value: object) -> None:
            if name == "connection":
                object.__setattr__(self, name, value)
            else:
                setattr(self.connection, name, value)

        def __enter__(self) -> WithoutFTS:
            self.connection.__enter__()
            return self

        def __exit__(self, *args: object) -> None:
            self.connection.__exit__(*args)

        def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
            if "SELECT rowid FROM media_fts" in sql or "media_fts MATCH" in sql:
                raise sqlite3.OperationalError("no such module: fts5")
            return self.connection.execute(sql, *args)

    monkeypatch.setattr(library.sqlite3, "connect", WithoutFTS)
    assert library.add_files((str(second),)) == (1, 0)
    assert len(library.search("second")) == 1
    with original(catalog) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
                "AND name LIKE 'media_fts_%'"
            ).fetchone()[0]
            == 0
        )


def test_commands_share_parser_and_keep_media(
    catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = media(tmp_path / "my media", "demo.mp4")
    assert commands.main(["scan", str(path.parent)]) == 0
    assert commands.run_repl("list --type video") == 0
    item = library.get_by_path(path)
    assert item is not None
    assert commands.run_repl(f'tag add {item.id} "My favorites"') == 0
    assert commands.main(["search", "", "--tag", "my favorites"]) == 0
    assert commands.main(["bookmark", "add", str(item.id), "--at", "01:30"]) == 0
    assert commands.main(["forget", str(item.id)]) == 0
    assert path.is_file()
    assert commands.main(["show", str(item.id)]) == 2


def test_picture_and_invalid_inputs_are_rejected(catalog: Path, tmp_path: Path) -> None:
    picture = media(tmp_path, "picture.png")
    library.add_files((str(picture),))
    item = library.get_by_path(picture)
    assert item is not None
    with pytest.raises(ValueError):
        library.bookmark_add(item.id, 3, "invalid")
    with pytest.raises(ValueError):
        library.list_items(0)
    with pytest.raises(ValueError):
        library.search("")
    with pytest.raises(ValueError):
        commands._seconds("01:99")
    with pytest.raises(ValueError):
        library.tag_add(item.id, "\x1b[31m")
    assert library.add_files((str(tmp_path / "absent.mp4"),)) == (0, 1)


def test_download_indexes_even_without_history_and_failure_is_nonfatal(
    catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pinak.downloader as downloader
    from pinak.config import config

    path = media(tmp_path, "new track.mp3")
    monkeypatch.setitem(config, "output_dir", str(tmp_path))
    monkeypatch.setitem(config, "record_history", False)
    monkeypatch.setattr(downloader, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(downloader, "get_platform", lambda _url: "YouTube")
    monkeypatch.setattr(downloader, "handle_duplicate", lambda *_a, **_kw: "download")
    monkeypatch.setattr(downloader, "record_download", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        downloader,
        "download_media_content",
        lambda url, *_a, **_kw: {
            "success": True,
            "url": url,
            "files": [str(path)],
            "info": {},
        },
    )
    url = "https://www.youtube.com/watch?v=library-test"
    assert downloader.handle_download(url, interactive=False)["success"]
    assert library.get_by_path(path) is not None
    monkeypatch.setattr(
        library, "add_files", lambda _paths: (_ for _ in ()).throw(OSError("locked"))
    )
    assert downloader.handle_download(url, interactive=False)["success"]


def test_rescan_new_path_reports_relink_collision_without_losing_data(
    catalog: Path, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    old_path = media(root, "old.mp3")
    library.scan(root)
    old = library.get_by_path(old_path)
    assert old is not None
    library.tag_add(old.id, "Keep")
    new_path = root / "new.mp3"
    old_path.rename(new_path)
    library.scan(root)
    new = library.get_by_path(new_path)
    assert new is not None and new.id != old.id
    with pytest.raises(ValueError, match="already belongs"):
        library.relink(old.id, new_path)
    assert library.tags(old.id) == ["Keep"]
    assert library.get(new.id).available


def test_player_resume_bookmark_override_and_storage_fallback(
    catalog: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from pinak.media.player.coordinator import MediaSession

    path = media(tmp_path, "lecture.mp4")
    library.add_files((str(path),))
    library.save_position(path, 42, 200)
    session = MediaSession([path], enable_consent_prompt=False)
    session._current_meta = SimpleNamespace(media_type="video")  # type: ignore[assignment]
    seeked: list[float] = []
    monkeypatch.setattr(session, "seek_to", lambda seconds: seeked.append(seconds) or seconds)
    session._restore_library_position(path)
    assert seeked == [42]
    session.transport.current_pts = 60
    session.transport.duration_sec = 200
    session._save_library_position()
    assert library.get_by_path(path).position == 60  # type: ignore[union-attr]

    bookmark = MediaSession([path], initial_start_seconds=90, enable_consent_prompt=False)
    bookmark._current_meta = SimpleNamespace(media_type="video")  # type: ignore[assignment]
    monkeypatch.setattr(bookmark, "seek_to", lambda seconds: seeked.append(seconds) or seconds)
    monkeypatch.setattr(
        library, "get_by_path", lambda _path: (_ for _ in ()).throw(OSError("db unavailable"))
    )
    bookmark._restore_library_position(path)
    assert seeked[-1] == 90

    ordinary = MediaSession([path], enable_consent_prompt=False)
    ordinary._current_meta = SimpleNamespace(media_type="video")  # type: ignore[assignment]
    monkeypatch.setattr(ordinary, "seek_to", lambda seconds: seeked.append(seconds) or seconds)
    ordinary._restore_library_position(path)
    assert seeked[-1] == 0
