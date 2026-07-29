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
├── ffmpeg.exe                  # Local FFmpeg binary (packaged)
└── ffprobe.exe                 # Local FFprobe binary (packaged)
```

---

## 🛠️ Installation & Setup

### Requirements
*   Python 3.8 or higher.
*   `ffmpeg.exe` and `ffprobe.exe` (automatically provided inside this directory).

### Step 1: Install in Editable Mode
Open your terminal at the `cli/` directory and run:

```bash
pip install -e .
```

This registers the CLI globally as the terminal command `pinak`. Because it is installed in *editable mode*, any changes you make to the code inside the package take effect immediately.

### Step 2: Test Command
Open a new terminal shell anywhere on your system and launch the interactive console:

```bash
pinak
```

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

Pinak CLI saves user-specific configuration (like download directory, quality, retry counts) in a standard configuration folder.

- **Config Path**: `~/.config/pinak-cli/config.json` (via `platformdirs`)
- **SQLite DB Path**: `~/.local/share/pinak-cli/history.db`
- **Output Directory**: The default downloads are saved to a directory named `downloads/` inside your user-profile, or inside this package folder. You can customize this by running `/setout <absolute_path>`.

---

## 🔒 Telemetry Tracker

The CLI contains an asynchronous background thread that pushes tracking events (`session_start`, `session_end`, `download`, `command`) to the **Pinak Receiver Server** to log activity. 

To configure a custom server URL or token, set the following environment variables:
```bash
$env:PINAK_PROXY_URL = "https://your-receiver-space.hf.space"
$env:PINAK_API_TOKEN = "your-api-token"
```
If the server is unreachable or offline, the CLI will fail-soft, allowing you to download files offline with zero interruptions.
