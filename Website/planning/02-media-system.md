# Phase 2 — Media system

## Inputs and dependencies

Phase 1; Sharp, FFmpeg/FFprobe; source Media files and optional `media.json`.

## Tasks and outputs

- Walk nested directories deterministically, ignore symlinks, and classify supported file extensions.
- Validate metadata, optional local cover/caption/transcript references, source size, and decode/probe success.
- Create responsive image renditions, H.264/AAC video, audio playback files, covers, and selected muted previews.
- Cache by source bytes, processing version, metadata, and referenced attachment contents.
- Generate a typed gallery manifest; remove stale published media directories.
- Implement 24-item pagination, type/title/tag filters, image zoom, native playback, focus-restoring dialogs, and no-JavaScript media links.
- Preserve aspect ratios with contain rendering; offer readable full-size screenshots.

## Commands

`npm run media:prepare -- --from "<external-folder>"`, `npm run media:build`, `npm test`.

## Acceptance

All five initial supported assets appear. New supported files appear after rebuild without page edits. Removed files disappear. Unicode/nested names work; corrupt inputs fail with the filename. Videos remain full length and prepared files fit the budget. Full media is not downloaded on homepage load.

## Completion notes

The supplied screenshots and inspected video frames show real product captures and playback demonstrations. Optional metadata improves presentation but is not required for discovery. Caption text is supplied by editors, never fabricated.
