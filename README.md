# Pinak Z

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CLI](https://img.shields.io/badge/CLI-Python%20Click-orange.svg)](cli/pyproject.toml)
[![FFmpeg](https://img.shields.io/badge/Powered%20by-FFmpeg-red.svg)](https://ffmpeg.org/)

> A fast, reliable, and privacy-focused media downloader CLI for direct URLs and Instagram content.

## Overview

Pinak Z is a cross-platform Python CLI tool that makes downloading media simple and reliable. It supports direct URL downloads, Instagram posts/reels/stories/highlights, quality and format selection, audio-video merging via FFmpeg, download history, and built-in diagnostics.

**Key Highlights:**
- 🚀 Clean, modular architecture
- 🎯 Rich terminal UX with progress bars & tables
- 🔒 Privacy-first – all data stays local
- ⚡ Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) for broad URL support
- 🎬 Bundled FFmpeg for seamless post-processing
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
- Python 3.8 or higher
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
pinak doctor
```

### Basic Usage

```bash
# Download from URL
pinak download "https://example.com/video.mp4"

# Download Instagram reel
pinak instagram "https://www.instagram.com/reel/REEL_ID/"

# View history
pinak history

# Check config
pinak config --show

# Get help
pinak --help
```

## Project Structure

```
D:\pinak Z\
├── README.md                          # Root README (this file)
├── PINAK_EXCELLENCE_DOCUMENTATION.md  # Comprehensive excellence guide
├── PINAK_FOLDER_ANALYSIS_REPORT.md    # Detailed folder analysis
├── PINAK_ANDROID_APP_EXCELLENCE_GUIDE.md # Android app guide
├── .gitignore                         # Git exclusions
├── cli/                               # CLI application
│   ├── README.md                      # CLI-specific docs
│   ├── pyproject.toml                 # Packaging & dependencies
│   ├── pinak_cli.py                   # Entry wrapper
│   ├── ffmpeg.exe                     # Bundled FFmpeg (Windows)
│   ├── ffprobe.exe                    # Bundled FFprobe (Windows)
│   └── pinak/                         # Core package
│       ├── cli.py                     # CLI interface
│       ├── downloader.py              # Download engine
│       ├── instagram.py               # Instagram handler
│       ├── config.py                  # Config management
│       ├── history.py                 # History tracking
│       ├── doctor.py                  # Diagnostics
│       ├── updater.py                 # Update checker
│       ├── utils.py                   # Utilities
│       ├── __init__.py                # Package init
│       ├── __main__.py                # Module entry
│       └── __pycache__/               # Compiled files
└── downloads/                         # Default downloads folder
```

## CLI Usage

### Download Command

```bash
pinak download <URL> [OPTIONS]
```

| Option | Description | Default |
|---|---|---|
| `--output`, `-o` | Output directory | `downloads/` |
| `--quality`, `-q` | Quality (best/worst/1080p/etc.) | `best` |
| `--format`, `-f` | Output format (mp4/mp3/webm) | `mp4` |
| `--no-merge` | Don't merge audio+video | `false` |

**Examples:**
```bash
pinak download "https://youtu.be/VIDEO_ID" --quality 720p
pinak download "https://example.com/video" --format mp4 --output "C:\Downloads"
```

### Instagram Command

```bash
pinak instagram <URL> [OPTIONS]
```

| Option | Description | Default |
|---|---|---|
| `--output`, `-o` | Output directory | `downloads/` |
| `--quality`, `-q` | Preferred quality | `best` |

**Examples:**
```bash
pinak instagram "https://www.instagram.com/p/ABC123/"
pinak instagram "https://www.instagram.com/reel/XYZ789/"
pinak instagram "https://www.instagram.com/stories/username/"
```

### History Command

```bash
pinak history [OPTIONS]
```

| Option | Description |
|---|---|
| `--limit`, `-l` | Show last N entries (default: 10) |
| `--all`, `-a` | Show all history entries |

```bash
pinak history --limit 5
pinak history --all
```

### Config Command

```bash
pinak config [OPTIONS]
```

| Option | Description |
|---|---|
| `--show` | Display current configuration |
| `--set KEY=VALUE` | Set a config value |

```bash
pinak config --show
pinak config --set output_dir="D:/MyDownloads"
pinak config --set default_quality="720p"
```

### Doctor Command

```bash
pinak doctor [OPTIONS]
```

Runs comprehensive environment checks.

```bash
pinak doctor
pinak doctor --verbose
```

### Update Command

```bash
pinak update
```

Checks for newer versions.

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
| **Language** | Python 3.8+ | Core implementation |
| **CLI Framework** | [Click](https://click.palletsprojects.com/) | Command-line interface |
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
- **[PINAK_ANDROID_APP_EXCELLENCE_GUIDE.md](PINAK_ANDROID_APP_EXCELLENCE_GUIDE.md)** – Android app implementation excellence guide.

## Roadmap

- [ ] Add comprehensive pytest test suite
- [ ] Integrate ruff, black, mypy, pre-commit
- [ ] GitHub Actions CI/CD pipeline
- [ ] Resume support for partial downloads
- [ ] Cross-platform FFmpeg auto-detection
- [ ] MkDocs documentation site
- [ ] Docker support
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
