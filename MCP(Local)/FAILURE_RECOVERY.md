# Failure scenarios and recovery policy

Turn every numbered scenario into a test or a documented manual check. A fallback
must preserve permissions and data. Never silently switch to HTTP, another database,
another destination, or a different URL/quality to make an operation appear successful.

1. **SDK extra missing:** regular CLI remains usable. `pinak-mcp` writes a short
   installation remedy to stderr and exits nonzero; no traceback or partial protocol
   banner. No automatic pip invocation from the server.
2. **Unsupported Python/SDK/core combination:** reject before serving with required
   versions and the actual interpreter path. A compatible pinned release is the
   fallback; current builds require Python 3.11+ for patched dependencies.
3. **Host cannot locate executable / wrong environment / wrong cwd:** generated
   config uses absolute paths; doctor prints a launch check and environment remedy.
   Runtime must not depend on starting in the repository.
4. **Protocol negotiation or stdout contamination:** test handshake/framing; keep
   all incidental output on stderr. Unsupported versions get an explicit error.
5. **Invalid URL, option, ID, path, or oversized call:** reject before enqueue or
   filesystem mutation; error identifies the field. No partial bulk removal.
6. **Read-only/full/unavailable output folder:** preflight and catch actual write
   failures, since availability can change. Preserve partial files and fail the job;
   do not retry endlessly or redirect it without the user's instruction.
7. **SQLite busy/locked:** use bounded wait/backoff; report DATABASE_BUSY when
   exhausted. A locked DB is not corruption and must never be quarantined/reset.
8. **Confirmed corruption:** follow the existing evidence-based quarantine policy,
   preserve the damaged database, expose its location through local diagnostics,
   and disclose any new empty store. Test queue, history, and MCP tables together.
9. **Future schema / failed migration:** fail closed with a compatible-version
   remedy. Roll back the migration transaction. Preserve data and backup.
10. **Multiple hosts / existing CLI runner:** the worker FileLock decides ownership.
    Return RUNNER_BUSY; inspection and enqueue remain usable. Do not steal a lock
    based only on heartbeat age or kill a process identified only by PID.
11. **Repeated tool call after response loss:** same request_key/arguments replays
    the committed result; conflicting reuse returns IDEMPOTENCY_CONFLICT. For
    queue_start, reconcile durable starting state and child identity before retry.
12. **Source network error / temporary throttle:** use core bounded retry/backoff.
    Persistent errors become failed jobs with repair/retry instructions. Do not
    add nested unlimited retry loops in the MCP layer.
13. **Private/deleted/unsupported media, login/DRM restriction:** truthful failed
    result; do not invent bypasses, request raw credentials in tool output, or
    promise universal source support.
14. **Missing/broken FFmpeg or FFprobe:** doctor names the missing capability;
    queue management stays usable. Link installation guidance and allow explicit
    retry after repair. No provisioning during protocol initialization.
15. **Unknown download size/duration or FFmpeg postprocessing:** return unknown or
    processing states; do not show a fake percent/ETA or success at transfer EOF.
16. **User cancels a waiting job:** persist cancelled. Active job cancellation uses
    queue_stop semantics, not queue_cancel disguised as success.
17. **MCP call timeout/cancellation:** do not equate it with a stopped worker or
    rolled-back mutation. Client can reconcile via request_key, run_id, or queue_show.
18. **Host exits normally / adapter gets EOF:** stop the owned worker cooperatively,
    requeue interrupted work, retain partial files/history, close handles/locks.
19. **Parent killed / machine sleeps / worker crashes:** liveness watchdog prevents
    indefinite orphan claims; tolerate suspension without duplicate workers.
    Recovery only follows verified process death and exclusive lock acquisition.
20. **Graceful stop exceeds deadline / FFmpeg child hangs:** terminate only the
    verified owned tree, wait for exit, record interrupted outcome where possible;
    otherwise let the next locked runner recover the stale row. No detached FFmpeg.
21. **Crash after file completion before DB commit:** document possible repeat
    attempt and use existing duplicate/partial-file handling. No exactly-once claim.
22. **Progress listener fails / slow client / broken stderr pipe:** bounded queues,
    coalesced progress, and guarded logging must not fail or deadlock a download.
23. **Metadata is malformed, huge, or malicious:** sanitize control characters,
    limit response bytes/probe time, treat content as data, do not execute tags.
24. **Client lacks notifications/roots/structured rendering:** use polling,
    configured roots, and equivalent text results; core tool semantics stay equal.
25. **Client is cloud-only or does not support local stdio:** explain unsupported
    connection and suggest a supported local client or regular Pinak CLI.
26. **Config file malformed / multiple host entries / installed executable moved:**
    preserve originals, generate a reviewed repair snippet, avoid overwriting
    unrelated entries; detect stale executable path in doctor.
27. **Upgrade attempted during a live run:** ask user to stop the run and close
    clients, then verify no worker owns the lock before migration/update.
28. **Updated package will not start / downgrade cannot read migrated DB:** use
    last compatible package in a clean environment; restore a verified pre-migration
    backup only after quiescing writers and explaining post-backup data loss.
29. **MCP cannot start but core works:** `pinak queue list/show/run/retry` remains
    the documented operational fallback against the same database.
30. **Offline installation/update check:** existing installed operations and local
    inspection still work. Explicit update checks report unavailable, not up-to-date.

Recovery messages must say what happened, whether a mutation committed, whether
work is still active, and the next safe step. Logs must redact URL secrets,
credentials, and private paths where appropriate. Keep bounded rotating local
logs; do not require a telemetry server.
