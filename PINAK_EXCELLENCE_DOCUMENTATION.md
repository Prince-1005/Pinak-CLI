# Pinak – Excellence Documentation

**Version:** 1.2.1  
**Last Updated:** October 13, 2026  
**Location:** `D:\pinak Z`

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Vision & Mission](#2-vision--mission)
3. [Core Principles](#3-core-principles)
4. [Project Overview](#4-project-overview)
5. [Architecture](#5-architecture)
6. [Directory Structure](#6-directory-structure)
7. [Technology Stack](#7-technology-stack)
8. [Features](#8-features)
9. [Installation](#9-installation)
10. [Usage Guide](#10-usage-guide)
11. [Configuration](#11-configuration)
12. [Download Workflows](#12-download-workflows)
13. [Code Quality Standards](#13-code-quality-standards)
14. [Security & Privacy](#14-security--privacy)
15. [Performance & Reliability](#15-performance--reliability)
16. [Testing Strategy](#16-testing-strategy)
17. [Troubleshooting](#17-troubleshooting)
18. [Roadmap](#18-roadmap)
19. [Contributing](#19-contributing)
20. [Appendix](#20-appendix)

## 1. Executive Summary

Pinak is a robust, user-friendly media downloader CLI designed for reliability, simplicity, and cross-platform portability. It combines direct URL downloading with Instagram content extraction, powered by yt-dlp and FFmpeg for high-quality media processing.

This documentation defines the standards, architecture, and practices that make Pinak an excellence-driven project—from clean code and intuitive UX to security, performance, and maintainability.

## 2. Vision & Mission

**Vision:** To be a reliable, privacy-respecting, and developer-friendly media downloader that "just works" out of the box.

**Mission:** Deliver a clean, modular CLI that simplifies media downloading while respecting user privacy, maintaining code quality, and providing a frictionless experience across platforms.

## 3. Core Principles

| Principle | Description |
|---|---|
| **Clarity** | Simple commands, clear output, helpful errors. |
| **Reliability** | Graceful failure handling, retries, validation. |
| **Performance** | Efficient streaming, minimal overhead, smart processing. |
| **Security** | Local-first, safe paths, no telemetry, careful credential handling. |
| **Maintainability** | Modular design, DRY, readable code, clear boundaries. |
| **Portability** | Runs on Windows/Linux/macOS with minimal setup. |
| **User-Centric** | Rich feedback, progress bars, sensible defaults. |

## 4. Project Overview

### Purpose
Pinak helps users download media content efficiently with support for multiple sources, format control, and persistent state management.

### Key Capabilities
- Direct URL downloads from supported platforms (via yt-dlp)
- Instagram: posts, reels, stories, highlights, IGTV, profiles
- Quality/format selection with audio+video merging
- Post-processing via FFmpeg (conversion, merging, optimization)
- Download history tracking
- Configuration management with user preferences
- Environment diagnostics (`doctor` command)
- Update checking
- Rich terminal UI (progress, colors, tables)

### Target Users
- CLI users who need reliable media downloads
- Developers wanting a clean, extensible downloader base
- Users prioritizing privacy and local control

## 5. Architecture

### High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                        CLI Layer                             │
│  cli.py (Typer + Rich) - Commands, Options, REPL UX          │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    Orchestration Layer                        │
│  Router: Direct URL | Instagram Handler                       │
│  downloader.py · instagram.py                                 │
└──────────────────────────────┬────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Download Engine│  │  Config/History  │  │  Infra/Health   │
│  downloader.py  │  │ config.py/history│  │ doctor/updater  │
│  (yt-dlp+ffmpeg)│  │                 │  │                 │
└─────────┬───────┘  └─────────────────┘  └─────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Utilities Layer                             │
│  utils.py - Paths, Sanitization, FFmpeg, Formatting            │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                      Storage Layer                             │
│  downloads/ · config.json · history.json · logs               │
└─────────────────────────────────────────────────────────────┘
```

### Module Dependencies

| Module | Depends On | Purpose |
|---|---|---|
| `cli.py` | config, downloader, instagram, history, doctor, updater, utils | Main interface & orchestration |
| `downloader.py` | utils, config | Core download logic |
| `instagram.py` | utils, config | Instagram-specific extraction |
| `config.py` | utils, appdirs | Persistent settings |
| `history.py` | utils, appdirs | Download records |
| `doctor.py` | utils, config | System diagnostics |
| `updater.py` | utils, requests, packaging | Version checks |
| `utils.py` | stdlib + appdirs | Shared utilities |

### Design Patterns
- **Single Responsibility**: Each module has one clear purpose
- **Dependency Injection**: Config passed/shared where needed
- **Facade**: CLI provides unified interface to complex subsystems
- **Utility Module**: Common helpers centralized
- **Fail-Fast Validation**: Early checks via doctor/utils

## 6. Directory Structure

```text
pinak-z/
├── README.md
├── PINAK_EXCELLENCE_DOCUMENTATION.md
├── PINAK_FOLDER_ANALYSIS_REPORT.md
├── .gitignore
├── .github/
│   └── workflows/ci.yml
├── cli/
│   ├── README.md
│   ├── pyproject.toml
│   ├── pinak_cli.py
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── requirements-lock.txt
│   ├── tests/
│   └── pinak/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── commands/
│       ├── config.py
│       ├── downloader.py
│       ├── doctor.py
│       ├── ffmpeg_setup.py
│       ├── history.py
│       ├── notify.py
│       ├── updater.py
│       └── utils.py
└── downloads/
```

### Directory Purposes
| Path | Purpose |
|---|---|
| `cli/` | Main CLI application package |
| `cli/pinak/` | Core Python source code |
| `downloads/` | Default output directory for downloaded media |
| `root/*.md` | Project documentation |

## 7. Technology Stack

### Core Dependencies
| Library | Version (from pyproject) | Purpose |
|---|---|---|
| `yt-dlp` | Latest compatible | Download engine for direct URLs |
| `requests` | Latest | HTTP requests for updates/network checks |
| `tqdm` | Latest | Progress bars |
| `rich` | Latest | Rich terminal output, tables, colors |
| `typer` | Latest | CLI framework & argument parsing |
| `pydantic-settings` | Latest | Configuration management & validation |
| `platformdirs` | Latest | Cross-platform user data/config dirs |
| `packaging` | Latest | Version parsing/comparison |

### Build & Runtime
- **Language:** Python 3.10+
- **Build Backend:** setuptools
- **Entry Point:** `pinak = pinak.cli:run_cli`
- **FFmpeg:** System PATH or auto-installed via `pinak --install-ffmpeg`

## 8. Features

### Core Features
- ✅ Direct URL media download
- ✅ Multi-format support via yt-dlp
- ✅ Quality selection (best/worst/custom)
- ✅ Audio+video merging
- ✅ Format conversion
- ✅ Output directory customization
- ✅ Filename sanitization
- ✅ Resume capability (where supported)

### Instagram Features
- ✅ Posts (single/multi-image/video)
- ✅ Reels
- ✅ Stories
- ✅ Highlights
- ✅ IGTV videos
- ✅ Profile media (with limits)
- ✅ Session-aware handling considerations

### UX & Management
- ✅ Rich CLI with colors/tables
- ✅ Progress bars (tqdm)
- ✅ Verbose/quiet modes
- ✅ Download history (view/track)
- ✅ Config persistence
- ✅ Environment diagnostics (`doctor`)
- ✅ Update checker
- ✅ Safe path handling

### Developer Experience
- ✅ Modular architecture
- ✅ Clear separation of concerns
- ✅ Reusable utilities
- ✅ Comprehensive logging
- ✅ Type-safe config via Pydantic
- ✅ Modern packaging

## 9. Installation

### Prerequisites
- Python 3.10 or higher
- pip/uv/pipx (recommended)

### From Source (Current Directory)
```bash
cd "D:\pinak Z\cli"
pip install -e .
```

### Using pip
```bash
cd "D:\pinak Z\cli"
pip install .
```

### Using uv (Fast)
```bash
cd "D:\pinak Z\cli"
uv pip install -e .
```

### Using pipx (Isolated)
```bash
cd "D:\pinak Z\cli"
pipx install .
```

### Verify Installation
```bash
pinak --version
# or
python -m pinak --version
```

### Post-Install Check
```bash
pinak doctor
```

This validates Python, FFmpeg, dependencies, network, disk space.

## 10. Usage Guide

### Basic Syntax
```bash
pinak [URL] [OPTIONS]
```

### Direct CLI Flags
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

### Interactive REPL Mode
Running `pinak` without arguments launches an interactive shell with auto-completion:
- `/doctor` – Health check
- `/history` – Search and inspect history
- `/stats` – View download stats
- `/audio <URL>` – Download as MP3
- `/video <URL>` – Download video
- `/instagram <URL>` – Download Instagram content
- `/batch <file>` – Download batch list of URLs
- `/update` – Update tools to latest versions
- `/exit` – Exit interactive prompt

### Examples

**Download from direct URL:**
```bash
pinak download "https://example.com/video.mp4"
pinak download "https://example.com/video" --quality best
pinak download "https://example.com/video" --format mp4 --output "D:\pinak Z\downloads"
```

**Download Instagram content:**
```bash
pinak instagram "https://www.instagram.com/p/POST_ID/"
pinak instagram "https://www.instagram.com/reel/REEL_ID/"
pinak instagram "https://www.instagram.com/stories/USERNAME/"
pinak instagram "https://www.instagram.com/highlights/ID/"
```

**Quality & Format:**
```bash
# Best quality (default)
pinak download <URL> --quality best

# Specific format
pinak download <URL> --format mp4

# Custom resolution if available
pinak download <URL> --quality 1080p
```

**History & Config:**
```bash
# View recent downloads
pinak history

# Show full history
pinak history --all

# Show current config
pinak config --show

# Set default output directory
pinak config --set output_dir "D:/Downloads/Pinak"
```

**Diagnostics:**
```bash
# Full health check
pinak doctor

# Verbose diagnostics
pinak doctor --verbose
```

## 11. Configuration

### Config Location
Config is stored in user data directory via `appdirs`:
- **Windows:** `C:\Users\<User>\AppData\Local\pinak\pinak\config.json`
- **Linux:** `~/.config/pinak/config.json`
- **macOS:** `~/Library/Application Support/pinak/config.json`

### Config Schema (Recommended)
```json
{
  "output_dir": "D:/pinak Z/downloads",
  "default_quality": "best",
  "default_format": "mp4",
  "merge_audio": true,
  "use_bundled_ffmpeg": true,
  "ffmpeg_path": null,
  "ffprobe_path": null,
  "max_retries": 3,
  "timeout": 30,
  "history_enabled": true,
  "verbose": false,
  "user_agent": "PinakZ/1.0.0"
}
```

### Key Settings
| Setting | Type | Default | Description |
|---|---|---|---|
| `output_dir` | str | `downloads/` (relative) or resolved path | Default download location |
| `default_quality` | str | `"best"` | Preferred quality |
| `default_format` | str | `"mp4"` | Preferred output format |
| `merge_audio` | bool | `true` | Merge separate audio/video streams |
| `use_bundled_ffmpeg` | bool | `true` | Use bundled FFmpeg if available |
| `ffmpeg_path`/`ffprobe_path` | str/null | `null` | Custom FFmpeg paths |
| `max_retries` | int | `3` | Retry attempts on failure |
| `timeout` | int | `30` | Network timeout (seconds) |
| `history_enabled` | bool | `true` | Track downloads in history |

### Managing Config
Use the `config` command or edit the JSON file directly. Always validate with `pinak doctor` after changes.

## 12. Download Workflows

### Direct URL Download Flow
1. **Parse**: CLI validates URL
2. **Probe**: yt-dlp extracts info (formats, title, duration)
3. **Select**: Choose streams based on quality/format
4. **Download**: Stream to temp with progress
5. **Post-Process**: Merge/convert via FFmpeg if needed
6. **Finalize**: Move to `output_dir` with sanitized name
7. **Record**: Save to history
8. **Report**: Show success details

### Instagram Download Flow
1. **Validate**: Check URL is Instagram
2. **Extract**: Parse post/reel/story/highlight/profile
3. **Resolve Media**: Get direct media URLs
4. **Download**: Fetch each media item
5. **Process**: Handle carousel (multiple items)
6. **Name**: Generate descriptive, sanitized filenames
7. **Record & Report**: Same as above

### Post-Processing (FFmpeg)
- **Merging**: Combine best video + best audio when separate
- **Format Conversion**: Convert to requested format
- **Metadata**: Preserve/clean as appropriate
- **Optimization**: Optional stream copy where safe

## 13. Code Quality Standards

### Style Guidelines
- Follow PEP 8 for Python code
- Use descriptive, intention-revealing names
- Keep functions small and focused (< 50 lines ideally)
- Max line length: 88–100 chars (Black-compatible)
- Use type hints for public APIs
- Write docstrings for modules, classes, functions

### Architecture Standards
- **Modularity**: No circular imports; clear dependency direction
- **Separation**: Platform logic isolated (Instagram adapter)
- **DRY**: Extract common logic to `utils.py`
- **Single Source of Truth**: Config, paths centralized
- **Error Handling**: Explicit exceptions, user-friendly messages

### Documentation Standards
- Update docs with code changes
- Keep README accurate and concise
- Use clear examples in CLI help
- Document non-obvious logic with comments sparingly

### Recommended Tooling
| Tool | Purpose | Config Location |
|---|---|---|
| `ruff` | Linting + import sorting | `pyproject.toml`/`ruff.toml` |
| `black` | Code formatting | `pyproject.toml` |
| `isort` | Import sorting (if not via ruff) | `pyproject.toml` |
| `mypy` | Static type checking | `mypy.ini`/`pyproject.toml` |
| `pytest` | Testing framework | `pyproject.toml`/`pytest.ini` |
| `pre-commit` | Git hooks | `.pre-commit-config.yaml` |

## 14. Security & Privacy

### Privacy-First Design
- **Local-Only**: All downloads and history stored locally
- **No Telemetry**: No analytics, tracking, or crash reporting
- **Minimal Network**: Only for downloads + optional update check
- **No Remote Logging**: Logs stay on user's machine

### Security Practices
- **Path Safety**: Filename sanitization prevents traversal attacks
- **Safe Subprocess**: FFmpeg invoked with validated args
- **Input Validation**: URLs validated before processing
- **Credential Caution**: If using cookies/sessions for Instagram, store securely and never commit
- **Dependency Hygiene**: Keep deps updated; audit with `pip-audit`
- **No Hardcoded Secrets**: Zero credentials in source

### User Data
| Data | Location | Notes |
|---|---|---|
| `config.json` | User config dir | User preferences (local) |
| `history.json` | User data dir (or configurable) | Download records (local) |
| Downloaded files | `downloads/` | User content (local) |
| Logs | Temp/user dir | If enabled (local) |

## 15. Performance & Reliability

### Performance Optimizations
- **Streaming Downloads**: Avoid loading entire files in memory
- **yt-dlp Efficiency**: Leverages optimized extraction
- **Smart Format Selection**: Chooses best compatible streams
- **Conditional Merging**: Skip FFmpeg if not needed
- **Progress Reporting**: Non-blocking, accurate

### Reliability Measures
- **Retry Logic**: Configurable retries on transient failures
- **Timeouts**: Network timeouts prevent hanging
- **Validation**: Pre-flight checks (disk space, FFmpeg)
- **Graceful Errors**: Clear messages with actionable hints
- **Atomic-ish Operations**: Write to temp then move
- **Doctor Checks**: Proactive environment validation

### Resource Considerations
- **Disk I/O**: Efficient streaming
- **Memory**: Minimal footprint; large files stream
- **CPU**: FFmpeg is main CPU consumer during merge/convert
- **Network**: Respects source constraints; no aggressive parallelism

## 16. Testing Strategy

### Test Pyramid
| Layer | Focus | Coverage Goal |
|---|---|---|
| **Unit** | Pure functions (`utils.py`, validators) | 80%+ |
| **Integration** | Module interactions (config+history, CLI flow) | 60–70% |
| **E2E** | End-to-end with mocks (download flow) | Critical paths |

### Test Structure
```text
tests/
├── unit/
│   ├── test_utils.py
│   ├── test_config.py
│   └── test_history.py
├── integration/
│   ├── test_cli.py
│   └── test_downloader_mock.py
└── conftest.py
```

### Testing Priorities
1. **High-value:** `utils.py` (sanitization, paths, formatting)
2. **High-value:** `config.py` (load/save, defaults, validation)
3. **High-value:** `history.py` (CRUD, persistence)
4. **Medium:** `doctor.py` (checks, reporting)
5. **Medium:** CLI parsing/commands

### Running Tests (Future)
```bash
# Install test deps
pip install pytest pytest-cov pytest-mock

# Run tests
pytest

# With coverage
pytest --cov=pinak --cov-report=term-missing

# Target specific module
pytest tests/unit/test_utils.py -v
```

### Mocking Strategy
- Mock `requests.get/post` for network calls
- Mock `yt-dlp.YoutubeDL` for downloads
- Mock `subprocess.run` for FFmpeg
- Mock filesystem with `tmp_path`/`monkeypatch`

## 17. Troubleshooting

### Quick Diagnostics
```bash
pinak doctor --verbose
```

Checks: Python, FFmpeg/ffprobe, dependencies, network, disk, permissions.

### Common Issues

| Issue | Symptom | Fix |
|---|---|---|
| **FFmpeg not found** | "ffmpeg not found" errors | Run `pinak doctor`. Use bundled or set custom path in config. |
| **Download fails** | Network/403/404 errors | Check URL validity, network, retry with `--verbose`. |
| **Instagram blocked** | Extraction fails | May need updated handling; check for rate limits. |
| **Permission denied** | Can't write to output dir | Choose writable directory via `--output` or config. |
| **Disk full** | Write errors | Free space, use different `output_dir`. |
| **Slow downloads** | Poor speeds | Check network, try different quality/format. |

### Debug Mode
```bash
pinak --verbose download <URL>
pinak --verbose doctor
```

### Log Locations
Check CLI output with `--verbose`. Future: add `--log-file` for persistent logs.

## 18. Roadmap

### Completed Milestones
- [x] Comprehensive pytest test suite (170+ unit, integration, and security tests)
- [x] Integrate ruff + black + mypy linting and type checking
- [x] Multi-OS GitHub Actions CI (Ubuntu, Windows, macOS on Python 3.10–3.12)
- [x] Security audit CI job (bandit static analysis + pip-audit dependency scanner)
- [x] Automated CycloneDX SBOM generation
- [x] Docker support with pre-installed FFmpeg
- [x] Cross-platform static FFmpeg auto-installer (`pinak --install-ffmpeg`)
- [x] Persistent `--log-file` logging option

### Future Roadmap
- [ ] Resume support for partial downloads
- [ ] MkDocs documentation site
- [ ] Download queue/batch progress enhancement
- [ ] Plugin system for custom sources

### Quality Goals
- **Test Coverage:** >= 80% on core modules
- **Type Coverage:** >= 90% (mypy strict on public APIs)
- **Lint Score:** 0 ruff errors
- **CI Pass Rate:** 100% on main branch

## 19. Contributing

We welcome contributions that align with our core principles.

### Getting Started
1. Fork the repo
2. Clone locally: `git clone <fork-url>`
3. Create venv: `python -m venv .venv && .venv\Scripts\activate` (Windows)
4. Install dev deps: `pip install -e ".[dev]"` (if defined) or manual
5. Create feature branch: `git checkout -b feature/your-feature`
6. Make changes with tests
7. Run checks: lint, typecheck, tests
8. Submit PR with clear description

### Contribution Guidelines
- **Code Style:** Follow PEP 8; run ruff/black
- **Tests:** Add/update tests for new functionality
- **Commits:** Use clear, conventional messages
- **Docs:** Update README/excellence docs
- **Scope:** Keep changes focused and minimal
- **Security:** Never commit secrets; flag security issues privately

### Development Setup (Recommended)
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -e .
pip install pytest ruff black mypy pre-commit

# Setup hooks
pre-commit install
```

## 20. Appendix

### A. Architecture Diagram (Text)
See Section 5 for layered architecture and data flow.

### B. Module Responsibility Matrix
| Module | Core Logic | I/O | Config | Network | Subprocess | UI |
|---|---|---|---|---|---|---|
| `cli.py` | ★★★★☆ | ★★☆☆☆ | ★★★☆☆ | ★☆☆☆☆ | ★☆☆☆☆ | ★★★★★ |
| `downloader.py` | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★★☆ | ★★★★☆ | ★★☆☆☆ |
| `instagram.py` | ★★★★★ | ★★★★☆ | ★★☆☆☆ | ★★★★☆ | ★★☆☆☆ | ★★☆☆☆ |
| `utils.py` | ★★★★☆ | ★★★☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★☆☆☆☆ |
| `config.py` | ★★★☆☆ | ★★★★★ | ★★★★★ | ★☆☆☆☆ | ★☆☆☆☆ | ★☆☆☆☆ |
| `history.py` | ★★★☆☆ | ★★★★★ | ★★★☆☆ | ★☆☆☆☆ | ★☆☆☆☆ | ★☆☆☆☆ |
| `doctor.py` | ★★★★☆ | ★★★☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★☆☆ | ★★★★☆ |
| `updater.py` | ★★★☆☆ | ★★★☆☆ | ★★☆☆☆ | ★★★★☆ | ★☆☆☆☆ | ★★★☆☆ |

### C. Command Reference Quick Card
```bash
pinak --help
pinak "<URL>"
pinak "<URL>" --audio
pinak "<URL>" --quality 1080p
pinak --doctor
pinak --install-ffmpeg
pinak --config-path
```

### D. Environment Checklist
Run `pinak --doctor` to validate:
- [ ] Python 3.10+ installed
- [ ] All dependencies installed
- [ ] FFmpeg/ffprobe available (system or static build)
- [ ] Network connectivity
- [ ] Disk space sufficient
- [ ] Output directory writable
- [ ] Config file readable/writable

### E. Versioning
Follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`
- **MAJOR:** Breaking changes
- **MINOR:** New features (backward compatible)
- **PATCH:** Bug fixes

Current: `1.2.1`

### F. Acknowledgements
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) – Powerful download engine
- [Typer](https://typer.tiangolo.com/) – CLI framework
- [Rich](https://github.com/Textualize/rich) – Beautiful terminal output
- [tqdm](https://github.com/tqdm/tqdm) – Progress bars
- [FFmpeg](https://ffmpeg.org/) – Media processing
- [platformdirs](https://github.com/tox-dev/platformdirs) – Cross-platform dirs
- [Pydantic](https://docs.pydantic.dev/) – Data validation

---

**Excellence is a habit, not an act.** This documentation reflects Pinak's commitment to quality, clarity, and user-centric design.
