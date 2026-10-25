# Pinak-MCP Local

Connect an AI application to Pinak's local download engine and durable queue.
Pinak-MCP uses standard MCP **stdio**: the AI application launches a local Python
process. No hosted download service, public endpoint or user account is required.
The AI host may still send prompts and returned metadata to its provider.

## Get started without downloading the repository

Python 3.11+ and an AI application supporting local stdio MCP are required.

1. Open [CI builds](https://github.com/Prince-1005/Pinak-CLI/actions/workflows/ci.yml).
2. Select a successful **main-branch push** run that contains the installer artifact.
3. Under **Artifacts**, download **pinak-mcp-install** and extract the ZIP.
4. Follow its **INSTALL.md** to install the included wheel with the `[mcp]` extra
   in a dedicated Python environment, run doctor and generate client settings.
5. Enter those launch settings in your AI application and reload it.

The bundle contains one application wheel, INSTALL.md, BUILD-INFO.json and
SHA256SUMS. It excludes the repository, website/media, Git history, tests and
planning. Pinak's shared CLI/engine is included because MCP uses it. Pip separately
fetches runtime dependencies; Git and Node.js are unnecessary.

GitHub requires sign-in to download Actions artifacts. Bundles are retained for
90 days; use a newer successful main-branch build if one expires. Older builds
before this distribution workflow was added do not contain the artifact. Download
only from this repository's successful main-branch push runs, not pull requests.
This is a development build of the source revision recorded in BUILD-INFO.json,
not a new PyPI release. Do not assume the published PyPI package includes MCP yet.

Ask: “Queue this media URL, start the queue, and show me its download status.”
Adding a job alone does not start downloading. Install FFmpeg/FFprobe explicitly
when conversion, merging or metadata needs them. Remote-URL-only clients cannot
connect directly. See [complete installation steps](USAGE.md).

## Documentation

For an optional remote instance on your own VPS or Render account, see
[Pinak-MCP Cloud](<../MCP(cloud)/README.md>). Its cloud deployment acceptance
is recorded separately; this page describes the local stdio edition.

- [Installation, client setup and everyday usage](USAGE.md)
- [Policy and client configuration examples](examples/README.md)
- [Tool contract and errors](TOOL_CONTRACT.md)
- [Architecture and worker lifecycle](ARCHITECTURE.md)
- [Failure handling and recovery](FAILURE_RECOVERY.md)
- [Updates, compatibility and maintenance](MAINTENANCE.md)
- [Verification commands and release checks](VERIFICATION.md)

Runtime code is in `cli/pinak/mcp_server/`; the SDK is an optional dependency of
`pinak-cli[mcp]`. Ordinary CLI users do not need to install it. CLI and MCP share
the user's existing local queue, history, and Library. Downloaded media stays on the user's
device and is not included in tool responses.

## Verified scope

The earlier Windows Cursor 3.23.12 check discovered the original fourteen tools and passed actual local
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
