---
title: Configuration & storage
description: Understand local preferences, invocation overrides, and file locations.
---

## Inspect preferences

```sh
pinak --config-path
```

Use `/config` inside the interactive shell. Save preferences with commands such as `/setout`, `/video_quality`, and `/audio_format`.

## Defaults

- Output: `downloads`, relative to your current directory.
- Video: MP4, best available quality preference.
- Audio: MP3, 192 kbps preference.
- Retry count: 3.
- Connect timeout: 10 seconds.
- Read timeout: 30 seconds.

Other settings include `ffmpeg_path`, `ffprobe_path`, `history_enabled`, `log_file`, `embed_subs`, `auto_sort`, and `duplicate_action`.

## Override order

Explicit invocation options take precedence over process environment overrides and saved preferences. Environment overrides use the `PINAK_` prefix, for example `PINAK_OUTPUT_DIR` or `PINAK_QUALITY`.

One-shot output/quality settings remain temporary. Saving an unrelated preference does not persist process environment overrides. A `.env` file is also read; process environment values take precedence over it.

## Local storage

Platform-specific directories are resolved with platformdirs:

- Configuration: user config directory for `pinak-cli`, then `config.json`.
- History: user data directory for `pinak-cli`, then `history.db`.
- REPL command history: `~/.pinak_cli_history`.
- IPC descriptor: user cache directory for `pinak-cli`, inside `ipc`.
- Downloads: your chosen output directory, separately from application settings.
- Logs: the explicit path you select.

Use `pinak --config-path` instead of assuming a fixed Windows/macOS/Linux path. Back up media and application data separately. History records are not backups of downloaded files.

The history database is SQLite. Confirmed corruption is preserved before recovery; normal lock/permission failures are reported rather than treated as corruption.
