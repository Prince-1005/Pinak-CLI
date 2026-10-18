# Maintaining the showcase

## Normal workflow

1. Add supported media inside `Website/Media`, including optional subfolders. Keep path capitalization consistent: production Linux paths are case sensitive.
2. Optionally add a filename-keyed entry to `Website/media.json`.
3. Run `npm run build` from `Website` and inspect `.cache/media-report.json`.
4. Preview using `npm run preview`, inspect the full-size gallery item, then commit and push source changes.
5. The website workflow discovers the new file and deploys after checks pass.

Supported images: PNG/JPEG/WebP/AVIF/GIF. Videos: MP4/WebM/MOV/MKV/AVI. Audio: MP3/WAV/FLAC/OGG/M4A/AAC/Opus. Conversion depends on FFmpeg’s installed decoder support. Unsupported files are reported. Corrupt supported inputs fail the build with their filename.

## Optional metadata example

```json
{
  "demos/My demo.mp4": {
    "title": "Local playback walkthrough",
    "description": "A real recording showing the terminal controls.",
    "tags": ["Playback", "Demo"],
    "featured": true,
    "order": 10,
    "poster": "covers/playback.png",
    "captions": "captions/playback.vtt",
    "transcript": "captions/playback.txt",
    "previewRange": [2, 8]
  }
}
```

Paths are relative to Media. Captions must be WebVTT and begin `WEBVTT`. `previewRange` is seconds, at most 12 seconds, only generated for featured videos. `cover` is an alternative to `poster`. Image metadata can include `alt` and `focalPoint` (CSS object-position). Cover images are also automatically discovered as gallery items, as promised by the all-media contract.

## Large files

GitHub rejects individual tracked files at/over the site’s conservative 100 MiB preflight. Keep large originals outside the repository; use:

```sh
npm run media:prepare -- --from "<external-folder>"
```

The command preserves the supplied originals, imports full-length video into Media as MP4, and refuses destination overwrites. It targets 40 MiB per video, verifies duration, and refuses bitrates below its technical threshold. Watch the result to assess quality. Long or complex clips may require an intentionally shorter editorial source. Never silently truncate or replace original recordings.

Files under the Git limit may be dropped into Media directly. The build creates optimized derivatives regardless. Do not commit generated output or caches.

## Presentation and accessibility

Give product captures meaningful alt text, and label media samples as samples. Use captions/transcripts for spoken walkthroughs. Do not invent transcription. Portrait/square/landscape media fit within frames; the enlarged viewer preserves the complete image. Audio without artwork receives a designed fallback cover.

Gallery filtering/pagination needs JavaScript. Without it, all previews and direct media links remain available. The ambient soundtrack is separate original synthesized audio and never automatically borrows uploaded music.

## Removal and replacement

Delete a source and rebuild to remove it from the gallery/output. Optional obsolete metadata produces a warning. Replacing bytes under the same path retains the media identity but changes the conversion cache key. Changing captions/covers also invalidates derivatives. Clear `.cache/media` only for troubleshooting or a deliberate pipeline reset.
