# Pinak-MCP acceptance evidence

Source implementation, reviewed 2026-10-19. Local checks use Windows/Python 3.12,
MCP SDK 2.3.0. This document tracks evidence, not a claim of universal readiness.
The package version is unchanged; no tag or PyPI release. The temporary isolated
Cursor registration was removed after testing and original config restored.

## Requirements

- R1: official SDK stdio initialization, fourteen tools, compatible text/structured
  results; independent Inspector 2.11.0 discovery and server_info call passed.
  Windows Cursor 3.23.12 discovery and real calls passed; other hosts remain open.
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
  regular CLI fallback and actual installed-wheel protocol smoke passed. Named
  Windows Cursor 3.23.12 download/stop/disconnect/reconnect acceptance passed.
- R9: consistent SQLite backup, migration receipts, future-extension refusal,
  Unicode seeded state, failed-backup preservation and live-run refusal passed.
  Actual pre-MCP/current local wheel upgrade, compatible core downgrade, re-upgrade
  and receipt replay passed in a venv. Pipx 1.18.4 force-install/reinstall/upgrade
  retained the extra and passed stdio. Disposable backup restoration passed.
  Both fixture source revisions identify as 2.0.0; no new release was published.
- R10: final source CI passed all eighteen jobs, including the complete native
  OS/Python matrix, package/container, upgrade and security checks. All fifteen
  timing reports were inspected; manual acceptance and the noted metadata target
  miss remain limitations.

## Failure scenarios 1–30

Numbers refer to FAILURE_RECOVERY.md. Existing core tests remain authoritative
for download behavior delegated to the shared engine.

1. Missing extra: clean core-only wheel smoke; stderr remedy and no stdout.
2. SDK mismatch: exact version check before optional imports; baseline native CI
   passed all fifteen OS/Python combinations, including final source 41dd4e8.
3. Wrong cwd: real SDK/wheel subprocesses launch from unrelated directories;
   generated interpreter is absolute. Moving an installed interpreter requires reconfigure.
4. Framing: real SDK and independent Inspector; no banner on stdout.
5. Bad arguments: contracts/store tests; no partial bulk mutation.
6. Output write failures: actual worker output-folder conflict preserved the
   existing file/destination and saved failure. Real SQLite FULL (page cap) and
   read-only mode tests rolled back queue/receipt changes without quarantine.
7. Busy SQLite: bounded core connection timeout; locked classification fault test.
8. Corruption: real damaged DB quarantined, original bytes retained and warning returned.
9. Future schema: extension refusal and core schema checks; additive transaction/backup
   tests, injected mid-migration DDL failure rolled back all extension tables.
   Atomic validated snapshots and incomplete-backup refusal/doctor checks passed.
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
    dedicated process group; native POSIX/Windows baseline CI passed.
21. Completion/commit crash: documented possible repeat attempt; no exactly-once claim.
22. Progress: core listener-failure guards and coalesced snapshots; actual overload
    rejects twelve of twenty overlapping calls while eight execute. A 2.5 MB log
    rotation/broken-stderr drill verified three bounded files and secret redaction.
    Prolonged duration/resource soak testing remains manual.
23. Metadata: controls/secrets/NaN sanitation, per-response limit, isolated ten-second
    probe watchdog and no artwork bytes. Actual outer-timeout injection killed the
    helper's real Python identity and its descendant, including Windows redirectors.
    Hostile-file memory stress remains manual.
24. Client capability fallback: same factual JSON in text and structured content;
    polling and configured roots. Cursor 3.23.12 Windows discovery, actual download,
    progress/stop, metadata and error rendering passed; other host gates remain open.
25. Cloud-only client: explicit unsupported transport guidance; no remote bridge.
26. Config: disposable invalid JSON, backup, merge, idempotency and failed replace tests.
27. Live update: lock and saved-active-run refusal; point-in-time warning, no pip invoked.
28. Broken update: atomic backup integrity/failure preservation, actual compatible
    core downgrade/re-upgrade and disposable restoration passed. Post-backup records
    remain in a separate current-state archive and are absent in the restored store.
29. CLI fallback: core queue remains shared/readable; full existing regression suite passed.
30. Offline: no network update check or automatic upgrade; offline wheel/install
    cache scenario remains manual. Existing local inspection needs no network.

## Release gates still open

Final source 41dd4e84606afb9ecf3c75c2f69aa99bdb5eaffd passed
[all eighteen CI jobs](https://github.com/Prince-1005/Pinak-CLI/actions/runs/39261336830).
All fifteen twenty-sample timing artifacts were inspected. Across native targets,
p95 ranges in seconds were: server_info 0.0001–0.0004, queue_list 0.0429–0.1061,
media_info 0.4200–1.0240, worker start 0.3851–0.9281 and stop 0.5486–1.2314.
Windows/Python 3.12 narrowly missed the provisional 1s metadata target; no timeout
or correctness failure occurred. Profiling/startup improvements remain follow-up
work, and these fixture timings are not desktop-host or AI-provider latency.

Local performance checkpoint (Windows/Python 3.12, twenty samples each): p95
server_info 0.0001s, queue_list(limit=100) over 10,000 saved records 0.0885s,
media_info 0.5992s, actual worker start 0.5450s, cooperative stop 0.7419s.
These are direct shared-service timings with temporary SQLite/WAV/loopback HTTP
fixtures, not AI-provider or desktop-host response latency. All are within the
provisional local targets. Native OS timing/resource and long-duration stress
acceptance remains open.

Latest production-default twenty-sample reports on the same Windows machine:
server_info p95 0.0001s, queue_list 0.2665s, media_info 1.0092s, worker start
0.7140s and stop 0.9622s. A concurrent-suite run measured media_info 1.0707s;
the repeat after the suite finished still narrowly missed the provisional 1s
metadata target. The isolated helper's interpreter/probe startup is included.
Inspect native CI artifacts and profile startup before claiming that target is
met. Both reports remain under ignored cli/benchmark-results/.

Do not describe all phases as verified until these results exist:

- A real macOS/Linux desktop client, with version and dated
  discovery/download/stop/reconnect evidence. Windows Cursor 3.23.12 passed.
- First published-version upgrade acceptance after a separately authorized release.
- Hostile-media memory, suspend/resume and prolonged resource soak checks
  described above; investigate metadata startup against the provisional target.

The current session cannot hot-attach arbitrary stdio tools through its exposed
tool API. SDK client tests and Inspector independently exercise the server;
neither substitutes for the desktop-host gates above. After a stopped first
attempt and exact config restoration, the user authorized a fresh Cursor test.
Cursor 3.23.12 Windows discovery/download/metadata/error/progress/stop and real
disconnect/reconnect passed; see CLIENT_ACCEPTANCE.md for scope and exact config
restoration. macOS/Linux desktop acceptance remains open.
