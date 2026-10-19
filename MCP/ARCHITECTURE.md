# Local architecture and lifecycle decisions

## Package layout to implement

Keep human/GPT planning and setup examples in root `MCP/`. Runtime code belongs
under `cli/pinak/mcp_server/` so the existing wheel discovery includes it.

Proposed modules: `__main__.py` for launch/diagnostic/configuration subcommands,
`server.py` for SDK registration, `models.py` for contracts, `tools.py` for adapters,
`policy.py` for roots/limits/redaction, `worker.py` for the child entry point,
`worker_controller.py` for ownership/lifecycle, `store.py` for additive MCP records,
and `setup.py` for client configuration generation. Avoid importing the SDK from
core engine, queue, or regular CLI startup.

Use one distribution, `pinak-cli[mcp]`, and one version source. Add a `pinak-mcp`
console entry point. Do not create a second database or independent downloader.

## Process responsibilities

The AI host launches the MCP adapter through an absolute executable/interpreter
path. The adapter handles protocol traffic and short metadata operations. A
dedicated local child process runs downloads through the existing queue engine.
It is not a system service, does not start at login, and opens no port.

Stdio stdout contains protocol messages only. Diagnostics go to stderr. Worker
stdout/stderr must be routed away from protocol stdout, bounded, and redacted.
Never call the interactive `pinak` REPL from an MCP tool. Do not rely only on an
SDK's stdout redirection to compensate for banner-producing imports.

## Queue and run semantics

- `queue_add` stores options and returns promptly; it does not download implicitly.
- `queue_start` snapshots the requested eligible job IDs, or all eligible IDs at
  request time, and starts a bounded run. Jobs added later wait for another run.
- Return `run_id` and state after a bounded startup handshake, not after download
  completion. A planned target is <=2 seconds on an already provisioned system;
  measure it, and make slow startup visible rather than falsely reporting running.
- Use the existing queue FileLock in the actual worker. A PID or run record never
  substitutes for it. An active CLI runner produces RUNNER_BUSY, without being stopped.
- Runs have durable identity and states: starting, running, stopping, completed,
  failed, interrupted. Store owner/session identity, process start identity, target
  snapshot, timestamps, heartbeat, terminal result, and a redacted last error.
- Job states remain the core states. `queue_cancel` cancels only waiting jobs;
  `queue_stop` requests a run stop, not record deletion. Do not label a queued
  cancellation as an active transfer abort.

## Shutdown and crash recovery

Choose a supervised lifetime for v1: host EOF or adapter shutdown requests stop of
only that adapter's owned child. Stop new claims, cooperatively interrupt the
active operation, preserve partial files, and requeue interrupted work. Explicit
restart via MCP or `pinak queue run` can resume it. Do not require MCP to remain
available for CLI recovery.

Add cooperative cancellation hooks to engine/download loops and retry waits;
an asyncio cancellation alone cannot stop a blocking downloader thread. Propagate
the stop request into Instagram workers and FFmpeg subprocess ownership.

Implement a private parent-liveness channel/watchdog so a killed parent cannot
leave an unmanaged worker claiming jobs indefinitely. Provisional defaults:
2-second parent heartbeat, 30-second orphan threshold, 10-second graceful stop.
Make these testable and configurable within safe bounds.

If grace expires, terminate only the verified owned process tree. Use supported
Windows process ownership/group/Job Object handling and POSIX process groups;
never kill all Python/FFmpeg processes or trust a reused PID. Wait for actual
exit and lock release before allowing recovery. A leftover running row is
recovered by the next exclusive runner, never by an observer racing a live worker.

Keep blocking work off the protocol event loop. Status/list tools must stay
responsive while a run or shutdown is in progress. Optional MCP progress/task
extensions may enhance the experience; start/status/stop must work without them.

## Storage and replay safety

Use additive versioned tables in the current local database for run state and
mutation request receipts. The current queue schema uses PRAGMA user_version=1;
do not invent a conflicting independent schema counter. Coordinate an overall
schema migration and minimum compatible core version.

For mutating tools, accept a request_key. Persist tool name, key, canonical argument
hash, and committed result. Same key + same arguments returns the recorded result;
same key + different arguments returns IDEMPOTENCY_CONFLICT. Scope keys to the
local installation/tool, not a volatile host session. Record queue mutation and
receipt atomically; spawning a process needs an explicit starting-state recovery
handshake because SQLite and process creation cannot form one transaction.

Retain receipts for a documented window (initial target 7 days). Expose the replay
window; do not promise unlimited deduplication. Existing fingerprint-based queue
dedupe stays useful but does not replace mutation receipts, especially with force.

Persist bounded job/run progress snapshots for polling. Existing DownloadEvent
data is not durably stored byte progress today. Throttle writes; unknown total,
processing, failed, and stale-heartbeat states must remain distinct from 100%.
