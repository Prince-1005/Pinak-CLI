# Phase 03 — Durable supervised download worker

Status: planned. Dependencies: phases 01–02 verified.

## Inputs

ARCHITECTURE.md, existing run_queue/FileLock/recovery, DownloadEvent, downloader
retry loops, FFmpeg and Instagram child behavior. R4–R6; scenarios 10–22.

## Tasks

1. Implement local worker entry point and controller, immutable selected-job
   snapshot, persistent run identity, and bounded startup acknowledgment.
2. Start it with the correct interpreter and fixed argument vector, no shell.
   Route all worker output away from MCP protocol stdout.
3. Add cooperative stop checks to claiming, transfer/postprocessing, retry waits,
   and parallel Instagram work. Return interrupted state consistently.
4. Implement run polling and coalesced durable progress; listener errors must not
   abort downloads. Unknown totals and processing must stay distinguishable.
5. Implement parent-liveness watchdog, grace deadline, owned process-tree handling,
   actual exit verification, and lock-safe crash recovery on each OS.
6. Reconcile durable starting state after spawn/ack/response loss. Use request-key
   receipts and worker identity to prevent a duplicated queue_start.

## Outputs and commands

Worker/controller/store integration and cancellation hooks with tests. Run
`pytest tests/test_mcp_worker.py tests/test_mcp_process_lifecycle.py` plus existing
queue engine, local HTTP, interruption, and history tests. Use actual subprocesses
for lifecycle tests and native Windows/POSIX runners for tree ownership checks.

## Acceptance

- Start/status/stop do not wait for full media download. Parallel status requests
  remain responsive; run success is never confused with per-job success.
- Existing CLI runner wins its lock and is not killed by another host's controller.
- EOF, parent kill, worker kill, stop-during-retry, and hung owned child preserve
  saved jobs/partials and leave no uncontrolled claiming process.
- Recovery cannot requeue work still being written by a live child.
- CLI-only run/retry works after MCP crashes, using the same database/history.
- A completed run never quietly starts newly enqueued jobs outside its snapshot.

## Completion notes

Pending: process ownership mechanism per OS, measured deadlines, exact injected
crashes, cleanup evidence, performance results, and commits.
