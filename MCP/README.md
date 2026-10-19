# Pinak-MCP implementation plan

Status: **implemented in source; release acceptance in progress.**

Prepared 2026-10-19 against the existing Pinak engine and durable queue.

## Product decision

The name **Pinak-MCP** is suitable. The proposed executable is `pinak-mcp`,
the import namespace is `pinak.mcp_server`, and the client configuration key is
`pinak`. Keep this work in the current repository. Initially ship it as the
optional `mcp` extra of `pinak-cli`, sharing one release with its core engine.
These names do not assert ownership or availability of a separate PyPI package
or MCP Registry listing; check those separately if separate publication is wanted.

The runtime lives in `cli/pinak/mcp_server/`. Start with the
[connection and usage guide](USAGE.md); see the
[status ledger](IMPLEMENTATION_STATUS.md) for verified checks and remaining gates.
Dependency/schema updates and installer rehearsal are documented in
[maintenance](MAINTENANCE.md).
No live AI client has been registered and no package release has been published.
The package version remains unchanged.

## Intended experience

1. Install the optional extra using a documented, isolated Python environment.
2. Generate and inspect a client launch configuration; apply it only when requested.
3. Restart a compatible local MCP host and verify Pinak's tools are discoverable.
4. Ask the AI to queue media, start a local run, inspect results, or manage jobs.
5. Read the same queue and download history through Pinak CLI and MCP.
6. Close/reopen the host without losing saved jobs. Interrupted attempts remain
   resumable where the source/download engine supports partial-file continuation.

All execution and storage belong to the user's machine. Stdio transport requires
no hosted backend, public endpoint, account database, or inbound network port.
Downloads still require connections to their source websites. A cloud-backed AI
host may process prompts and returned metadata remotely; local transport does not
make that host offline.

## Read in this order

1. [GPT implementation guide](GPT_IMPLEMENTATION_GUIDE.md)
2. [Requirements and scope](REQUIREMENTS.md)
3. [Architecture and worker lifecycle](ARCHITECTURE.md)
4. [Tool contract](TOOL_CONTRACT.md)
5. [Failures and recovery](FAILURE_RECOVERY.md)
6. [Installation, client configuration, and updates](SETUP_AND_UPDATES.md)
7. [Verification and release gates](VERIFICATION.md)
8. [Implementation status](IMPLEMENTATION_STATUS.md)

## Sequential delivery phases

- [01 — Compatibility and foundation](planning/01-foundation.md)
- [02 — Contracts and shared services](planning/02-contracts.md)
- [03 — Durable worker control](planning/03-worker.md)
- [04 — MCP transport and tools](planning/04-mcp-server.md)
- [05 — Installation and client setup](planning/05-client-setup.md)
- [06 — Failure recovery and operational hardening](planning/06-recovery.md)
- [07 — Updates and compatibility](planning/07-updates.md)
- [08 — End-to-end verification and release](planning/08-release.md)

Phases are checkpoints, not separately advertised complete products. The first
public release must include all eight, including MCP-initiated download runs.
Queue management alone does not satisfy this plan.

## Reliability promise

Do not promise software with zero possible bugs or universal client compatibility.
Deliver tested behavior, bounded operations, visible failure reasons, preserved
data, and supported recovery steps. A failed download must never be presented as
successful merely because an MCP request returned successfully.

## Official references

Recheck these at implementation time; SDK APIs and host formats can change.

- [Python SDK repository](https://github.com/modelcontextprotocol/python-sdk)
- [SDK running and transports](https://py.sdk.modelcontextprotocol.io/run/)
- [MCP tools specification](https://modelcontextprotocol.io/specification/latest/server/tools)
- [MCP compatibility specification](https://modelcontextprotocol.io/specification/latest/basic/lifecycle)
- [Official server and desktop configuration tutorial](https://modelcontextprotocol.io/docs/develop/build-server)

The SDK guidance inspected for this plan uses `MCPServer` and local stdio.
Verify the installed release's actual API and supported Python versions before
choosing bounds; do not copy an older FastMCP example or an unpinned main branch.
