# Phase 04 — MCP transport and complete tool surface

Status: SDK and Inspector checks passed locally; desktop acceptance pending.

## Inputs

Frozen models/services/worker, installed SDK API, TOOL_CONTRACT.md, protocol
compatibility guidance. R1, R3–R7; scenarios 4, 11, 17, 22–25.

## Tasks

1. Register Pinak-MCP with package version and accurate tool descriptions.
2. Serve stdio with proper initialization/negotiation. Use the SDK's protocol
   implementation rather than a custom JSON-RPC parser.
3. Register every required tool, including start/status/stop, diagnostics, history,
   and media_info. Use shared services, not terminal command execution.
4. Return schema-valid structured results plus concise equivalent text. Map domain
   failures to tool errors and malformed protocol input to protocol errors.
5. Offload blocking operations, bound concurrency, propagate host EOF to owned
   worker shutdown, and keep progress optional for less capable clients.
6. Verify stdout remains protocol-only from interpreter startup through exit,
   including dependency logs, worker spawning, exceptions, and closed pipes.

## Outputs and commands

Runnable server/module, tool schemas and session integration tests. Run
`pytest tests/test_mcp_stdio.py tests/test_mcp_download_e2e.py`. Launch via the
installed absolute interpreter from an unrelated cwd. Connect using an actual
SDK client, then inspect with the SDK-supported MCP Inspector invocation verified
in phase 01 (the plan does not assume a specific version's CLI syntax).

## Acceptance

- Actual initialize/discovery/call/error/EOF exchange passes from a clean install.
- Concurrent status works while a real local download runs; file bytes, saved
  options, terminal job state, and history are correct after completion/restart.
- Missing optional host capabilities trigger documented polling/text fallbacks.
- No public listener, TUI, prompt, or binary provisioning occurs during serving.
- No test can claim phase complete using only direct Python function calls.

## Completion notes

2026-10-19: Official SDK callbacks expose fourteen typed tools. Actual SDK initialize/list/call/error/download/MP3/history/replay/overload/cancellation tests passed. Inspector 2.11.0 independently discovered 14 tools and called server_info. Later, an explicitly authorized temporary Cursor 3.23.12 Windows registration passed discovery, actual download, metadata, errors, progress, stop and disconnect/reconnect. Original client configuration was restored exactly; see CLIENT_ACCEPTANCE.md.

Remaining original gate checklist:

Pending: protocol/client/SDK versions, actual transcript evidence, tools list,
stdout audit, local-download fixture results, and commits.
