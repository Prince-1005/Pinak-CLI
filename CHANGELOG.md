# Changelog

All notable changes to `pinak-cli` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/).
(This file is updated automatically by release-please from conventional commits.)

## [Unreleased]

### Added
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
