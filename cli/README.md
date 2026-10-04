# 🔱 PINAK CLI — Media Content Downloader

PINAK CLI is a powerful, highly aesthetic command-line media downloader wrapper around `yt-dlp` and `ffmpeg`. It features a rich, interactive REPL shell with auto-completions, suggestions, customized banners, diagnostic tools, and automatic download tracking.

---

## 🚀 Key Features

*   **Interactive REPL Shell**: Features a terminal command prompt with auto-completions, command suggestions, and command history.
*   **Aesthetic UI**: Powered by `rich` and `prompt-toolkit` with vibrant color themes, tables, custom progress bars, and desktop toast notifications.
*   **Media Formats**: Download as best-quality video, select resolutions (360p, 720p, 1080p, etc.), or convert directly to high-quality MP3 audio.
*   **Telemetry Tracking**: Silently pushes download statistics and command executions to the central Pinak Receiver Server.
*   **Self-Diagnostics**: High-detail environmental doctor checks (`/doctor`) to verify internet, dependencies, rate limits, and configuration.
*   **Local SQLite History**: Keeps record of your download URLs, sizes, durations, and output paths in a local SQLite database (`history.db`).

---

## 📦 Directory Structure

```text
cli/
├── pinak/                      # Core Package Folder
│   ├── __init__.py
│   ├── __main__.py             # Entry point (python -m pinak)
│   ├── cli.py                  # REPL Interactive Shell & CLI handler
│   ├── downloader.py           # yt-dlp & FFmpeg downloader logic
│   ├── config.py               # Application configurations (Pydantic-Settings)
│   ├── history.py              # SQLite storage & Receiver integration
│   ├── doctor.py               # Dependencies & connection diagnostics
│   └── utils.py                # Formatting & clipboard utility helpers
├── extra/                      # Unnecessary / legacy resources & tools
│   ├── .pinak_history.json.bak # History backup
│   ├── PINAK_CLI_EXCELLENCE_GUIDE.md # Blueprint / guides
│   ├── instagram.py            # Legacy Instagram downloader module
│   └── supabase_setup.sql      # Legacy database setup schema
├── downloads/                  # Default output folder (excluded)
├── pyproject.toml              # Pyproject packaging config
├── pinak_cli.py                # Wrapper startup script
├── LICENSE                     # MIT license
└── Dockerfile                  # Container image (ffmpeg included)
```

> **Note:** FFmpeg is *not* bundled with the PyPI package. See
> [FFmpeg setup](#-ffmpeg-setup) below — one command installs it.
```

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
| `/quality <val>`| Change download quality (e.g. `best`, `worst`, `720p`, `1080p`) |
| `/history` | View a list of recent downloads from your history database |
| `/config` | Print out the current config settings and environment |
| `/setout <dir>` | Change the output downloads directory |
| `/open` | Open the downloads directory in File Explorer |
| `/paste` | Retrieve a URL from clipboard and trigger download |
| `/platform [q]` | List supported platforms or search filter them |
| `/exit` | Terminate the interactive REPL shell |

---

## ⚙️ Configuration File

Pinak CLI saves user-specific configuration (like download directory, quality, retry counts) in a standard configuration folder (via `platformdirs`).

- **Windows**: `%LOCALAPPDATA%\pinak\pinak-cli\config.json`
- **macOS**: `~/Library/Application Support/pinak-cli/config.json`
- **Linux**: `~/.config/pinak-cli/config.json`
- **SQLite history**: alongside it (`history.db`)

Run `pinak --config-path` anywhere to print your exact path, or `/config`
inside the REPL (the path is shown above the table). Change the output
folder with `/setout <absolute_path>`.

---

## 🔒 Telemetry Tracker

The CLI contains an asynchronous background thread that pushes tracking events (`session_start`, `session_end`, `download`, `command`) to the **Pinak Receiver Server** to log activity. 

To configure a custom server URL or token, set the following environment variables:
```bash
$env:PINAK_PROXY_URL = "https://your-receiver-space.hf.space"
$env:PINAK_API_TOKEN = "your-api-token"
```
If the server is unreachable or offline, the CLI will fail-soft, allowing you to download files offline with zero interruptions.

---

## ⚖️ Legal disclaimer

Pinak CLI is a general-purpose downloading tool. You are solely responsible
for how you use it:

- Only download content you own, that is freely licensed, or that you have
  explicit permission to save.
- Downloading copyrighted material without authorization may violate
  copyright law in your country.
- Automated downloading may violate the Terms of Service of platforms such
  as YouTube or Instagram; your account could be restricted by those
  platforms. Use at your own risk.
- The authors provide this software "as is" (MIT License) and accept no
  liability for misuse.
