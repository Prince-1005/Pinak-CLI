---
title: Pinak Library
description: Find, organize, and resume media stored on your device.
---

Pinak Library is a local catalog. It stores paths, tags, collections, bookmarks, and playback position in a SQLite database. It does **not** move, copy, upload, or delete your media files. Successful new downloads are added automatically, including downloads run through the queue. Existing folders are scanned only when you choose them.

> These commands describe the current repository source. Check `pinak --version`; the published PyPI release may be older.

## Add existing media

```sh
pinak library scan "path/to/your/media"
pinak library scan --all
pinak library list
pinak library search "guitar"
pinak library search "" --tag favorites
pinak library show 12
```

The first command scans that folder and its subfolders, and remembers it for later `scan --all` runs. Pinak does not follow symbolic links. A later complete scan marks disappeared files as missing, while retaining their tags, bookmarks, and collection membership. If a scan reports errors, Pinak preserves the previous availability state for files it could not inspect.

For example, after scanning a music folder, run `pinak library list`, take an ID from its output, and replace `12` in the commands below with that ID.

## Organize and play

```sh
pinak library tag add 12 favorites
pinak library tag remove 12 favorites
pinak library collection create "Road trip"
pinak library collection list
pinak library collection add 1 12
pinak library collection show 1
pinak library collection move 1 12 --before 15
pinak library collection play 1
pinak library play 12
pinak library play 12 --from-start
```

A collection is an ordered playlist of cataloged files. Playback skips missing files. Audio and video playback saves progress periodically and when paused or closed. Near the end of a track, progress resets so the next play starts at the beginning. `--from-start` overrides saved progress for that playback.

## Check catalog storage

```sh
pinak library storage
pinak library storage --refresh
pinak library storage --root "path/to/your/media" --refresh --json
pinak library storage --collection 1
```

The default report uses file sizes recorded when items were cataloged. `--refresh` stats cataloged paths without scanning new folders or changing the catalog, and reports missing or unreadable paths separately. Collection totals can overlap, so they should not be added together. Filesystem capacity is shared space, and the report does not measure physical disk allocation. The MCP `library_storage_report` tool returns only cached totals for approved paths and omits host capacity.

## Save a moment

```sh
pinak library bookmark add 12 --at 01:30 --note "Favorite part"
pinak library bookmark list 12
pinak library bookmark open 3
pinak library bookmark remove 3
```

Times accept seconds, `MM:SS`, or `HH:MM:SS`. Bookmarks apply to audio and video, and opening one starts playback at its saved time.

## After moving a file

```sh
pinak library relink 12 "new/path/to/media.mp4"
pinak library forget 12
```

`relink` keeps item 12's tags, bookmarks, and collection membership. The replacement must be a supported file of the same media type. If the new path was already scanned into another item, forget that duplicate item first, then relink. `forget` removes only the catalog entry; the media file remains on disk.

Every command above also works in the interactive shell with `/library` in place of `pinak library`. Run `pinak library --help` or `/library help` for the complete command list.
