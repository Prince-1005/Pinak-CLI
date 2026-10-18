# 🔱 PINAK CLI 1.4.4 — Media Content Downloader

PINAK CLI is a powerful, highly aesthetic command-line media downloader wrapper around `yt-dlp` and `ffmpeg`. It features a rich, interactive REPL shell with auto-completions, suggestions, customized banners, diagnostic tools, and automatic download tracking.

The [current operating guide](https://github.com/Prince-1005/Pinak-CLI/blob/main/cli/OPERATIONS.md) covers local playback, authenticated
IPC, configuration precedence, lock files, release artifacts and recovery limits.
The [release readiness record](https://github.com/Prince-1005/Pinak-CLI/blob/main/RELEASE_READINESS.md)
records release fixes and verification.

---

## 🚀 Key Features

*   **Interactive REPL Shell**: Features a terminal command prompt with auto-completions, command suggestions, and command history.
*   **Aesthetic UI**: Powered by `rich` and `prompt-toolkit` with vibrant color themes, tables, custom progress bars, and desktop toast notifications.
*   **Media Formats**: Download as best-quality video, select resolutions (360p, 720p, 1080p, etc.), or convert directly to high-quality MP3 audio.
*   **Local-First & Private**: All data, settings, and download histories remain strictly local on your machine with zero remote tracking.
*   **Self-Diagnostics**: High-detail environmental doctor checks (`/doctor`) to verify internet, dependencies, rate limits, and configuration.
*   **Local SQLite History**: Keeps record of your download URLs, sizes, durations, and output paths in a local SQLite database (`history.db`).

---

## 📦 Directory Structure

```text
cli/
├── pinak/                      # Core Package Folder
│   ├── __init__.py
│   ├── __main__.py             # Entry point (python -m pinak)
│   ├── cli.py                  # REPL Interactive Shell & Typer CLI handler
│   ├── commands/               # Modular REPL & info subcommands
│   ├── media/                  # Local playback, native windows, subtitles and IPC
│   ├── downloader.py           # yt-dlp & FFmpeg downloader logic
│   ├── config.py               # Application configurations (Pydantic-Settings)
│   ├── history.py              # SQLite storage & local tracking
│   ├── doctor.py               # Dependencies & connection diagnostics
│   ├── ffmpeg_setup.py         # Static FFmpeg installer utility
│   ├── notify.py               # Desktop notifications & terminal banners
│   ├── updater.py              # Update checker
│   └── utils.py                # Formatting & utility helpers
├── tests/                      # Automated test suite (pytest)
├── pyproject.toml              # Pyproject packaging config
├── requirements-lock.txt       # Locked dependencies for reproducible installs
├── requirements-runtime-lock.txt # Runtime dependency lock
├── tools/                      # Installation and release-version checks
├── OPERATIONS.md               # Current operating guide
├── CHANGELOG.md                # Maintained release history
├── Dockerfile                  # Container image (ffmpeg included)
├── .dockerignore               # Docker build ignore patterns
└── LICENSE                     # MIT license
```

> **Note:** FFmpeg is *not* bundled with the PyPI package. See
> [FFmpeg setup](#-ffmpeg-setup) below — one command installs it.

---

## 🛠️ Installation & Setup

### Requirements
*   Python 3.10 or higher.
*   FFmpeg (see [FFmpeg setup](#-ffmpeg-setup) — one command).

### Step 1: Install from PyPI

```bash
pip install pinak-cli
# recommended (isolated, always on PATH):
pipx install pinak-cli
```

This registers the global `pinak` command. From source (developers):

```bash
cd cli
pip install -e ".[dev]"
```

Clone [Prince-1005/Pinak-CLI](https://github.com/Prince-1005/Pinak-CLI) first and
use a virtual environment. PyPI installs the latest published version, which can
differ from the current source before release.

For playback on Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg libportaudio2 python3-tk
```

Tkinter must match the selected Python interpreter. Windows/macOS pip installs
of SoundDevice include PortAudio; Linux may need the system package above.
See the [playback prerequisite guide](https://github.com/Prince-1005/Pinak-CLI/blob/main/cli/OPERATIONS.md#playback-prerequisites)
for optional OpenCV and headless systems.

### Step 2: Test Command

```bash
pinak --doctor
pinak
```

> **`pinak` not found after install?** Your Python Scripts folder isn't on
> PATH. Either add it, use `pipx install pinak-cli`, or run
> `python -m pinak` instead — it works identically. `pinak --doctor`
> includes a "CLI on PATH" check that tells you exactly what to do.

---

## 🎞️ FFmpeg setup

FFmpeg merges formats and extracts MP3s. Pick one option:

```bash
pinak --install-ffmpeg        # single-command mode: downloads a static build
/ffmpeg                        # same thing, inside the interactive REPL
pip install "pinak-cli[ffmpeg]"  # manual equivalent (static-ffmpeg extra)
```

Or install FFmpeg system-wide ([ffmpeg.org/download](https://ffmpeg.org/download.html))
and make sure it is on PATH. Docker users already have it (`cli/Dockerfile`).

---

## 🔄 Keeping everything fresh

Sites change often; an outdated `yt-dlp` is the #1 cause of sudden failures.
Pinak checks PyPI in the background (max once per day) and notifies you —
about new `yt-dlp` **and** new Pinak releases. Inside the REPL, update both
any time with:

```
/update
```

This runs `pip install --upgrade yt-dlp` and `pip install --upgrade
pinak-cli`, tells you exactly what changed (`Updated … 1.0.0 → 1.1.0` vs
`already the latest`), and — if Pinak itself was upgraded — asks you to
restart the CLI (`/exit`, then run `pinak` again) so the new version loads.

---

## 💻 CLI Commands

When running the interactive REPL shell (`pinak`), the following commands are available:

| Command | Description |
| :--- | :--- |
| `/help` | Display the list of all available commands and shortcuts |
| `/doctor` | Run comprehensive environment and connectivity checks |
| `/audio <url>` | Download the media from the URL as an MP3 audio track |
| `/video <url>` | Download video from a URL |
| `/instagram <url>` | Download Instagram post, reel, or IGTV with metadata |
| `/media <path>` | Open local media or the file picker |
| `/play <path>` | Play a local audio/video file |
| `/view <path>` | View local pictures |
| `/ctl <command>` | Control the active player through authenticated local IPC |
| `/batch <file>` | Download multiple URLs from a text file |
| `/history` | View a list of recent downloads from your history database |
| `/config` | Print out the current config settings and environment |
| `/setout <dir>` | Change the output downloads directory |
| `/open` | Open the downloads directory in File Explorer |
| `/platform [q]` | List supported platforms or search filter them |
| `/update` | Update yt-dlp and Pinak CLI to the latest versions |
| `/ffmpeg` | Download a static FFmpeg build automatically |
| `/exit` | Terminate the interactive REPL shell |

---

## ⚙️ Configuration File

### Subtitle languages and playback

Use `/subs_lang` for the language picker, or `/subs_lang list` to see language
codes. Save one to three languages with, for example, `/subs_lang hi en es`.
Preferences are stored locally in the same `config.json` as the system settings
and appear in `/config`. The default language is English (`en`).

Use `/subs on` to enable subtitle downloads and `/subs off` to disable them;
`/subs` without an argument toggles the setting. Downloads request only the
selected language codes, prefer creator-provided captions over automatic
captions for the same code, and skip languages the video does not offer.
Regional codes are explicit choices (for example, `en-US` or `pt-BR`).
Missing subtitles do not prevent downloading the video. Subtitle conversion
and embedding require FFmpeg. HTTP 429 stops immediate retries and reports
the platform's rate limit.

In the TUI video player, subtitles begin off. Press `c` to show the first
available track, press it again to advance through tracks, and press it after
the last track to turn subtitles off. Another `c` starts the cycle again.
The player reads embedded subtitles and matching `.srt`/`.vtt` sidecar files;
it does not fetch new languages during playback.

Pinak CLI saves user-specific configuration (like download directory, quality, retry counts) in a standard configuration folder (via `platformdirs`).

- **Windows**: `%LOCALAPPDATA%\pinak\pinak-cli\config.json`
- **macOS**: `~/Library/Application Support/pinak-cli/config.json`
- **Linux**: `~/.config/pinak-cli/config.json`
- **SQLite history**: `platformdirs.user_data_dir("pinak-cli", "pinak")/history.db`;
  on Linux this is normally `~/.local/share/pinak-cli/history.db`, separate from configuration.

Run `pinak --config-path` anywhere to print your exact path, or `/config`
inside the REPL (the path is shown above the table). Change the output
folder with `/setout <absolute_path>`.

---

## 🔒 Privacy & Local-First

Pinak CLI is strictly local-first and privacy-focused. All configuration, download history, and media files remain on your local machine. No external tracking or telemetry is performed.

---

## ⚖️ Educational Purpose & Legal Disclaimer

Pinak CLI is developed as an **educational project, technical study of CLI architecture, and personal-archiving tool** wrapper around `yt-dlp` and `ffmpeg`. You are solely responsible for how you use it:

- **Personal Archival Only:** Only download content you own, that is freely licensed (e.g., Creative Commons), or that you have explicit permission to save.
- **Terms of Service:** Automated downloading may violate the Terms of Service of platforms such as YouTube, Instagram, or TikTok; your account or IP could be restricted by those platforms. Use at your own risk.
- **Be Excellent to Creators:** Do not use this tool to pirate, redistribute, or monetize copyrighted material without authorization. Always support and respect creators.
- **No DRM Circumvention:** Pinak CLI does not bypass or defeat Digital Rights Management (DRM) or access restrictions.
- **Limitation of Liability:** The authors provide this software "as is" under the [MIT License](https://github.com/Prince-1005/Pinak-CLI/blob/main/LICENSE) and accept no liability for misuse.
