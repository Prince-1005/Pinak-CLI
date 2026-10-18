---
title: Commands & options
description: Direct CLI usage and the current public command surface.
---

## Download a URL

```sh
pinak "<your-media-url>"
pinak "<your-media-url>" --quality 720p -o downloads
pinak "<your-media-url>" --audio
```

URLs must start with `http://` or `https://`. Supported sources depend on yt-dlp and source accessibility. Quality presets include `best`, `worst`, and heights such as `720p` and `1080p`.

## Useful switches

- `--output`, `-o`: output directory for this invocation.
- `--audio`: audio extraction, using the configured audio format.
- `--quality`: preferred quality for this invocation.
- `--force`: bypass duplicate policy.
- `--dry-run`: show a locally resolved plan without downloading media.
- `--json`: reserve stdout for one JSON result; progress goes to stderr.
- `--verbose`, `-v`: debug output.
- `--log-file`: explicit detailed log path.
- `--doctor`: check dependencies, storage, and connectivity.
- `--install-ffmpeg`: provision static FFmpeg.
- `--config-path`: print the active configuration path.
- `--version`, `-V`: show the installed version.
- `--help`: show current CLI help.

## Inspect a plan

```sh
pinak "<your-media-url>" --dry-run --json
```

Dry-run describes local options and platform inference. It is not a guarantee of live source availability, resolved formats, or final file size.

## Scripting

```sh
pinak "<your-media-url>" --json
```

Inspect the process exit status as well as the result. A nonzero status means failure. Media source errors and postprocessing requirements still apply in JSON mode.

## Local files

```sh
pinak media "<local-path>"
```

Local playback and remote downloading are separate routes. Download remote media first. See [playback](../playback/).
