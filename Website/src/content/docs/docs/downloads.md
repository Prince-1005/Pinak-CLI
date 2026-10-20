---
title: Audio, quality & batches
description: Audio extraction, quality preferences, partial downloads, and batch workflows.
---

## Extract audio

```sh
pinak "<your-media-url>" --audio
```

FFmpeg is needed for extraction/conversion. The default audio format is MP3, with a 192 kbps preference. Inside the interactive shell, `/audio_format` and `/audio_quality` let you save preferences. Conversion does not restore information missing from a source.

## Choose quality and output

```sh
pinak "<your-media-url>" --quality 1080p -o "<output-folder>"
```

Available source formats determine what can be downloaded. One-shot options are temporary; use shell preferences to save defaults. `/sort` toggles sorting into platform folders.

## Import text files

Create a UTF-8 text file with one URL per line. Blank lines and lines beginning with `#` are ignored. Launch `pinak`, then:

```text
/queue import links.txt
/queue run
```

Import saves the entries as local jobs; run starts the queue. Jobs run sequentially while Pinak is open. If you close Pinak, unfinished jobs remain in the queue for a later `/queue run`.

You can also save jobs without starting them:

```sh
pinak queue add "<your-media-url>" --quality 720p -o downloads
pinak queue import links.txt
pinak queue list
pinak queue run
pinak queue retry --failed
```

The live display shows overall job counts, the active file, transfer size, speed, ETA, and processing status. Finished jobs show their result and any failure reason.

Each job keeps the options and preferences captured when it was added. Ctrl+C stops the current run and leaves the active job queued with partial files retained. Failed jobs need an explicit retry. The queue is local and foreground only; it does not keep downloading after the terminal closes.

Inside the interactive shell, the same actions are available as `/queue add <URL>`, `/queue import <file>`, `/queue list`, `/queue run`, and `/queue retry --failed`. Enter `/queue help` for options.

For example, add two links while Pinak is open, then process them later:

```text
/queue add <first-media-url>
/queue add <second-media-url>
/queue list
/queue run
```

## Manage saved jobs

```text
/queue show 12
/queue cancel 12
/queue list --status cancelled
/queue remove 12
/queue clean --completed
```

Use an ID from `/queue list`. `show` displays the saved options, files, attempts, and full last error. `cancel` marks a queued job as cancelled and keeps its record; cancelled jobs do not run or retry automatically. Add the URL again to download it later. `remove` deletes one inactive record. Stop a running job with Ctrl+C in its runner before cancelling or removing it.

`clean --completed` removes only succeeded/skipped records. Failed, cancelled, queued, and running jobs remain available. Cancellation, removal, and cleanup preserve media files, partial downloads, and the separate download history. Outside the interactive shell, replace `/queue` with `pinak queue`.

## Interrupted downloads

Partial files are retained for continuation where supported. Re-run the same command to attempt resume. This does not guarantee that every source or stream can resume indefinitely.

## Duplicates

Pinak consults successful local history and checks the recorded files. Missing outputs do not prevent a new attempt. Use `--force` to bypass duplicate policy. History-based URL checks are not content-hash deduplication.

## Trimming

In the interactive shell:

```text
/trim 01:15-02:30 <your-media-url>
```

Trimming uses the generic yt-dlp engine. Image posts are not audio/video ranges and cannot be trimmed this way.

## Instagram

Use `/instagram <URL>` or pass a URL directly. Extraction depends on what the source makes accessible. Carousels can have partial failures; review the result instead of assuming every slide succeeded. The tool does not bypass private access or platform restrictions.
