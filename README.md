# Pinak

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CLI](https://img.shields.io/badge/CLI-Python%20Typer-orange.svg)](cli/pyproject.toml)
[![FFmpeg](https://img.shields.io/badge/Powered%20by-FFmpeg-red.svg)](https://ffmpeg.org/)

> A fast, reliable, and privacy-focused media downloader CLI for direct URLs and Instagram content.

> [!IMPORTANT]
> **Educational & Personal Archival Purpose**  
> Pinak is an open-source educational project and terminal interface wrapper around [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and [`FFmpeg`](https://ffmpeg.org/), designed for learning CLI architecture and personal media archiving.  
> ⚠️ **Notice:** Downloading content may violate a platform's Terms of Service. Only download media that you own, that is freely licensed, or that you have explicit permission to keep. Respect copyright laws and **be excellent to creators!**

Current source release: **1.4.3**. See the [release notes](cli/CHANGELOG.md),
[operating guide](cli/OPERATIONS.md), and [prior release readiness record](RELEASE_READINESS.md)
for behavior and verification. GitHub releases are created manually;
automatic release creation is disabled.

## Overview

Pinak is a cross-platform Python CLI tool and educational wrapper around `yt-dlp` that makes personal media archiving simple and reliable. It supports direct URL downloads, Instagram posts/reels/stories/highlights, quality and format selection, audio-video merging via FFmpeg, download history, and built-in diagnostics.

**Key Highlights:**
- 🚀 Clean, modular architecture
- 🎯 Rich terminal UX with progress bars & tables
- 🔒 Privacy-first – all data stays local
- ⚡ Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) for broad URL support
- 🎬 Seamless media processing via FFmpeg
- 🩺 Built-in `doctor` for environment diagnostics

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [CLI Usage](#cli-usage)
- [Configuration](#configuration)
- [Data & File Locations](#data--file-locations)
- [Technology Stack](#technology-stack)
- [Documentation](#documentation)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Security Notes](#security-notes)
- [Educational Purpose & Legal Disclaimer](#educational-purpose--legal-disclaimer)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Features

### Core Downloading
- **Direct URL Support** – Download from yt-dlp-supported sources
- **Quality Control** – Choose best/worst or specific quality
- **Format Selection** – Prefer MP4, MP3, or other formats
- **Smart Merging** – Auto-merge separate audio+video streams
- **Post-Processing** – Format conversion via FFmpeg

### Instagram Support
- **Posts & Carousels** – Download single/multi-item posts
- **Reels & IGTV** – Grab short/long-form videos
- **Stories & Highlights** – Access available story/highlight media
- **Profiles** – Download profile media (where accessible)

### Management & UX
- **Download History** – Track all downloads locally
- **Persistent Config** – Save your preferred settings
- **Rich CLI** – Colored output, tables, progress bars
- **Environment Diagnostics** – `doctor` command to debug issues
- **Update Checker** – Stay informed of new versions
- **Safe Filenames** – Auto-sanitized for cross-platform safety

## Quick Start

### Prerequisites
- Python 3.10 or higher
- pip (or uv/pipx)

### Installation (from source)

```bash
git clone https://github.com/Prince-1005/Pinak-CLI.git
cd Pinak-CLI
python -m venv .venv

# Activate the environment before the following commands:
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux:        . .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ./cli
```

Use the Python 3.10+ interpreter installed on your system (`python3` if needed).
For the latest published package, use `pipx install pinak-cli`; source and PyPI
versions can differ before a release. Check the result with `pinak --version`.

For development, from the repository root in the activated environment:

```bash
python -m pip install --require-hashes -r cli/requirements-lock.txt
python -m pip install --no-deps -e ./cli
pre-commit install --config cli/.pre-commit-config.yaml
```

For local playback on Debian/Ubuntu, install system audio and GUI prerequisites:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg libportaudio2 python3-tk
```

Tkinter must match the Python interpreter you use. See the
[playback installation guide](cli/OPERATIONS.md#playback-prerequisites) for Windows,
macOS, optional OpenCV, and headless environments.

### Verify Installation

```bash
pinak --version
# or
python -m pinak --version
```

### Run Diagnostics

```bash
pinak --doctor
```

### Direct CLI Usage

```bash
# Download from URL
pinak "https://example.com/video.mp4"

# Extract audio directly as MP3
pinak "https://youtu.be/VIDEO_ID" --audio

# Specify custom output and quality
pinak "https://example.com/video.mp4" -o "downloads" --quality 1080p

# Dry-run inspection
pinak "https://example.com/video.mp4" --dry-run
```

### Interactive REPL Mode

Launch the interactive prompt with auto-completion and rich features by running `pinak` with no arguments:

```bash
pinak
```

Inside the interactive shell:
- `/doctor` – Validate environment, tools, and connectivity
- `/history` – Browse or filter download history
- `/stats` – View download analytics and statistics
- `/config` – View active configuration
- `/audio <URL>` – Download and extract audio as MP3
- `/video <URL>` – Download video
- `/instagram <URL>` – Download Instagram media
- `/media <path>` – Open local media or the file picker
- `/play <path>` – Play local audio/video
- `/view <path>` – View local pictures
- `/ctl <command>` – Control the active player through authenticated local IPC
- `/update` – Update yt-dlp and Pinak CLI
- `/ffmpeg` – Download static FFmpeg build automatically
- `/help` – Show all available slash commands
- `/exit` – Exit interactive prompt

## Project Structure

```
Pinak-CLI/
├── README.md                          # Root README (this file)
├── PINAK_DOCUMENTATION.md             # Historical design reference
├── RELEASE_READINESS.md               # Release fixes and verification
├── CHANGELOG.md                       # Link to cli/CHANGELOG.md
├── .gitignore                         # Git exclusions
├── .github/                           # CI/CD workflows
│   └── workflows/                     # CI, manual publishing, release policy
└── cli/                               # CLI application
    ├── CLI_README.md                  # CLI-specific documentation
    ├── OPERATIONS.md                  # Installation, playback and recovery
    ├── CHANGELOG.md                   # Maintained release history
    ├── pyproject.toml                 # Packaging & dependencies
    ├── pinak_cli.py                   # Entry wrapper script
    ├── Dockerfile                     # Container image definition
    ├── .dockerignore                  # Docker build ignore rules
    ├── requirements-lock.txt          # Pinned lockfile for dependencies
    ├── requirements-runtime-lock.txt  # Runtime-only dependency lock
    ├── tools/                         # Clean-install and release-version checks
    ├── tests/                         # Unit, integration and regression tests
    └── pinak/                         # Core Python package
        ├── __init__.py                # Package init & version
        ├── __main__.py                # Module entry point
        ├── cli.py                     # Typer CLI & interactive REPL shell
        ├── commands/                  # REPL command handlers & UI panels
        ├── media/                     # Decoders, TUI/native output, IPC and controls
        ├── downloader.py              # Download engine (yt-dlp wrapper)
        ├── config.py                  # Pydantic Settings configuration
        ├── history.py                 # SQLite download history & tracking
        ├── doctor.py                  # Environment diagnostics
        ├── ffmpeg_setup.py            # Static FFmpeg installer utility
        ├── notify.py                  # Notifications & terminal banners
        ├── updater.py                 # PyPI update checker
        └── utils.py                   # Formatting & validation utilities
```

## CLI Usage

### Direct Command Syntax

```bash
pinak [URL] [OPTIONS]
```

| Option | Short | Description | Default |
|---|---|---|---|
| `--output` | `-o` | Output directory | `downloads/` |
| `--audio` | | Extract audio directly as MP3 | `False` |
| `--quality` | | Quality preset (`best`, `worst`, `720p`, `1080p`) | Config default |
| `--force` | | Force download even if URL exists in history | `False` |
| `--doctor` | | Run environment and dependency checks | `False` |
| `--dry-run` | | Simulate extraction without downloading | `False` |
| `--json` | | One JSON result on stdout; progress on stderr | `False` |
| `--verbose` | `-v` | Enable verbose debug output | `False` |
| `--log-file` | | Save detailed logs to specified file | None |
| `--version` | `-V` | Show version and exit | |
| `--install-ffmpeg` | | Automatically download a static FFmpeg binary | |
| `--config-path` | | Print absolute path to configuration file | |

**Examples:**
```bash
# Download best video
pinak "https://youtu.be/VIDEO_ID"

# Download 720p to custom folder
pinak "https://example.com/video" --quality 720p -o "D:/Media"

# Extract audio as MP3
pinak "https://youtu.be/AUDIO_ID" --audio

# Run diagnostic check
pinak --doctor
```

## Configuration

Use `/config` inside the REPL and `pinak --config-path` for the configuration
file location. Preferences include `output_dir`, `quality`, `audio_quality`,
`video_format`, `audio_format`, `retry_count`, `connect_timeout`, `read_timeout`,
`duplicate_action`, `history_enabled`, `ffmpeg_path` and `ffprobe_path`.
Explicit `PINAK_<SETTING>` environment variables override saved values for the
process; one-shot CLI options remain temporary. See the
[current operating guide](cli/OPERATIONS.md#preferences-and-local-storage).

## Data & File Locations

Config and SQLite history use platformdirs' `pinak-cli` user config/data
directories. The REPL command history is `~/.pinak_cli_history`. Default downloads
go to `downloads` relative to the current directory. `--log-file` selects an
explicit log path. IPC credentials live in the current user's application cache.
Run `pinak --config-path` to locate configuration on the current platform.

## Technology Stack

Python 3.10+, Typer, yt-dlp, FFmpeg, Rich, prompt-toolkit, Pydantic Settings,
platformdirs, Pillow, Mutagen, NumPy, SoundDevice and filelock. Optional OpenCV
provides a native window with Tkinter fallback. Media playback accepts local
files: `/media <path>` in the REPL or `pinak media <path>` from the CLI.

## Documentation

- **[Website/README.md](Website/README.md)** – Static informational website, automatic media showcase, local development and GitHub Pages deployment.
- **[cli/OPERATIONS.md](cli/OPERATIONS.md)** – Current installation, settings, media controls, recovery and release guidance.
- **[PINAK_DOCUMENTATION.md](PINAK_DOCUMENTATION.md)** – Historical 1.3 architecture/design notes; settings and claims may be obsolete.
- **[RELEASE_READINESS.md](RELEASE_READINESS.md)** – Current release checks and resolution of the final audit findings.
- **[cli/CLI_README.md](cli/CLI_README.md)** – CLI-specific documentation.

## Roadmap

- [x] Automated unit, integration, media and security regression tests
- [x] Integrate ruff, black, mypy, pre-commit
- [x] GitHub Actions CI/CD pipeline (cross-platform matrix + security audit)
- [x] Cross-platform FFmpeg auto-detection & static downloader
- [x] Docker support
- [x] Resume support for partial downloads
- [ ] MkDocs documentation site
- [x] REPL batch-file downloads

## Contributing

Contributions are welcome! Use the current [operating guide](cli/OPERATIONS.md) and
the development setup above for:
- Development setup
- Code style & standards
- Testing requirements
- Pull request process

## Security Notes

- **Local-First:** All config, history, and downloads stay on your machine.
- **No Telemetry:** Pinak collects no usage data.
- **Safe Paths:** Filenames are sanitized to prevent path traversal.
- **Credential Awareness:** If using Instagram sessions/cookies, handle them securely and never commit to git.
- **Dependencies:** Keep packages updated. Consider running `pip-audit` regularly.

## Educational Purpose & Legal Disclaimer

Pinak is developed exclusively as an **educational project, technical study of CLI architecture, and personal-archiving tool**. It serves as an open-source terminal wrapper around `yt-dlp` and `FFmpeg`.

- **Personal Archival Only:** This tool is intended for backing up your own media, downloading public domain material, freely licensed content (such as Creative Commons), or media you have explicit permission to save.
- **Platform Terms of Service:** Downloading content may violate the Terms of Service of platforms such as YouTube, Instagram, or TikTok. Users are solely responsible for ensuring compliance with all applicable platform policies and regional copyright laws.
- **Be Excellent to Creators:** Do not use this tool to pirate, re-upload, distribute, or monetize copyrighted works. Support the creators whose work you enjoy.
- **No DRM Circumvention:** Pinak does not circumvent or bypass Digital Rights Management (DRM), encryption, or access paywalls.
- **Limitation of Liability:** The software is provided "as is" under the [MIT License](LICENSE) without warranty of any kind. The authors and contributors assume no liability or responsibility for any misuse of this software.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) if available.

## Acknowledgements

Special thanks to:
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for the robust download engine
- [FFmpeg](https://ffmpeg.org/) for powerful media processing
- [Click](https://click.palletsprojects.com/) & [Rich](https://github.com/Textualize/rich) for an excellent CLI experience
- All open-source contributors who make projects like this possible

---

**Built with ❤️ for reliability, simplicity, and excellence.**
