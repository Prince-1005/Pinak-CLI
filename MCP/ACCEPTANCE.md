# Pinak-MCP acceptance evidence

Source implementation, reviewed 2026-10-19. Local checks use Windows/Python 3.12,
MCP SDK 2.3.0. This document tracks evidence, not a claim of universal readiness.
The package version is unchanged; no tag, PyPI release or live host registration.

## Requirements

- R1: official SDK stdio initialization, fourteen tools, compatible text/structured
  results; independent Inspector 2.11.0 discovery and server_info call passed.
  Actual desktop-client acceptance remains outstanding.
- R2: lazy imports and core-only clean-wheel missing-extra remedy passed.
- R3: contracts/store/stdio tests verify typed inputs, all queue operations,
  transactions, replay, retention and preservation of downloaded files/history.
- R4: real worker/SDK download tests, concurrent polling, stop, eight-call limit,
  overload rejection and cancelled-response reconciliation passed.
- R5: real SQLite core interoperability, common runner FileLock and another
  session's stop refusal passed; no hosted services or new database.
- R6: seeded options/history, atomic bulk validation, exact PCM, clean keeping
  media, and additive core-schema compatibility tested.
- R7: pagination/root containment/redaction, real duration probe and isolated
  metadata process with watchdog implemented; hostile metadata stress is pending.
- R8: USAGE.md, configure generic stdio, disposable JSON merge/backup, doctor,
  regular CLI fallback and actual installed-wheel protocol smoke passed. No named
  desktop-host version is certified yet.
- R9: consistent SQLite backup, migration receipts, future-extension refusal,
  Unicode seeded state, failed-backup preservation and live-run refusal passed.
  Clean published-version/pipx upgrade pairs and restore drills remain pending.
- R10: baseline tests/lint/format/types/security/build/install passed locally;
  complete final source CI matrix, performance and manual acceptance remain gates.

## Failure scenarios 1–30

Numbers refer to FAILURE_RECOVERY.md. Existing core tests remain authoritative
for download behavior delegated to the shared engine.

1. Missing extra: clean core-only wheel smoke; stderr remedy and no stdout.
2. SDK mismatch: exact version check before optional imports; multi-Python CI pending.
3. Wrong cwd: real SDK/wheel subprocesses launch from unrelated directories;
   generated interpreter is absolute. Moving an installed interpreter requires reconfigure.
4. Framing: real SDK and independent Inspector; no banner on stdout.
5. Bad arguments: contracts/store tests; no partial bulk mutation.
6. Output write failures: shared engine tests and policy checks; real disk-full
   fixture/manual check remains pending. No destination fallback exists.
7. Busy SQLite: bounded core connection timeout; locked classification fault test.
8. Corruption: real damaged DB quarantined, original bytes retained and warning returned.
9. Future schema: extension refusal and core schema checks; additive transaction/backup
   tests. More migration failure injection and native OS matrix pending.
10. Multiple runners: existing FileLock and actual CLI lock test; no heartbeat lock stealing.
11. Response loss: actual cancelled SDK request reconciled; remove/start replay tests.
12. Network/throttle: existing core retry classification/backoff tests. Public sites
    deliberately are not CI fixtures; availability is not a universal support promise.
13. Restricted media: shared engine failure results; external login/DRM sites not certified.
14. Binaries: no provisioning in managed worker, bounded explicit doctor version check;
    real optional MP3 conversion tested locally. More missing/broken binary fault tests pending.
15. Processing: only core final outcome marks a job complete; real FFmpeg conversion test.
16. Cancellation: persisted waiting-job cancellation; actual stop requeues active work
    and does not claim later-added jobs.
17. Request cancellation: actual SDK cancellation/replay test; mutation may commit.
18. EOF: actual child stop/requeue/lock cleanup test.
19. Killed parent/worker: actual forced adapter kill and worker crash tests; stale rows
    recovered by locked core runner. Machine suspend/resume manual check pending.
20. Hung child: actual owned descendant watchdog test; Windows Job Objects / POSIX
    dedicated process group. Native POSIX CI evidence pending.
21. Completion/commit crash: documented possible repeat attempt; no exactly-once claim.
22. Progress: core listener-failure guards and coalesced snapshots; actual overload
    rejects twelve of twenty overlapping calls while eight execute. Broken-pipe
    and long-duration log stress drills pending.
23. Metadata: controls/secrets/NaN sanitation, per-response limit, isolated ten-second
    probe watchdog and no artwork bytes. Hostile-file timeout/memory stress pending.
24. Client capability fallback: same factual JSON in text and structured content;
    polling and configured roots. Host-version rendering acceptance pending.
25. Cloud-only client: explicit unsupported transport guidance; no remote bridge.
26. Config: disposable invalid JSON, backup, merge, idempotency and failed replace tests.
27. Live update: lock and saved-active-run refusal; point-in-time warning, no pip invoked.
28. Broken update: backup integrity/failure preservation and documented clean-venv
    rollback; old/new installation pairs and restoration drills pending.
29. CLI fallback: core queue remains shared/readable; full existing regression suite passed.
30. Offline: no network update check or automatic upgrade; offline wheel/install
    cache scenario remains manual. Existing local inspection needs no network.

## Release gates still open

Do not describe all phases as verified until these results exist:

- Final commit CI: Windows/macOS/Linux across Python 3.10–3.14, package/container
  smoke, coverage and security scans.
- A real Windows desktop client and a real macOS/Linux desktop client, with
  versions and dated discovery/download/stop/reconnect evidence.
- Published-version/pipx update pairs and rollback restore rehearsal.
- Repeated p95 timing/resource measurements; hostile media, disk-full,
  suspend/resume and long-duration logging stress checks described above.

The current session cannot hot-attach arbitrary stdio tools through its exposed
tool API. SDK client tests and Inspector independently exercise the server;
neither substitutes for the desktop-host gates above. No user configuration was
changed merely to generate evidence.
