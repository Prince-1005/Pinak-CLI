# Pinak-MCP

Connect an AI application to Pinak's local download engine and durable queue.
Pinak-MCP uses standard MCP **stdio**: the AI application launches a local Python
process. No hosted download service, public endpoint or user account is required.
The AI host may still send prompts and returned metadata to its provider.

## Get started

These MCP changes are available from repository source; do not assume the
published PyPI package includes them yet. Python 3.10+ and a client that supports
local stdio MCP servers are required.

```sh
git clone https://github.com/Prince-1005/Pinak-CLI.git
cd Pinak-CLI/cli
python -m venv .venv-mcp
```

On Windows:

```powershell
.venv-mcp/Scripts/python.exe -m pip install --upgrade pip
.venv-mcp/Scripts/python.exe -m pip install -e ".[mcp]"
.venv-mcp/Scripts/python.exe -m pinak.mcp_server doctor --json
.venv-mcp/Scripts/python.exe -m pinak.mcp_server configure
```

On macOS/Linux, replace `.venv-mcp/Scripts/python.exe` with
`.venv-mcp/bin/python`. Install FFmpeg/FFprobe explicitly when conversion, merging
or metadata requires them; the MCP server does not provision these binaries.

Enter the generated command, arguments and environment in your AI application's
local MCP settings, then reload it. Ask: “Queue this media URL, start the queue,
and show me its download status.” Adding a job alone does not start downloading.
Clients that accept only remote HTTP/SSE URLs cannot connect directly.

## Documentation

- [Installation, client setup and everyday usage](USAGE.md)
- [Policy and client configuration examples](examples/README.md)
- [Tool contract and errors](TOOL_CONTRACT.md)
- [Architecture and worker lifecycle](ARCHITECTURE.md)
- [Failure handling and recovery](FAILURE_RECOVERY.md)
- [Updates, compatibility and maintenance](MAINTENANCE.md)
- [Verification commands and release checks](VERIFICATION.md)

Runtime code is in `cli/pinak/mcp_server/`; the SDK is an optional dependency of
`pinak-cli[mcp]`. Ordinary CLI users do not need to install it. CLI and MCP share
the user's existing local queue/history. Downloaded media stays on the user's
device and is not included in tool responses.

## Verified scope

Windows Cursor 3.23.12 discovered all fourteen tools and passed actual local
download, metadata, history, error, progress, stop and disconnect/reconnect checks.
The temporary test registration was removed and original configuration restored.
SDK client and Inspector 2.11.0 interoperability also passed.

[Source CI at 41dd4e8](https://github.com/Prince-1005/Pinak-CLI/actions/runs/39261336830)
passed all eighteen jobs, including Windows/macOS/Linux on Python 3.10–3.14,
installed-wheel downloads, upgrade/downgrade, container and security checks.
Local regression: 642 tests passed, 77.42% coverage. One native metadata timing
measured p95 1.024s, slightly above the provisional one-second target.

macOS/Linux desktop-host acceptance, hostile-media memory checks, suspend/resume,
long-duration resource testing and a first published-version upgrade remain open.
This is not universal client certification or an exactly-once download guarantee.

Implementation planning and superseded progress reports are ignored local files.
They are unnecessary for installation, building or running Pinak-MCP.
