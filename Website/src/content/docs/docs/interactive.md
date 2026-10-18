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
- `/batch links.txt`: save and immediately run entries from a text file; unfinished jobs remain in the local queue.
- `/queue add <URL>`, `/queue list`, `/queue run`, `/queue retry --failed`: manage the same durable jobs without leaving the shell. Use `/queue help` for all options.
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

- `/media <local-path>`: open a file or local browser.
- `/play <local-path>`: play local media.
- `/view <local-path>`: open pictures.
- `/ctl status`: ask the authenticated local player for status.
- `/ctl pause`: control the active player.

`/reset` restores terminal state if it is left in an unexpected mode. `/exit` exits the shell. Paths with spaces should be supplied as the full command argument; consult the installed command behavior for your shell.
