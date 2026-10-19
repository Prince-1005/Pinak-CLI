"""Shared parser for direct and interactive Pinak Library commands."""

from __future__ import annotations

import argparse
import os
import shlex
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .. import library
from ..text_safety import safe_rich, safe_text

console = Console()


def _parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description="Find and organize local media")
    actions = parser.add_subparsers(dest="action", required=True)
    scan = actions.add_parser("scan", help="Index a folder, or refresh chosen folders")
    scan.add_argument("folder", nargs="?")
    scan.add_argument("--all", action="store_true", help="Refresh previously chosen folders")
    listing = actions.add_parser("list", help="List catalog items")
    listing.add_argument("--type", choices=["audio", "video", "picture"])
    listing.add_argument("--limit", type=int, default=100)
    show = actions.add_parser("show", help="Show an item and its tags")
    show.add_argument("id", type=int)
    search = actions.add_parser("search", help="Search titles, paths and tags")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--tag")
    search.add_argument("--limit", type=int, default=100)
    play = actions.add_parser("play", help="Play an item, resuming where it stopped")
    play.add_argument("id", type=int)
    play.add_argument("--from-start", action="store_true")
    relink = actions.add_parser("relink", help="Update an item's path after a move")
    relink.add_argument("id", type=int)
    relink.add_argument("path")
    forget = actions.add_parser("forget", help="Remove an item from the catalog, keeping its file")
    forget.add_argument("id", type=int)

    tag = actions.add_parser("tag", help="Add or remove an item tag").add_subparsers(
        dest="operation", required=True
    )
    for name in ("add", "remove"):
        action = tag.add_parser(name)
        action.add_argument("id", type=int)
        action.add_argument("name")

    collection = actions.add_parser("collection", help="Manage ordered collections").add_subparsers(
        dest="operation", required=True
    )
    collection.add_parser("list")
    created = collection.add_parser("create")
    created.add_argument("name")
    for name in ("show", "play"):
        action = collection.add_parser(name)
        action.add_argument("collection_id", type=int)
    for name in ("add", "remove"):
        action = collection.add_parser(name)
        action.add_argument("collection_id", type=int)
        action.add_argument("id", type=int)
    move = collection.add_parser("move")
    move.add_argument("collection_id", type=int)
    move.add_argument("id", type=int)
    move.add_argument("--before", type=int, required=True)

    bookmark = actions.add_parser("bookmark", help="Manage timestamped bookmarks").add_subparsers(
        dest="operation", required=True
    )
    add = bookmark.add_parser("add")
    add.add_argument("id", type=int)
    add.add_argument("--at", required=True)
    add.add_argument("--note", default="")
    listing = bookmark.add_parser("list")
    listing.add_argument("id", type=int)
    for name in ("open", "remove"):
        action = bookmark.add_parser(name)
        action.add_argument("bookmark_id", type=int)
    return parser


def _seconds(value: str) -> float:
    parts = value.split(":")
    if not 1 <= len(parts) <= 3 or any(not p.isdigit() for p in parts):
        raise ValueError("Time must be seconds, MM:SS or HH:MM:SS")
    numbers = [int(part) for part in parts]
    if len(numbers) > 1 and any(n >= 60 for n in numbers[1:]):
        raise ValueError("Minutes and seconds must be below 60")
    seconds = 0
    for number in numbers:
        seconds = 60 * seconds + number
    return float(seconds)


def _items(items: list[library.LibraryItem]) -> None:
    table = Table(title="Pinak Library")
    for title in ("ID", "Type", "Title", "Status", "Path"):
        table.add_column(title)
    for item in items:
        table.add_row(
            str(item.id),
            item.media_type,
            Text(safe_text(item.title)),
            "ready" if item.available and Path(item.path).is_file() else "missing",
            Text(safe_text(item.path)),
        )
    console.print(table)


def _play(
    items: list[library.LibraryItem], *, start: float | None = None, from_start: bool = False
) -> int:
    from ..media.player.coordinator import MediaSession

    available = [item for item in items if item.available and Path(item.path).is_file()]
    missing = len(items) - len(available)
    if missing:
        console.print(
            f"[yellow]Skipping {missing} unavailable item(s). Use library relink.[/yellow]"
        )
    if not available:
        raise ValueError("No playable files are available")
    session = MediaSession(
        playlist=[item.path for item in available],
        enable_consent_prompt=True,
        initial_start_seconds=0.0 if from_start else start,
    )
    session.start()
    return 0


def main(argv: Sequence[str], *, prog: str = "pinak library") -> int:
    args = _parser(prog).parse_args(list(argv))
    try:
        if args.action == "scan":
            if args.all == bool(args.folder):
                raise ValueError("Give a folder or --all")
            found, failed, errors = library.scan_all() if args.all else library.scan(args.folder)
            console.print(f"Indexed {found} file(s); {failed} scan error(s).")
            for error in errors:
                console.print(f"[yellow]{safe_rich(error)}[/yellow]")
            return 1 if failed else 0
        if args.action == "list":
            _items(library.list_items(args.limit, media_type=args.type))
        elif args.action == "show":
            item = library.get(args.id)
            _items([item])
            console.print("Tags: " + (", ".join(map(safe_rich, library.tags(item.id))) or "none"))
            if item.media_type != "picture":
                console.print(f"Resume at: {item.position:.0f}s")
        elif args.action == "search":
            _items(library.search(args.query, tag=args.tag, limit=args.limit))
        elif args.action == "play":
            return _play([library.get(args.id)], from_start=args.from_start)
        elif args.action == "relink":
            library.relink(args.id, args.path)
            console.print(f"Item #{args.id} now points to {safe_rich(args.path)}")
        elif args.action == "forget":
            library.forget(args.id)
            console.print(f"Forgot item #{args.id}. Its media file was kept.")
        elif args.action == "tag":
            if args.operation == "add":
                library.tag_add(args.id, args.name)
            else:
                library.tag_remove(args.id, args.name)
            console.print("Tags: " + (", ".join(map(safe_rich, library.tags(args.id))) or "none"))
        elif args.action == "collection":
            if args.operation == "create":
                cid = library.collection_create(args.name)
                console.print(f"Created collection #{cid}: {safe_rich(args.name)}")
            elif args.operation == "list":
                for cid, name, count in library.collection_list():
                    console.print(f"#{cid} {safe_rich(name)} ({count} items)")
            elif args.operation == "show":
                _items(library.collection_items(args.collection_id))
            elif args.operation == "play":
                return _play(library.collection_items(args.collection_id))
            else:
                if args.operation == "move":
                    library.collection_move(args.collection_id, args.id, args.before)
                elif args.operation == "add":
                    library.collection_add(args.collection_id, args.id)
                else:
                    library.collection_remove(args.collection_id, args.id)
                console.print("Collection updated.")
        elif args.action == "bookmark":
            if args.operation == "add":
                bid = library.bookmark_add(args.id, _seconds(args.at), args.note)
                console.print(f"Created bookmark #{bid}.")
            elif args.operation == "list":
                for bid, seconds, note in library.bookmark_list(args.id):
                    console.print(f"#{bid} {seconds:.0f}s  {safe_rich(note)}")
            elif args.operation == "open":
                item, seconds, _ = library.bookmark_get(args.bookmark_id)
                return _play([item], start=seconds)
            else:
                library.bookmark_remove(args.bookmark_id)
                console.print("Bookmark removed.")
        return 0
    except (ValueError, OSError, sqlite3.Error, RuntimeError) as exc:
        console.print(f"[red]Library error: {safe_rich(str(exc))}[/red]")
        return 2


def run_repl(raw: str) -> int:
    try:
        args = shlex.split(raw, posix=os.name != "nt")
        if os.name == "nt":
            args = [
                arg[1:-1] if len(arg) > 1 and arg[0] == arg[-1] and arg[0] in "\"'" else arg
                for arg in args
            ]
    except ValueError as exc:
        console.print(f"Library error: {safe_rich(str(exc))}")
        return 2
    if not args or args[0].lower() == "help":
        args = ["--help"]
    try:
        return main(args, prog="/library")
    except SystemExit as exc:
        return int(exc.code or 0)
