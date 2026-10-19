---
title: Interactive shell
description: Navigate Pinak’s REPL commands and saved preferences.
---

Start with `pinak` and no arguments. Use `/help` for the installed version’s command list.

## Download

- `/video <URL>`: video download.
- `/audio <URL>`: audio extraction.
- `/any <URL>`: route through yt-dlp-supported sources.
- `/instagram <URL>`: Instagram extraction.
- `/queue add <URL>`, `/queue list`, `/queue run`, `/queue retry --failed`: manage the same durable jobs without leaving the shell.
- `/queue show <ID>`, `/queue cancel <ID>`, `/queue remove <ID> [ID ...]`, `/queue clean --completed`: inspect jobs and manage their records while keeping downloaded files and history. Use `/queue help` for all options.
- `/trim 00:15-01:30 <URL>`: select an audio/video range.

## Preferences

- `/setout <folder>`: save the output directory.
- `/video_quality`, `/audio_quality`: choose preferred quality.
- `/video_format`, `/audio_format`: choose formats.
- `/subs`: toggle automatic subtitle extraction/embedding for supported video downloads.
- `/sort`: toggle sorting into platform folders.
- `/config`: inspect active preferences.

## History and diagnostics

- `/history`: browse download history.
- `/history search <text>`: search URLs and recorded file paths.
- `/stats`: local download statistics.
- `/open`: open the output folder.
- `/doctor`: environment diagnostics.
- `/ffmpeg`: provision static FFmpeg.
- `/update`: update yt-dlp and Pinak.

## Media

- `/library scan <folder>`: add local files from a folder you choose; `/library scan --all` refreshes chosen folders.
- `/library list`, `/library search <text>`, `/library show <ID>`: browse the local catalog.
- `/library tag`, `/library collection`, `/library bookmark`: organize files and play saved moments. [See the Library guide](../library/).
- `/media <local-path>`: open a file or local browser.
- `/play <local-path>`: play local media.
- `/view <local-path>`: open pictures.
- `/ctl status`: ask the authenticated local player for status.
- `/ctl pause`: control the active player.

`/reset` restores terminal state if it is left in an unexpected mode. `/exit` exits the shell. Paths with spaces should be supplied as the full command argument; consult the installed command behavior for your shell.

## Clear the screen

Use `/clear` (or `clear`) to clear the terminal screen and scrollback, including the shell output from launching Pinak, and redraw the Pinak ASCII logo and control panel. Saved jobs, history, preferences, and downloaded files remain intact.
