# Pinak Z

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CLI](https://img.shields.io/badge/CLI-Python%20Typer-orange.svg)](cli/pyproject.toml)
[![FFmpeg](https://img.shields.io/badge/Powered%20by-FFmpeg-red.svg)](https://ffmpeg.org/)

> A fast, reliable, and privacy-focused media downloader CLI for direct URLs and Instagram content.

> [!IMPORTANT]
> **Educational & Personal Archival Purpose**  
> Pinak Z is an open-source educational project and terminal interface wrapper around [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) and [`FFmpeg`](https://ffmpeg.org/), designed for learning CLI architecture and personal media archiving.  
> ⚠️ **Notice:** Downloading content may violate a platform's Terms of Service. Only download media that you own, that is freely licensed, or that you have explicit permission to keep. Respect copyright laws and **be excellent to creators!**

## Overview

Pinak Z is a cross-platform Python CLI tool and educational wrapper around `yt-dlp` that makes personal media archiving simple and reliable. It supports direct URL downloads, Instagram posts/reels/stories/highlights, quality and format selection, audio-video merging via FFmpeg, download history, and built-in diagnostics.

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
# Navigate to CLI directory
cd "D:\pinak Z\cli"

# Install in editable mode (recommended for development)
pip install -e .

# Or regular install
pip install .
```

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
- `/update` – Update yt-dlp and Pinak CLI
- `/ffmpeg` – Download static FFmpeg build automatically
- `/help` – Show all available slash commands
- `/exit` – Exit interactive prompt

## Project Structure

```
D:\pinak Z\
├── README.md                          # Root README (this file)
├── PINAK_EXCELLENCE_DOCUMENTATION.md  # Comprehensive technical guide
├── PINAK_FOLDER_ANALYSIS_REPORT.md    # Detailed codebase analysis
├── .gitignore                         # Git exclusions
├── .github/                           # CI/CD workflows
│   └── workflows/ci.yml               # Multi-OS automated test & security pipeline
└── cli/                               # CLI application
    ├── README.md                      # CLI-specific documentation
    ├── pyproject.toml                 # Packaging & dependencies
    ├── pinak_cli.py                   # Entry wrapper script
    ├── Dockerfile                     # Container image definition
    ├── .dockerignore                  # Docker build ignore rules
    ├── requirements-lock.txt          # Pinned lockfile for dependencies
    ├── tests/                         # Pytest test suite (170+ tests)
    └── pinak/                         # Core Python package
        ├── __init__.py                # Package init & version
        ├── __main__.py                # Module entry point
        ├── cli.py                     # Typer CLI & interactive REPL shell
        ├── commands/                  # REPL command handlers & UI panels
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
| `--json` | | Output JSON metadata (pairs with `--dry-run`) | `False` |
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

Pinak Z uses a JSON config file stored in your user data directory. Use `pinak config --show` to view current settings.

**Common settings:**
- `output_dir` – Default download location
- `default_quality` – Preferred quality (`best`, `worst`, etc.)
- `default_format` – Preferred format (`mp4`, `mp3`)
- `merge_audio` – Auto-merge streams (`true`/`false`)
- `max_retries` – Retry attempts on failure
- `timeout` – Network timeout in seconds
- `history_enabled` – Track download history

See [Excellence Documentation](PINAK_EXCELLENCE_DOCUMENTATION.md#11-configuration) for full schema and details.

## Data & File Locations

| Item | Windows | Linux | macOS |
|---|---|---|---|
| **Config** | `C:\Users\<User>\AppData\Local\pinak\pinak\config.json` | `~/.config/pinak/config.json` | `~/Library/Application Support/pinak/config.json` |
| **History** | Same data dir as above (`history.json`) | Same as above | Same as above |
| **Downloads** | `D:\pinak Z\downloads\` (default) or custom | `~/Downloads/Pinak/` or custom | `~/Downloads/Pinak/` or custom |
| **Logs** | User temp/data dir (if enabled) | `~/.local/share/pinak/` or temp | Temp dir |

## Technology Stack

| Category | Technology | Purpose |
|---|---|---|
| **Language** | Python 3.10+ | Core implementation |
| **CLI Framework** | [Typer](https://typer.tiangolo.com/) | Command-line interface & argument parsing |
| **Download Engine** | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Media extraction/download |
| **Media Processing** | [FFmpeg](https://ffmpeg.org/) | Merging, conversion, processing |
| **Terminal UI** | [Rich](https://github.com/Textualize/rich), [tqdm](https://github.com/tqdm/tqdm) | Beautiful output & progress |
| **HTTP** | [requests](https://docs.python-requests.org/) | Network requests |
| **Config/Validation** | [Pydantic](https://docs.pydantic.dev/) | Data validation |
| **Cross-Platform Paths** | [appdirs](https://github.com/ActiveState/appdirs) | User dirs |
| **Versioning** | [packaging](https://packaging.python.org/) | Version comparison |
| **Packaging** | [setuptools](https://setuptools.pypa.io/) | Build/distribution |

## Documentation

- **[PINAK_EXCELLENCE_DOCUMENTATION.md](PINAK_EXCELLENCE_DOCUMENTATION.md)** – Complete technical guide: architecture, features, config, testing, roadmap, troubleshooting.
- **[PINAK_FOLDER_ANALYSIS_REPORT.md](PINAK_FOLDER_ANALYSIS_REPORT.md)** – In-depth folder/codebase analysis with strengths & recommendations.
- **[cli/README.md](cli/README.md)** – CLI-specific documentation.

## Roadmap

- [x] Add comprehensive pytest test suite (170+ tests covering unit, e2e, security)
- [x] Integrate ruff, black, mypy, pre-commit
- [x] GitHub Actions CI/CD pipeline (cross-platform matrix + security audit)
- [x] Cross-platform FFmpeg auto-detection & static downloader
- [x] Docker support
- [ ] Resume support for partial downloads
- [ ] MkDocs documentation site
- [ ] Batch download queue

## Contributing

Contributions are welcome! Please read our [Excellence Documentation](PINAK_EXCELLENCE_DOCUMENTATION.md#19-contributing) for guidelines on:
- Development setup
- Code style & standards
- Testing requirements
- Pull request process

## Security Notes

- **Local-First:** All config, history, and downloads stay on your machine.
- **No Telemetry:** Pinak Z collects no usage data.
- **Safe Paths:** Filenames are sanitized to prevent path traversal.
- **Credential Awareness:** If using Instagram sessions/cookies, handle them securely and never commit to git.
- **Dependencies:** Keep packages updated. Consider running `pip-audit` regularly.

## Educational Purpose & Legal Disclaimer

Pinak Z is developed exclusively as an **educational project, technical study of CLI architecture, and personal-archiving tool**. It serves as an open-source terminal wrapper around `yt-dlp` and `FFmpeg`.

- **Personal Archival Only:** This tool is intended for backing up your own media, downloading public domain material, freely licensed content (such as Creative Commons), or media you have explicit permission to save.
- **Platform Terms of Service:** Downloading content may violate the Terms of Service of platforms such as YouTube, Instagram, or TikTok. Users are solely responsible for ensuring compliance with all applicable platform policies and regional copyright laws.
- **Be Excellent to Creators:** Do not use this tool to pirate, re-upload, distribute, or monetize copyrighted works. Support the creators whose work you enjoy.
- **No DRM Circumvention:** Pinak Z does not circumvent or bypass Digital Rights Management (DRM), encryption, or access paywalls.
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
