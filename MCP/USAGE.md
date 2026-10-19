# Connect your AI application to Pinak-MCP

Pinak-MCP runs locally through standard MCP **stdio**. Choose an AI application
that can launch a local MCP process. Its AI provider/model can vary; Pinak does
not require a provider API key. Cloud-only clients that accept only remote URLs
cannot connect directly. No hosted service, public URL, or listening port is used.

## Install the current source

These changes are not yet a published PyPI release. From the repository's `cli`
directory create a dedicated environment:

```powershell
python -m venv .venv-mcp
.venv-mcp/Scripts/python.exe -m pip install --upgrade pip
.venv-mcp/Scripts/python.exe -m pip install -e ".[mcp]"
.venv-mcp/Scripts/python.exe -m pinak.mcp_server doctor --json
.venv-mcp/Scripts/python.exe -m pinak.mcp_server configure
```

On macOS/Linux replace `.venv-mcp/Scripts/python.exe` with
`.venv-mcp/bin/python`. Python 3.10+ is required; the extra pins the tested official
MCP SDK 2.3.0. The normal CLI needs no MCP SDK. `pinak-mcp` is also installed as
an executable in that environment. After publication the intended package is
`pinak-cli[mcp]`; do not assume the current PyPI release includes it.

Doctor checks SDK, output permissions, database compatibility and bounded FFmpeg /
FFprobe version checks. Conversion/merging needs usable FFmpeg; metadata benefits
from FFprobe. MCP never silently downloads those binaries. Install/repair them
explicitly using the regular Pinak installation instructions before retrying.

## Register in your client

Run `configure` with the **installed environment's Python**. It prints these fields:

- Transport: `stdio`.
- Command: the absolute path to that Python executable.
- Arguments: `-m`, `pinak.mcp_server`, `serve`, `--transport`, `stdio` as separate items.
- Environment: `PINAK_MCP_CONFIG` with the printed absolute policy filename.

Enter those fields in the client's local MCP settings or translate them into its
documented config format. No shell activation script is needed. A client that
accepts only HTTP/SSE URLs is incompatible with this version. Restart/reload the
host if required by that application, then discover the fourteen Pinak tools.

For a host using Claude Desktop's mcpServers JSON format, preview explicitly with
`pinak-mcp configure --client claude-desktop`. `--apply` merges Pinak's entry with
a backup and atomic replacement; other server entries remain intact. `--target`
can point at a disposable config for review. Generic stdio mode never edits files.
This format example is not a certification of every client/version.

## Decide where files may go

With no policy file, downloads use your user's `Downloads/Pinak` folder. To change
it, create the printed `PINAK_MCP_CONFIG` file using the version 1 policy template
in examples/, replacing placeholders with absolute paths. Only output_roots are
valid download destinations; read_roots additionally allow metadata inspection.
Paths are resolved before containment checks, including symlinks/junctions.
Relative download paths use the configured default directory, never the host cwd.

CLI and MCP use the same existing per-user database. `PINAK_DATA_DIR` can explicitly
select portable/test storage; set the same value for both processes to share it.
It is a trusted launch setting, never an AI tool argument. Existing queue records
can be managed from either adapter. This is not an OS sandbox: the downloader has
outbound network access, and another local program can change files or paths.

## Ask the AI to work

Examples:

- “Queue this URL as audio in my approved download folder, then start the queue.”
- “Show the options and error for job 12.”
- “Show the status of that run. When it finishes, list its saved files.”
- “Stop this session's run and keep partial files so I can resume later.”
- “Retry failed jobs, then start another run.”
- “Remove job 12 from the queue; keep its downloaded files.”

`queue_add` saves a job; `queue_start` executes a bounded snapshot, default 100
jobs and maximum 1,000. Poll `queue_run_status`; acceptance is not download success.
Jobs added after the snapshot wait for the next run. Only one CLI/MCP runner can
hold the shared lock. A different session cannot stop a run it does not own.

Mutations require request_key. Reuse the same key and identical arguments after a
lost response to reconcile the result; use a new key for a new intentional action.
Receipts persist seven days by default. They do not guarantee exactly-once network
downloads: a crash between writing media and committing the result can cause a
later attempt. File completion and history are committed through the core queue.

## Disconnect, recover, update

Closing the host/stdio pipe requests a stop. The worker preserves partial files
and requeues interrupted work cooperatively; a hung child is terminated after
the configured grace period. If forcibly killed before recording its outcome,
the next runner recovers stale running rows **after taking the exclusive lock**.
Downloads do not continue unattended after the MCP adapter dies.

Use the ordinary CLI fallback: `pinak queue list`, `pinak queue show 12`,
`pinak queue run`, `pinak queue retry --help`. Repair the environment rather than
deleting the database. Confirmed corruption is quarantined and disclosed; busy
storage is reported as busy, never reset. Keep the quarantined file for recovery.

Before upgrades: stop runs, close hosts, run `pinak-mcp prepare-update`, save its
backup paths, then upgrade explicitly with your original installation method.
Run doctor, inspect jobs/history, reconnect and resume explicitly. Read
[update/rollback limits](SETUP_AND_UPDATES.md) before restoring a backup.

Logs rotate locally (512 KiB, two backups). Returned URLs redact credentials and
query strings; text strips terminal controls. Your AI host can still send prompts
and returned metadata to its provider. Pinak-MCP sends no downloaded media bytes
to the model by default.

## Verification status

The official SDK client tests initialize, discover all tools and execute actual
local downloads, audio conversion, history, replay and process cleanup. See
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for exact evidence. Real
desktop-host and cross-platform release acceptance must be recorded separately;
protocol interoperability does not mean every AI application is certified.
