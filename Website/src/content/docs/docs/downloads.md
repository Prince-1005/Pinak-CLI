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

## Batch text files

Create a UTF-8 text file with one URL per line. Blank lines and lines beginning with `#` are ignored. Launch `pinak`, then:

```text
/batch links.txt
```

Batch processing is sequential. It is not a durable background queue. Keep the process running to finish the batch.

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
