# Pinak: current operating guide

This guide describes the current source. [Historical design notes](https://github.com/Prince-1005/Pinak-CLI/blob/main/PINAK_DOCUMENTATION.md)
describe an earlier state. See [release readiness](https://github.com/Prince-1005/Pinak-CLI/blob/main/RELEASE_READINESS.md)
for the final audit fixes and verification.

## Installation and checks

Python 3.10 or newer is required. Install with `pipx install pinak-cli` or, from
this directory, `python -m pip install .`. For reproducible development, create an
isolated environment, install `requirements-lock.txt` using `--require-hashes`,
then install the project with `python -m pip install --no-deps -e .`.
`requirements-runtime-lock.txt` contains the runtime closure; the development
lock also includes test, lint, build, security and SBOM tools. Both contain
Python/platform markers and hashes. Regenerate them together when dependencies
change. A hash validates the selected package artifact; it does not establish
that its code is safe.

Run `pinak --version`, `pinak --help`, and `pinak --doctor`. Doctor tests storage,
dependencies and connectivity; a failed generic connectivity test is diagnostic
information and does not prevent downloading from a reachable source.

Media dependencies include Pillow, NumPy, SoundDevice and Mutagen. Rich and
prompt-toolkit provide terminal interfaces; platformdirs provides user paths;
Pydantic Settings validates preferences; filelock coordinates configuration
writes between processes. Optional OpenCV enables a native video window;
Tkinter is its fallback when available. Audio output requires an available
working device/driver. No output device is simulated during normal playback.

### Playback prerequisites

Downloading through the CLI does not require a graphical desktop or speakers.
Local audio playback needs a working output device; native `w` windows need a
graphical desktop and either Tkinter or OpenCV with GUI support.

On Debian/Ubuntu, for the distribution's Python interpreter:

```sh
sudo apt-get update
sudo apt-get install -y ffmpeg libportaudio2 python3-tk
```

If using a different Python build, install its matching Tkinter/Tcl/Tk support.
On Windows and macOS, SoundDevice's pip wheels include PortAudio; the selected
Python installation still needs Tkinter for the default native-window fallback.
As an alternative GUI backend, install `opencv-python` into the same environment:

```sh
python -m pip install opencv-python
# For a pipx-managed Pinak installation instead:
pipx inject pinak-cli opencv-python
```

`opencv-python-headless` does not provide a desktop GUI. On headless hosts,
download and CLI diagnostics remain usable, but native windows require an
available display. Container builds are intended for downloading; desktop display
and audio-device forwarding are not configured by the supplied Dockerfile.

Check imports without opening a window or playing sound:

```sh
python -c "import sounddevice; print(sounddevice.query_devices()); import tkinter; print(tkinter.TkVersion)"
pinak --doctor
```

### Contributor hooks

From the repository root, after installing the development lock and editable
package into an activated environment:

```sh
pre-commit install --config cli/.pre-commit-config.yaml
pre-commit run --config cli/.pre-commit-config.yaml mypy --all-files
```

Hook paths are relative to the repository root. Tool revisions match the locked
Ruff, Black and Mypy versions used by CI.

## Downloads and temporary options

```sh
pinak "https://example.com/video.mp4" --quality 720p -o downloads
pinak "https://example.com/video.mp4" --audio
pinak "https://example.com/video.mp4" --dry-run --json
pinak "https://example.com/video.mp4" --force
```

`--output`, `--log-file` and quality options affect that invocation. Use REPL
preferences commands to save defaults. `--json` reserves stdout for one JSON
document; progress goes to stderr. Unknown options fail before download work.
`--force` bypasses duplicate policy. A history record with missing output files
does not prevent downloading again.

Completion requires a nonempty final media artifact attributed to the request
and a successful extractor/postprocessor outcome. Partials, directories and
sidecars are excluded. This does not guarantee every byte of a container will
decode; external extractors, codecs and source availability remain dependencies.
Failed optional cover remuxing retains the original audio. Instagram carousel
results retain successful slides and report failed slides as partial failure.
Trimming uses the generic yt-dlp engine; Instagram image posts cannot be trimmed
as audio/video.

## Durable local queue

```sh
pinak queue add "https://example.com/video.mp4" --quality 720p -o downloads
pinak queue import links.txt
pinak queue list
pinak queue run
pinak queue retry --failed
```

`queue add` saves the current output, format, quality, subtitle, sorting, timeout,
retry, and duplicate settings with the job. Later preference changes do not
change that job. An equivalent unfinished job returns its existing ID; use
`--force` to intentionally add a separate download. The interactive `ask`
duplicate preference becomes `skip` for a saved job, because a foreground queue
run never stops to ask for input. `queue import` validates
every non-comment line before saving any jobs. Import links with
`/queue import links.txt` in the interactive shell, then use `/queue run`.

One foreground worker runs queued jobs in order and continues after failed
jobs. Closing the terminal stops processing. Ctrl+C returns the active job to
`queued` and retains partial files; the next `queue run` attempts continuation.
After an abrupt process exit, the next runner recovers stale `running` jobs.
Failed jobs require `queue retry <id>` or `queue retry --failed`. Job state is
stored locally in the history database even when history recording is disabled.
Two queue runners cannot operate on the same local database at once. A crash
after a media file is completed but before its result is recorded can cause a
repeat attempt; this is not an exactly-once system. No background service or
remote download server is started.

The interactive shell exposes the same queue through `/queue add <URL>`,
`/queue import <file>`, `/queue list`, `/queue run`, and
`/queue retry <id>` or `/queue retry --failed`. `/queue help` shows options.
`/queue add` and `/queue import` save jobs until a run starts. The live queue
display shows overall job counts, the active file, bytes, speed, ETA, and processing
status. Each finished job prints its result; failures include the reason.

### Inspecting and managing saved jobs

```text
/queue show 12
/queue cancel 12
/queue list --status cancelled
/queue remove 12 15 21
/queue clean --completed
```

Replace `12` with an ID from `/queue list`. `show` displays saved options, status,
attempts, output paths, and the full last error. The equivalent commands outside
Pinak's shell start with `pinak queue`.

`cancel` changes only a queued job to `cancelled`; cancelled jobs remain visible
and are never claimed by the worker or included in `retry --failed`. To download
one later, add the URL again. Cancelling an already cancelled job is harmless.

`remove` deletes one or more inactive job records in one transaction. If any ID
is unknown or running, none are removed. Running jobs cannot be cancelled or
removed: press Ctrl+C in their runner first. Claims and management changes use
SQLite transactions so a waiting job cannot start after its cancellation or
removal commits.

`clean --completed` deletes only `succeeded` and `skipped` records. It preserves
queued, running, failed, and cancelled records. All three management actions keep
downloaded and partial files and the separate download history; cleanup does not
delete media from disk. Unknown/nonpositive IDs produce an error without changing
other jobs. The `--completed` flag is required for cleanup. Each queue attempt
also updates local download history with its result, files, and saved options
when history recording is enabled. Removing or cleaning queue records keeps
those history entries.

`/clear` (or `clear`) clears the terminal screen and scrollback (including the shell output from
launching Pinak), then redraws the Pinak ASCII logo and
control panel with current settings. It preserves jobs, history, preferences, and
downloaded files and does not repeat first-run initialization.

## Local Library

Successful direct and queued downloads are cataloged locally, independent of
download-history recording. To catalog existing files, run
`pinak library scan <folder>`; `pinak library scan --all` refreshes only folders
previously chosen by you. Use `pinak library list`, `show <id>`, and
`search <text>` to find items. The same commands work inside the shell as
`/library ...`. `pinak library --help` lists every subcommand.

`tag add/remove`, `collection create/list/add/remove/move/show/play`, and
`bookmark add/list/open/remove` organize media without moving or copying it.
An ordered collection plays through the existing local player. Audio/video
progress is saved during playback and on pause/exit; `play <id> --from-start`
overrides it. If a file moves, `relink <id> <new-path>` preserves its metadata.
`forget <id>` removes the catalog record but never deletes the media file.

The Library uses a separate `library.db` in Pinak's user-data directory. Its
search falls back to ordinary SQLite matching if FTS5 is unavailable. It does
not scan in the background or follow symbolic links. Catalog errors are logged
without changing a successful download into a failed one. The
[Library guide](../Website/src/content/docs/docs/library.md) has examples.

## Preferences and local storage

Run `pinak --config-path` for the actual config location and `/config` in the
REPL to display preferences. Names include `output_dir`,
`quality`, `audio_quality`, `video_format`, `audio_format`, `retry_count`,
`connect_timeout`, `read_timeout`, `ffmpeg_path`, `ffprobe_path`, `history_enabled`,
`log_file`, `embed_subs`, `auto_sort`, `duplicate_action`, `username`, `greeting`,
and `last_update_check`. The old `retries`/`timeout` keys migrate to
`retry_count`/`read_timeout`; unknown keys are ignored.

Defaults include output `downloads` relative to the invocation directory,
quality `best`, MP4 video, MP3 audio at 192 kbps, 3 retries, a 10-second connect
timeout and a 30-second read timeout. Explicit `PINAK_<SETTING>` environment
variables override saved values for the process. Explicit invocation options
take precedence. Saving unrelated preferences does not persist environment
overrides. A `.env` file is also read by Pydantic Settings; process environment
takes precedence over that file. Invalid settings produce diagnostics without
preventing `--help` or `--version` from loading.

Config uses `platformdirs.user_config_dir("pinak-cli", "pinak")/config.json`.
SQLite history uses `user_data_dir("pinak-cli", "pinak")/history.db`.
REPL command history is `~/.pinak_cli_history`. IPC descriptors use
`user_cache_dir("pinak-cli", "pinak")/ipc/`. Logs are written only at the
configured/requested path. Downloaded media is separate from those application
data locations. SQLite locks and permissions are reported rather than treated
as corruption; confirmed corrupt databases are preserved under unique names.

Configuration changes use a cross-process lock and a unique atomic replacement;
unrelated changes from another process are merged. A valid `.bak` can recover a
damaged primary. Disk/permission errors are reported; deletion commands only
claim success after the storage transaction succeeds.

## Local media player and controls

Use `/media <local path>`, `/play <local path>`, or `/view <local path>` in the
REPL, or `pinak media <local path>`. The player accepts local files/directories;
download remote URLs first. Interactive playback needs a terminal. Use
`--inline` for the current terminal, `--standalone` for another console, or
`--window` for an additional native media window. A failed standalone launch
falls back to the current terminal. The macOS Terminal tab may remain open when
playback ends; the launcher waits for the command and checks its recorded exit
status.

The file browser wraps the selected filename in the list and Media Inspector.
Use left/right arrows to page through names too long to fit vertically; selecting
another item resets the name page. The inspector shows audio/video length as
`M:SS` or `H:MM:SS`. Duration loads in the background and is cached until the
file changes; unreadable or unsupported duration is shown as `Unavailable`.

Space pauses/resumes, arrows seek/change volume, Ctrl+M mutes, `n`/`p` navigate,
`r` changes repeat mode, `s` toggles shuffle, `m` changes renderer, `w` toggles a native window and
Esc/`x` closes media. Picture controls route to the viewer once. Native-window
fullscreen belongs to the native window; the deprecated PictureViewer
fullscreen method is retained for API compatibility. Directory scans and image
decoding enforce resource budgets, and small terminals request a resize.

For audio and video, shuffle preserves the current track and shows `Shuf: ON/OFF`
in the header. With repeat ALL (ON), each next track is randomly selected from the
full playlist, including previously played tracks. With repeat OFF, it selects
only tracks not yet played in this session and pauses after exhaustion, including
for music. With repeat SOLO, the current track repeats on completion. Manual
`n`/`p` navigation can change tracks in SOLO; `p` follows playback history while
shuffle is on. Toggling shuffle/repeat preserves played history; reopen the
collection for a fresh session. Shuffle OFF restores normal sequential behavior.

An open GPU/native window stays open across automatic track changes, repeat,
shuffle, and manual next/previous navigation. The same window displays the next
video or song artwork and updates its title while keeping its size and fullscreen
state. `w` still closes it explicitly; exiting playback releases it.

Playback starts without an assessment prompt when measured device resources are
healthy. It asks for consent when unplugged battery is at or below 15%, free RAM
is below the media's estimated playback budget (at least 512 MB), or a readable
temperature sensor reports 85°C or more. The card lists each reason. A critical
session launched without an interactive terminal stops with a diagnostic because
it cannot collect consent. Unavailable temperature sensors are treated as unknown.
The `w` window opens to fit the usable display and scales video with the correct
aspect ratio; `f` toggles fullscreen from that window.

The first video frame can appear while the audio device opens. Optional subtitle
extraction runs in one background worker. Terminal video is decoded to the
visible renderer budget; native-window output retains its selected resolution.
Normal frame lag drops stale frames; large recovery seeks are rate-limited.

Hardware decode failures retry software once. Audio output prefers continuous SoundDevice output with low latency (the
matching shared WASAPI endpoint on Windows), streams bounded 20 ms PCM blocks and applies volume/mute to that session. Driver errors try alternatives;
audio-only playback reports failure if no driver works. Video can continue with
a monotonic clock when audio output fails or ends before its video stream.
The winsound/afplay compatibility paths use short WAV blocks; those fallbacks
may have gaps and are less suitable for continuous high-fidelity playback than
SoundDevice/ffplay. Unknown-duration playback ends on decoder/output EOF.

Local IPC requires a random per-session token. Built-in `pinak ctl` and `/ctl`
discover the actual port and credentials in the current user's cache. When
several sessions exist, select one with `PINAK_IPC_PORT`; discovery refuses an
ambiguous session. Custom clients specifying a port must also supply its token.
Keep descriptor files private: POSIX permissions are restricted; on Windows the
user profile/cache ACL supplies the account boundary. Processes running as the
same account can read those credentials. Controls queue to the session thread,
and stale queued controls are cancelled on transitions.

## Executables and release artifacts

Configure `ffmpeg_path`/`ffprobe_path` or install binaries in an absolute trusted
PATH directory. Implicit current-directory and relative-PATH discovery is
excluded. The static-ffmpeg fallback downloads upstream binaries; Pinak does not
independently attest their provenance or hashes. Use administrator-provisioned,
verified executables where that assurance is required.

From `cli/`, build with `python -m build --outdir release-dist/2.2.0`, then
`python tools/smoke_wheel.py release-dist/2.2.0`. The smoke check installs the wheel
outside the source tree and exercises imports, version and JSON dry-run. Rebuild
after source changes and use a fresh version-specific directory for each release.
Old files in `cli/dist/` are historical 1.0.0 artifacts.

Release notes are maintained in `cli/CHANGELOG.md`; the root changelog links to
them. Automatic release creation is disabled: `release.yml` has no push trigger,
release-writing action, or write permissions. It only reports this policy when
run manually. The retained Release Please configuration is inactive.

Create GitHub releases manually. Publishing a GitHub release or manually running
`publish.yml` first checks the requested version against `pyproject.toml`,
`pinak.__version__`, and the release manifest. Release tags must be `v<VERSION>`
(for example `v2.2.0`). Manual dispatch requires the exact version string in its
`version` input (for example `2.2.0`). A mismatch stops before building or upload.
The workflow then invokes the reusable quality/security workflow for that revision,
builds fresh artifacts, verifies a clean wheel installation, and then uploads to
PyPI using trusted publishing. The trusted publisher must match repository
`Prince-1005/Pinak-CLI` and workflow filename `publish.yml`. Repository-side
workflow changes take effect after they are committed and pushed.

The reusable secret scan uses a checksum-verified pinned Gitleaks CLI and default
detection rules on all caller events. A synthetic canary must be detected before
Git history is scanned. Linux CI installs PortAudio/Tk prerequisites and verifies
a clean wheel installation plus the Docker downloader entry points.

The Windows uninstall helper schedules package removal and only then removes
selected application data on success. It does not remove downloaded media or
arbitrary external log files. A scheduled helper is reported as pending work,
not as proof that deletion already completed.
## Optional local MCP adapter

Source installation: `python -m pip install -e ".[mcp]"` from cli/. The executable
is `pinak-mcp`; module launch is `python -m pinak.mcp_server`. `configure` prints
generic stdio launch fields, `doctor` performs local readiness checks, `serve`
starts the protocol, and `prepare-update` creates explicit local state backups.
Ordinary CLI installations do not import or require the optional SDK.

MCP and CLI share the same per-user queue/history DB and runner FileLock.
`PINAK_DATA_DIR` explicitly overrides the storage directory for both processes;
it is a trusted local launch setting, not an MCP tool argument. Policy comes from
`PINAK_MCP_CONFIG` or the platform user config directory's mcp.json. With no
policy file, downloads use ~/Downloads/Pinak. Output/read roots restrict download
destinations and returned file information; record management uses the shared
user queue. This adapter is not an operating-system sandbox.

The worker belongs to one stdio session and stops on disconnect. Partial files
remain; stale running rows are recovered only by the next exclusively locked
runner. A new host does not automatically resume downloads. Mutation receipts
default to seven days; use identical request keys/arguments to reconcile lost
responses. They do not promise exactly-once download execution.

No binary provisioning, package updates, network listener, desktop player or
external AI account setup happens during initialization. Download sources still
require outbound network access. See ../MCP(Local)/USAGE.md and IMPLEMENTATION_STATUS.md
for setup, supported behavior, recovery and outstanding release acceptance.
