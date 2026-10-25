"""Storage accounting uses catalog scope and labels current observations."""

from __future__ import annotations

from pathlib import Path

import pytest

from pinak import library, library_storage
from pinak.commands import library as commands
from pinak.mcp_server.models import Policy
from pinak.mcp_server.tools import Tools


def test_storage_cached_refresh_collections_and_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_history_db: str
) -> None:
    monkeypatch.setattr(library, "DB_FILE", tmp_path / "library.db")
    root = tmp_path / "approved"
    root.mkdir()
    a = root / "one.mp3"
    b = root / "two.mp3"
    a.write_bytes(b"abc")
    b.write_bytes(b"longer")
    library.scan(root)
    first = library.get_by_path(a)
    second = library.get_by_path(b)
    assert first and second
    one = library.collection_create("One")
    two = library.collection_create("Two")
    for cid in (one, two):
        library.collection_add(cid, first.id)
    library.collection_add(two, second.id)
    cached = library_storage.report(root=root)
    assert cached["catalog_logical_bytes"] == 9
    assert cached["current_available_bytes"] is None
    assert cached["by_root"] == [{"root": str(root), "items": 2, "catalog_logical_bytes": 9}]
    assert sum(group["catalog_logical_bytes"] for group in cached["collections"]) == 12
    assert cached["collections_overlap"]
    assert library_storage.report(collection_id=one)["catalog_logical_bytes"] == 3
    a.write_bytes(b"changed")
    b.unlink()
    current = library_storage.report(root=root, refresh=True, limit=1)
    assert current["catalog_logical_bytes"] == 9
    assert current["current_available_bytes"] == 7
    assert current["missing"] == 1
    assert current["next_cursor"] == 1
    assert commands.main(["storage", "--root", str(root), "--refresh", "--json"]) == 1
    with pytest.raises(ValueError, match="previously scanned"):
        library_storage.report(root=tmp_path)

    tools = Tools(Policy(default_output_dir=root))
    try:
        result = tools.call("library_storage_report", {})
        assert result["ok"] and result["data"]["catalog_logical_bytes"] == 9
        assert result["data"]["capacity"] == []
        private = tmp_path / "private.mp3"
        private.write_bytes(b"private media")
        library.add_files((str(private),))
        scoped = tools.call("library_storage_report", {})["data"]
        assert scoped["items"] == 2 and scoped["catalog_logical_bytes"] == 9
        assert tools.call("library_storage_report", {"root": str(tmp_path)})["ok"] is False
    finally:
        tools.close()


def test_storage_refresh_does_not_follow_symlink_or_count_hardlink_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(library, "DB_FILE", tmp_path / "library.db")
    root = tmp_path / "root"
    root.mkdir()
    first = root / "first.mp3"
    second = root / "second.mp3"
    first.write_bytes(b"same")
    try:
        second.hardlink_to(first)
    except OSError:
        pytest.skip("Hard links are unavailable")
    library.scan(root)
    report = library_storage.report(refresh=True)
    assert report["catalog_logical_bytes"] == 8
    assert report["current_available_bytes"] == 4


def test_mcp_collection_list_hides_private_catalog_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "DB_FILE", tmp_path / "library.db")
    approved = tmp_path / "approved"
    private = tmp_path / "private"
    approved.mkdir()
    private.mkdir()
    public_file = approved / "public.mp3"
    secret_file = private / "secret.mp3"
    public_file.write_bytes(b"public")
    secret_file.write_bytes(b"secret")
    library.add_files((str(public_file), str(secret_file)))
    public_item = library.get_by_path(public_file)
    secret_item = library.get_by_path(secret_file)
    assert public_item and secret_item
    secret_only = library.collection_create("Secret only")
    mixed = library.collection_create("Mixed")
    library.collection_add(secret_only, secret_item.id)
    library.collection_add(mixed, public_item.id)
    library.collection_add(mixed, secret_item.id)
    tools = Tools(Policy(default_output_dir=approved))
    try:
        result = tools.call("library_collection_list", {})
        assert result["ok"]
        assert result["data"]["items"] == [
            {"id": mixed, "name": "Mixed", "item_count": 1}
        ]
    finally:
        tools.close()


def test_storage_scopes_parent_root_and_pages_collections(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "DB_FILE", tmp_path / "library.db")
    parent = tmp_path / "catalog"
    approved = parent / "approved"
    approved.mkdir(parents=True)
    media = approved / "song.mp3"
    media.write_bytes(b"music")
    library.scan(parent)
    item = library.get_by_path(media)
    assert item is not None
    for number in range(7):
        group = library.collection_create(f"Group {number}")
        library.collection_add(group, item.id)

    first = library_storage.report(allowed_roots=[approved], include_capacity=False, limit=3)
    assert first["by_root"] == [
        {"root": str(approved), "items": 1, "catalog_logical_bytes": 5}
    ]
    assert len(first["collections"]) == 3
    assert first["collection_next_cursor"] == 3
    second = library_storage.report(
        allowed_roots=[approved],
        include_capacity=False,
        limit=3,
        collection_cursor=first["collection_next_cursor"],
    )
    assert len(second["collections"]) == 3
    assert second["collection_next_cursor"] == 6
