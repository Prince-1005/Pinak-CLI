# Changelog

All notable changes to `pinak-cli` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/).
Release notes are maintained manually; automatic release creation is disabled.

## [Unreleased]

### Added
- Make audio/video shuffle selectable with `s`, show its state and control in the TUI, choose from the full playlist with repeat ALL, only unplayed tracks with repeat OFF, and repeat the current track with SOLO.
- Record each queue attempt in local download history together with its saved job result, including skipped and failed attempts, when history is enabled.
- Accept multiple IDs in `queue remove` and `/queue remove`, with all-or-nothing validation.
- Render the five letters of the Pinak terminal logo in distinct colors.
- Add `queue show <id>` to inspect saved job options, files, status, attempts, and the full last error.
- Add `queue cancel <id>`, `queue remove <id>`, and `queue clean --completed` to the CLI and interactive `/queue` interface. Keep downloaded files and history; protect running jobs with transactional state checks.
- Add a persistent `cancelled` job state, supported by queue listing and excluded from worker claims and failed-job retries.

## [2.0.0] - 2026-10-19

### Added
- Add a durable local SQLite download queue with `pinak queue add`, `import`, `list`, `run`, and `retry`, plus matching `/queue` commands in the interactive shell.
- Capture each job's output folder, formats, quality, subtitle preferences, retry policy, and other download options when it is added; unfinished jobs survive process restarts even when history recording is disabled.
- Expose a reusable download engine with immutable requests, structured results, and progress events for clients that do not render terminal output.
- Show a live queue panel with overall job counts, active file, transferred size, speed, ETA, processing status, and per-job results.
- Add `/clear` and `clear` to erase the terminal screen and scrollback, then redraw the Pinak logo and control panel while preserving saved data.

### Changed
- Run queued jobs through one foreground worker with a process lock, continue after failures, and return interrupted jobs to the queue for a later run.
- Resolve the interactive `ask` duplicate preference to `skip` for saved jobs; use `--force` to explicitly repeat a download.

### Removed
- **Breaking:** remove `/batch` from the shell, completion, and help. Replace `/batch links.txt` with `/queue import links.txt` followed by `/queue run` (or the equivalent `pinak queue` commands).

### Fixed
- Treat yt-dlp runtime deprecation notices as warnings so successful downloads remain successful on Python 3.10.
- Validate an entire imported link file before saving jobs and report invalid line numbers without leaving a partially imported queue.
- Recover interrupted retries without mistaking files from a previous failed attempt for a completed job, and support large imported job selections without SQLite parameter-limit failures.
- Keep worker errors and interruptions visible in queue results, and prevent display-listener failures from changing saved job outcomes.

## [1.4.4] - 2026-10-19

### Added
- Add `/subs_lang` with a language picker and explicit language codes; save one to three preferred subtitle languages alongside the local system configuration.
- Add `/subs on` and `/subs off` while retaining the existing toggle command.

### Fixed
- Download only selected subtitle languages that a video provides, preferring creator-provided captions over automatic captions for the same language instead of requesting every translation.
- Stop rapid download retries after HTTP 429 and explain the platform's rate limit without misleading connection advice or visible ANSI escape fragments.
- Keep TUI subtitles off until requested; cycle `c` through available tracks, then Off, and preserve subtitle requests made during background loading.
- Show embedded subtitle language labels when metadata is available and recognize language codes in external subtitle filenames.

## [1.4.3] - 2026-10-18

### Changed
- Simplify picture viewing to zoom and arrow-key panning, with no Fit/1:1 toggle or letter-key panning.
- Open music artwork and picture GPU windows at the same compact scale as video windows.
- Wrap music playback and manual next/previous navigation across playlist ends.
- Show all files, including unsupported and hidden files, in the media picker; label unsupported types without opening them.
- Restore the selected folder or file when navigating back or returning from playback, clearing a search filter when it hides a file opened by path input.

## [1.4.2] - 2026-10-17

### Packaging
- Correct package links to Prince-1005/Pinak-CLI and include this changelog in source distributions.
- Disable automatic release creation; retain manually initiated GitHub releases and verified PyPI publishing.
- Use an event-independent, checksum-verified secret scanner with enabled default rules and a required detector canary.
- Validate release tags/manual version inputs and all version files before building or uploading.
- Verify Linux playback imports and clean wheel/container installations in CI; exclude local audit outputs from Docker contexts.
- Align contributor hooks with repository paths and locked tools, and refresh portable installation/media documentation links.
- Require patched setuptools for builds/development and upgrade clean-install bootstrap tools before dependency auditing.

### Fixed
- Ask for playback consent only when measured battery is at or below 15%, available RAM falls below the media's working budget, or a temperature sensor reports at least 85°C. List every critical reason in the prompt; stop unattended playback when confirmation is required.
- Read device health through the declared `psutil` dependency. Missing temperature sensors no longer trigger repeated warnings, and a momentary CPU load does not block playback.
- Open the `w` native video window at an aspect-correct size based on the usable display, preserve the chosen window size when the decoder changes resolution, and scale frames to fill the window without distortion.
- Start video GPU windows at half the fitted dimensions while preserving the video ratio and existing picture/audio window sizes.
- Use statically recognized Windows guards for platform APIs and isolate background update workers in configuration tests across CI platforms.
- Keep POSIX media input polling usable with redirected/closed stdin and make executable, terminal-launch and playlist fixtures portable.
- Stop critical-device playback if the warning cannot be displayed, so terminal output failure cannot bypass consent.

## [1.4.1] - 2026-10-17

### Fixed
- Restore continuous low-latency audio: prefer SoundDevice, select the matching shared WASAPI endpoint on Windows, use 20 ms PCM blocks, and pace against a cumulative stream clock.
- Reduce FFplay input analysis buffering. Retain bounded per-session gain/mute and driver failover.
- Show the first video frame while the audio device opens; move optional subtitle extraction to one background worker with stale-track cancellation.
- Decode terminal video at the renderer's visible detail budget while preserving native-window resolution and selectable quality profiles.
- Anchor decoder resizes to the presentation clock, cache hardware detection, retain software fallback across seeks, and rate-limit large-desync recovery instead of repeatedly restarting lagging video.
- Add playback performance regressions for startup, pacing, decoder churn, resize timing and asynchronous subtitle loading.

## [1.4.0] - 2026-10-17

### Security
- Require per-session credentials for local media IPC; bound client/message resources and close accepted sockets on shutdown.
- Remove implicit working-directory executable discovery and pass notification text as data rather than AppleScript source.
- Preserve original audio during failed cover remuxing and quarantine history only for confirmed SQLite corruption.
- Bound image transfers and decoded image/animation memory; sanitize local file names for terminal display.

### Fixed
- Require completed media artifacts for download success and report partial Instagram carousel failures.
- Keep one-shot output overrides temporary, separate JSON from progress output, and honor forced downloads.
- Make media initialization cleanup exception-safe, preserve playing-track identity when shuffling, and retain GIF animation frames.
- Stream audio in bounded PCM blocks with per-session gain/mute and driver failover instead of whole-file temporary WAV conversion.
- Retry failed hardware video decoding using software, and prevent retired decoder workers from contaminating restarted streams.
- Correct native key handling, file-picker spaces/editing, REPL control routing, metadata parsing, and diagnostic write probes.
- Add process-safe configuration writes, explicit degraded diagnostics, and regression tests for audited failure paths.

### Packaging
- Declare media renderer and configuration-lock dependencies; align the package and release manifest at version 1.4.0.
- Restore Python 3.10-compatible uninstall command formatting.

## [1.3.0] - 2026-10-14

### Added
- New `/any <url>` REPL command and CLI command `pinak any <url>` to download media from any URL supported by `yt-dlp` (including direct media links and generic video/audio embeds).
- Real-time generic webpage media probing: automatically detects downloadable streams on platforms without dedicated extractors (e.g. Voicy soundboards, podcasts, and generic HTML5/OpenGraph video embeds).
- Multi-tier network fallback: Tier 1 fast HTTP HEAD request with a 2-second timeout, falling back to Tier 2 low-level TCP socket check on port 53 against `1.1.1.1` and `8.8.8.8` to prevent false offline detections behind corporate/restrictive proxies.
- Resilient notification fallback chain: Windows 10/11 native toast notifications via `win11toast`, falling back to macOS `osascript`, Linux desktop notifications, and Rich console status panels.

### Fixed
- Fixed static-ffmpeg discovery when packaged in site-packages bin directories without `ffmpeg.exe` in root, eliminating persistent `ffmpeg not found at ffmpeg.exe` notices.
- Fixed premature link rejection on generic sound and media sites like Voicy (`voicy.network`) by probing `yt-dlp` generic extractors when no dedicated extractor matches.
- Cleaned up duplicate/missing platform indicators in download summaries and dry-run output tables.

## [1.2.1] - 2026-10-13

### Fixed
- Fixed cross-platform `AttributeError` on non-Windows environments by using safe `getattr(subprocess, ...)` fallback for creation flags in `execute_uninstallation()`.
- Isolated user directory purging in unit tests to prevent `expanduser` side effects across test runs.

## [1.2.0] - 2026-10-13

### Added
- Interactive self-uninstallation feature via `pinak --uninstall` and REPL `/uninstall` command.
- Expressive confirmation dialog with emojis (`🥺💔`, `🗑️`, `📁`, `📜`, `🛡️`, `✨🎉`, `🌸✨`), protecting user downloaded media files in `./downloads/`.
- Automated detection of package manager installer (`uv tool`, `pipx`, or standard `pip`).
- Automated purging of saved configuration settings, history database (`history.db`), and local caches across Windows, Linux, and macOS.
- Detached background uninstaller process for Windows to bypass running executable file locks cleanly.

## [1.1.1] - 2026-10-13

### Fixed
- Fixed CI test failure in `test_ensure_ffmpeg_uses_fetched_binary` on Linux runners: added executable permission (`chmod 0o755`) to dummy test binary and isolated `shutil.which` to prevent fallback to host system `/usr/bin/ffmpeg`.

## [1.1.0] - 2026-10-12

### Added
- Promoted `static-ffmpeg>=2.5` to core package dependencies (`dependencies` in `pyproject.toml`): automatic zero-configuration FFmpeg/FFprobe binary provisioning on first execution across all platforms.
- Instagram high-resolution media extraction: `_best_thumbnail_url()` detects master `display_url` and direct CDN image URLs, eliminating low-resolution thumbnail fallback.
- Added URL regex dimension parser (`_infer_area_from_url`) to extract width and height from Instagram CDN paths (`s1080x1080`, `p1080x1080`, `1080w`) when API metadata omits dimensions.
- Added direct image URL validator (`_is_direct_image_url`) to filter out post webpage links.
- Preserved list ordering ties in candidate ranking to favor higher-quality candidates in ascending thumbnail sequences.
- `pinak/commands/` package: REPL display (`panels`, `info`) and single-command
  execution (`run`) extracted from the monolithic `cli.py` (1207 → ~700 lines).
- Single-command CLI flags: `--dry-run` (preview plan), `--json` (machine-readable
  output), `--version/-V`, `--verbose/-v`, `--log-file`; shell completions via
  `--install-completion` / `--show-completion`.
- Non-zero exit codes on download failure in single-command mode (scripting-friendly).
- `pinak/retry.py`: exponential backoff + jitter, transient-error classification.
- `pinak/exceptions.py`: actionable error hierarchy (network, FFmpeg, Instagram
  rate-limit/private-content, config, output-dir).
- `pinak/logging_setup.py`: file logging + verbose mode.
- `pinak/subproc.py`: centralized no-shell subprocess runner with timeouts.
- `pinak/ffmpeg_setup.py`: static-FFmpeg auto-fetch fallback (`pinak-cli[ffmpeg]` extra).
- Download integrity verification (missing/empty files never recorded as success).
- Parallel Instagram carousel downloads (bounded worker pool, single metadata pass).
- Split `connect_timeout` / `read_timeout` configuration with Pydantic validation.
- `pinak doctor`: executable checks, disk-space/config-validity checks, fix hints.
- Test suite: 130+ unit, integration, property-based (hypothesis) and subprocess
  entry-point tests; coverage gate 75% in CI (80% locally, REPL loop excluded).
- CI: lint (ruff), format (ruff-format, black), types (mypy strict on core modules),
  tests, Bandit (medium+), pip-audit, CycloneDX SBOM artifact, gitleaks.
- `requirements-lock.txt` (pip-compile pinned dev tree).
- `Dockerfile` for containerized runs; PyPI trusted-publishing workflow;
  release-please automation.
- `pinak/notify.py`: cross-platform notifications (Windows toast via
  win11toast, Rich panel fallback everywhere else).
- One-command FFmpeg provisioning: `pinak --install-ffmpeg` and `/ffmpeg`
  install the `pinak-cli[ffmpeg]` static build (no admin rights needed).
- Update notice in single-command mode (cached yt-dlp check; `/update` in REPL).
- Offline startup notice when the device has no internet.
- Instagram failure notice panel explaining platform-side blocks.
- `pinak doctor`: "CLI on PATH" check with `python -m pinak` fallback hint.
- `pinak --config-path` flag; `/config` shows the config file location.
- Legal disclaimer (README + in-app tip); install/PATH/FFmpeg docs rewritten.
- Pinak self-update: background PyPI check for `pinak-cli` itself (not just
  yt-dlp), startup/update notices in REPL and single-command mode, and
  `/update` now upgrades both packages with per-package results
  (`Updated … → …` vs `already the latest`) plus a restart prompt when Pinak
  itself changed.

### Changed
- `requires-python` raised to `>=3.10` (untested 3.9 floor dropped); CI matrix
  extended to Python 3.13.
- CLI is now a single Typer command: options parse in any order
  (`pinak <url> --quality 720p` works, previously a usage error).
- yt-dlp resilience options: resume partials (`continuedl`), retries,
  fragment retries, socket timeouts.
- Cancelled downloads keep partial files so the next run resumes.
- Pydantic-validated configuration with legacy key migration.

### Fixed
- Fixed unit test isolation for static-ffmpeg missing fallback tests by explicitly mocking `sys.modules["static_ffmpeg"] = None`.
- Removed stale rate-limit code paths referencing deleted history helpers
  (runtime `ImportError` / `NameError`).
- Bare `except:` clauses, ambiguous loop variables, and assorted lint findings.
- Bandit medium findings triaged with inline `# nosec` justifications.

## [1.0.0] - 2026-10-04

### Added
- Initial `pinak-cli`: interactive REPL + single-command media downloading
  (direct URLs via yt-dlp, Instagram posts/reels/stories/highlights).
- Bundled Windows FFmpeg/ffprobe, Rich terminal UI, SQLite history,
  Pydantic-settings configuration, environment doctor, update checker.
