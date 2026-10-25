"""MCP Library and detailed history contracts over isolated local storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pinak import history, library
from pinak.mcp_server.models import Policy
from pinak.mcp_server.tools import Tools


@pytest.fixture
def service(isolated_history_db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(library, "DB_FILE", tmp_path / "state" / "library.db")
    approved = tmp_path / "approved"
    approved.mkdir()
    tools = Tools(Policy(default_output_dir=approved))
    yield tools, approved
    tools.close()


def test_library_scan_organize_replay_and_keep_files(service, tmp_path: Path) -> None:
    tools, approved = service
    first = approved / "one.mp3"
    second = approved / "two.mp3"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"private")
    assert tools.call("library_scan", {"folder": str(tmp_path)})["error"]["code"] == "PATH_DENIED"
    assert tools.call("library_scan", {"folder": str(approved)})["data"]["indexed"] == 2
    page = tools.call("library_list", {"limit": 1})["data"]
    assert page["has_more"] and page["next_cursor"] is not None
    next_page = tools.call("library_list", {"limit": 1, "cursor": page["next_cursor"]})["data"]
    ids = [page["items"][0]["id"], next_page["items"][0]["id"]]
    assert len(set(ids)) == 2
    first_id = next(item.id for item in library.list_items() if item.title == "one")
    second_id = next(item.id for item in library.list_items() if item.title == "two")
    assert tools.call("library_search", {"query": "one"})["data"]["items"][0]["id"] == first_id
    assert tools.call("library_show", {"media_id": first_id})["data"]["position_seconds"] == 0

    tag_args = {"media_id": first_id, "name": "Favorite", "request_key": "tag-1"}
    tagged = tools.call("library_tag_add", tag_args)
    assert tagged["ok"] and tools.call("library_tag_add", tag_args) == tagged
    assert tools.call("library_search", {"tag": "favorite"})["data"]["items"][0]["id"] == first_id
    untagged = tools.call(
        "library_tag_remove",
        {
            "media_id": first_id,
            "name": "Favorite",
            "request_key": "untag",
        },
    )
    assert untagged["data"]["removed"]
    assert tools.call("library_search", {"tag": "favorite"})["data"]["items"] == []
    assert tools.call(
        "library_tag_add",
        {
            "media_id": first_id,
            "name": "Favorite",
            "request_key": "tag-again",
        },
    )["ok"]
    assert (
        tools.call("library_tag_add", {**tag_args, "name": "Different"})["error"]["code"]
        == "IDEMPOTENCY_CONFLICT"
    )

    created = tools.call("library_collection_create", {"name": "Mix", "request_key": "make"})
    assert (
        created["ok"]
        and tools.call("library_collection_create", {"name": "Mix", "request_key": "make"})
        == created
    )
    cid = created["data"]["collection_id"]
    assert tools.call("library_collection_list", {})["data"]["items"][0]["id"] == cid
    for media_id in (first_id, second_id):
        assert tools.call(
            "library_collection_add",
            {
                "collection_id": cid,
                "media_id": media_id,
                "request_key": f"add-{media_id}",
            },
        )["ok"]
    moved = tools.call(
        "library_collection_move",
        {
            "collection_id": cid,
            "media_id": second_id,
            "before_id": first_id,
            "request_key": "move",
        },
    )
    assert moved["ok"]
    shown_collection = tools.call("library_collection_show", {"collection_id": cid})
    assert [item["id"] for item in shown_collection["data"]["items"]] == [second_id, first_id]
    removed_from_mix = tools.call(
        "library_collection_remove",
        {
            "collection_id": cid,
            "media_id": second_id,
            "request_key": "remove-from-mix",
        },
    )
    assert removed_from_mix["data"]["removed"] and second.exists()

    bookmark_args = {"media_id": first_id, "seconds": 34.0, "note": "Start", "request_key": "mark"}
    bookmark = tools.call("library_bookmark_add", bookmark_args)
    assert bookmark["ok"] and tools.call("library_bookmark_add", bookmark_args) == bookmark
    bid = bookmark["data"]["bookmark_id"]
    assert (
        tools.call("library_bookmark_list", {"media_id": first_id})["data"]["items"][0]["id"] == bid
    )
    shown = tools.call("library_bookmark_show", {"bookmark_id": bid})
    assert shown["data"]["seconds"] == 34 and not shown["data"]["playback_started"]

    first.unlink()
    replacement = approved / "moved.mp3"
    replacement.write_bytes(b"moved")
    relink_args = {"media_id": first_id, "path": str(replacement), "request_key": "relink"}
    relinked = tools.call("library_relink", relink_args)
    assert relinked["ok"] and tools.call("library_relink", relink_args) == relinked
    assert tools.call("library_show", {"media_id": first_id})["data"]["tags"] == ["Favorite"]
    remove_args = {"bookmark_id": bid, "request_key": "unmark"}
    removed = tools.call("library_bookmark_remove", remove_args)
    assert removed["ok"] and tools.call("library_bookmark_remove", remove_args) == removed
    forget_args = {"media_id": first_id, "request_key": "forget"}
    forgotten = tools.call("library_forget", forget_args)
    assert forgotten["ok"] and tools.call("library_forget", forget_args) == forgotten
    assert replacement.exists() and not tools.call("library_show", {"media_id": first_id})["ok"]


def test_history_detail_redaction_and_root_scope(service, tmp_path: Path) -> None:
    tools, approved = service
    allowed = approved / "saved.mp4"
    allowed.write_bytes(b"file")
    allowed_second = approved / "saved-audio.mp3"
    allowed_second.write_bytes(b"audio")
    history.record_download(
        "https://example.com/watch?token=private",
        files=[str(allowed), str(allowed_second)],
    )
    listed = tools.call("history_list", {})
    assert listed["ok"] and listed["data"]["items"]
    record_id = listed["data"]["items"][0]["id"]
    detail = tools.call("history_show", {"history_id": record_id})
    assert detail["ok"] and detail["data"]["files"] == [str(allowed), str(allowed_second)]
    first_page = tools.call("history_show", {"history_id": record_id, "limit": 1})
    assert first_page["data"]["files"] == [str(allowed)]
    assert first_page["data"]["next_cursor"] == 2
    second_page = tools.call("history_show", {"history_id": record_id, "limit": 1, "cursor": 2})
    assert second_page["data"]["files"] == [str(allowed_second)]
    assert second_page["data"]["next_cursor"] is None
    assert "token=private" not in detail["data"]["url"]
    assert "[redacted]" in detail["data"]["url"]
    assert (
        tools.call("history_show", {"history_id": record_id + 100})["error"]["code"]
        == "HISTORY_NOT_FOUND"
    )
    outside = tmp_path / "private.mp4"
    outside.write_bytes(b"private")
    history.record_download("https://example.com/private", files=[str(outside)])
    new_id = tools.call("history_list", {})["data"]["items"][0]["id"]
    assert new_id == record_id
    assert (
        tools.call("history_show", {"history_id": record_id + 1})["error"]["code"] == "PATH_DENIED"
    )


def test_library_paths_are_scoped_and_missing_files_are_retained(service, tmp_path: Path) -> None:
    tools, approved = service
    path = approved / "song.mp3"
    path.write_bytes(b"song")
    tools.call("library_scan", {"folder": str(approved)})
    media_id = tools.call("library_list", {})["data"]["items"][0]["id"]
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"outside")
    assert (
        tools.call(
            "library_relink",
            {
                "media_id": media_id,
                "path": str(outside),
                "request_key": "deny",
            },
        )["error"]["code"]
        == "PATH_DENIED"
    )
    path.unlink()
    assert tools.call("library_scan", {"folder": str(approved)})["ok"]
    assert not tools.call("library_show", {"media_id": media_id})["data"]["available"]
    assert library.get(media_id).path == str(path)


def test_library_receipt_migration_preserves_existing_media(service) -> None:
    tools, approved = service
    path = approved / "prior.mp3"
    path.write_bytes(b"prior")
    library.add_files((str(path),))
    before = library.get_by_path(path)
    assert before is not None
    with sqlite3.connect(library.DB_FILE) as conn:
        conn.execute("DROP TABLE mcp_receipts")
        conn.execute("PRAGMA user_version=1")
    shown = tools.call("library_show", {"media_id": before.id})
    assert shown["ok"] and shown["data"]["path"] == str(path)
    with sqlite3.connect(library.DB_FILE) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='mcp_receipts'").fetchone()


def test_library_collection_list_filters_private_roots_and_preserves_empty(service, tmp_path: Path):
    tools, approved = service
    private_dir = tmp_path / "private"
    private_dir.mkdir()

    app_file = approved / "public.mp3"
    app_file.write_bytes(b"public")
    library.add_files((str(app_file),))
    app_id = library.get_by_path(app_file).id

    priv_file = private_dir / "secret.mp3"
    priv_file.write_bytes(b"secret")
    library.add_files((str(priv_file),))
    priv_id = library.get_by_path(priv_file).id

    with library._connect() as conn:
        cursor = conn.execute("INSERT INTO collections(name, name_key) VALUES ('Secret', 'secret')")
        priv_coll_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO collection_items(collection_id, media_id, position) VALUES (?, ?, 0)",
            (priv_coll_id, priv_id),
        )

        cursor = conn.execute("INSERT INTO collections(name, name_key) VALUES ('Mixed', 'mixed')")
        mixed_coll_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO collection_items(collection_id, media_id, position) VALUES (?, ?, 0)",
            (mixed_coll_id, app_id),
        )
        conn.execute(
            "INSERT INTO collection_items(collection_id, media_id, position) VALUES (?, ?, 1)",
            (mixed_coll_id, priv_id),
        )

        cursor = conn.execute("INSERT INTO collections(name, name_key) VALUES ('Empty', 'empty')")
        empty_coll_id = cursor.lastrowid

    res = tools.call("library_collection_list", {})["data"]["items"]
    res_by_id = {c["id"]: c for c in res}

    assert priv_coll_id not in res_by_id
    assert mixed_coll_id in res_by_id
    assert res_by_id[mixed_coll_id]["item_count"] == 1
    assert empty_coll_id in res_by_id
    assert res_by_id[empty_coll_id]["item_count"] == 0
