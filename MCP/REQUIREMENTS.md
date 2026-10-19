# Intent, scope, and acceptance requirements

## User intent

Expose Pinak to compatible AI applications under the name Pinak-MCP. Users should
manage and execute downloads through natural language using their own installation.
The maintainer must not operate a server that receives everyone's media requests.
CLI users must keep their existing workflow and saved data.

## Existing authoritative inputs

- `cli/pinak/engine.py`: validated immutable DownloadRequest, structured events/results,
  and reusable download execution. Capture options at enqueue time.
- `cli/pinak/queue.py`: local SQLite queue, FIFO claims, exclusive worker FileLock,
  cancellation of waiting jobs, atomic multi-ID removal, retry, crash recovery.
- `cli/pinak/history.py`: local history; queue completion and history currently commit
  together when history recording is enabled.
- `cli/pinak/commands/queue.py`: existing CLI adapter and slash-command semantics.
- `cli/pinak/config.py`, `cli/pinak/ffmpeg_setup.py`, `cli/pinak/subproc.py`:
  settings, binary resolution, and trusted subprocess handling.
- `cli/pyproject.toml`: Python >=3.10, package discovery for `pinak*`, optional extras.
- `cli/OPERATIONS.md`, tests, and current workflows: maintained behavior and gates.

Historical design notes are not authoritative. Re-read current files before editing.

## Required functionality

- R1: local stdio MCP server, launched by a supported desktop client, with a stable
  display identity and no network listener or remote hosting dependency.
- R2: optional installation; ordinary Pinak imports and commands work without the SDK.
- R3: typed queue add/list/show/retry/cancel/remove-many/clean-completed tools.
- R4: start a bounded local download run and inspect/stop it without blocking the
  MCP event loop for the entire download. Status remains available concurrently.
- R5: CLI and MCP share one user's queue/history. Existing lock remains the final
  authority against simultaneous CLI/MCP runners.
- R6: preserve queued options, files, history preferences, and atomic removal semantics.
- R7: paginated history and local media information; redact secrets by default.
- R8: clear setup, diagnostics, supported client examples, and CLI fallback instructions.
- R9: safe updates, migration compatibility checks, and documented rollback limits.
- R10: OS matrix tests, real stdio integration, failure injection, real local downloads,
  clean wheel installation, and release evidence before calling the product ready.

## Explicit boundaries

No accounts, hosted download server, public HTTP transport, arbitrary shell tools,
arbitrary file deletion, credential export, automatic package upgrades inside a
tool call, forced AI-provider API key, or automatic TUI/GPU window opening.
Future playback control is separate scope. Do not expose all configuration values
or return downloaded media bytes to a model by default.

Only local-process-capable MCP clients are initially supported. A cloud-only host
that cannot launch local processes cannot use this stdio design directly. Do not
silently introduce a remote bridge to make such a client appear supported.

## Permissions and limits

Use a user-owned MCP configuration with approved output roots and optional read
roots. Resolve paths before checking containment, including symlink/junction
escapes; relative output paths resolve against the configured default root, never
the AI host's working directory. Default to a dedicated user Downloads/Pinak
folder; allow users to add roots intentionally. Host workspace roots are useful
hints, not automatic permission grants.

Do not grant arbitrary yt-dlp flags, executable paths, database paths, or environment
variables through tools. Reuse core URL/settings validation, define explicit
argument/result limits, and report policy denials without silently changing paths.
Document that the existing downloader has outbound network access; this adapter
is not an OS sandbox. Optional domain policies must also account for redirects.

## Supported failure behavior

Failure is an observable product state, not something to conceal. Retry only
known transient operations with limits. Preserve partial files. Never claim exact
once download execution: a crash after writing a file but before committing a
result can require another attempt. Cancellation is distinct from MCP request
cancellation and from deleting a saved record.
