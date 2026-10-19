# Pinak-MCP status ledger

Last planning review: 2026-10-19.

## Current evidence

- Current runtime: Pinak CLI with reusable engine, SQLite queue, and local history.
- MCP runtime/extra/entry point: implemented in source; client registration
  has not been applied to any live host.
- This MCP folder: specification, phases, proposed examples, and verification gates.
- Runtime evidence below does not certify untested desktop clients or a release.

## Phase status

- 01 Foundation: local SDK 2.3.0 (Python >=3.10), optional extra and lazy entry point
  implemented; core import isolation and contract tests passed. OS matrix pending.
- 02 Contracts/shared services: SQLite receipts, additive extension schema and
  backup, policy, pagination, and mutations implemented; real SQLite tests passed.
- 03 Worker lifecycle: real Windows downloads, stop, adapter EOF/forced kill,
  worker crash, ownership refusal and hung descendant cleanup passed. OS matrix pending.
- 04 MCP transport/tools: real SDK client stdio initialize/discover/call/error/exit
  passed from unrelated cwd. Actual WAV download, MP3 conversion, request cancellation
  reconciliation and overload limits passed. Inspector 2.11.0 discovered fourteen
  tools and successfully called server_info through temporary stdio configuration.
- 05 Installation/client setup: preview/apply/backup/atomic merge implemented and
  temporary-directory tests passed. Client-neutral launch fields implemented.
  Clean core-only/MCP-extra wheel installation passed. Desktop acceptance pending.
- 06 Recovery/hardening: corruption disclosure/quarantine, disk-full/read-only
  classification, atomic rollback, receipt expiry and launch failure cleanup tested;
  metadata probes isolated with deadlines. See ACCEPTANCE.md for remaining gates.
- 07 Updates/compatibility: explicit backup preflight implemented. Unicode seeded
  queue/history preservation, snapshot integrity, failure cleanup and runner refusal
  passed. Published installer upgrade pairs/pipx and restoration drills pending.
- 08 Verification/release: local baseline passed (630 tests, 77.12% coverage at the
  full-suite checkpoint). Later concurrency/cancellation/forced-parent tests passed.
  Clean wheel/sdist metadata, actual installed stdio download, dependency consistency
  and advisory audit passed. Final CI and manual release gates remain pending.

## Next action

Finish final source CI and record external client acceptance. No phase is globally verified
until its required matrix/manual gates are recorded. SDK source verified locally:
MCPServer and official low-level Server callbacks in mcp 2.3.0; low-level callbacks
are used for explicit flat schemas/error envelopes, without custom JSON-RPC code.

Local evidence so far (2026-10-19, Windows, Python 3.12):
- `pytest tests/test_mcp_contracts.py tests/test_mcp_store.py --no-cov`: 14 passed.
- `pytest tests/test_mcp_worker.py --no-cov`: 3 passed with actual WAV download,
  FFmpeg metadata processing, exact PCM verification, history, lock and replay.
- `pytest tests/test_mcp_stdio.py tests/test_mcp_setup.py --no-cov`: 4 passed.
- Ruff and MyPy passed at this checkpoint (107 source files).
- MCP lock compiled universally for Python >=3.10 retaining core constraints.
- Full regression checkpoint: 630 passed in 62.87s; coverage 77.12%.
- SDK stdio concurrency/cancellation tests: 3 passed.
- Clean wheel: core-only missing-extra remedy, extra installation, real local
  download/PCM/queue/history, pip check and no known dependency advisories passed.
- Inspector 2.11.0 with Node 24.19.0: tools/list=14; server_info ok=true.
- Development pip check/advisory audit and Bandit medium+ gate passed;
  MyPy passed across 109 source files.
- Final local regression: 633 passed in 71.34s; coverage 76.76%. Subsequent focused
  setup/update/worker checks: 10 passed. Windows venv redirectors are handled by
  recording/verifying the actual worker identity separately from its launcher;
  retained-PID status and actual adapter-kill tests passed.

Local evidence is Windows/Python 3.12. No live client configuration was changed.
Disposable logs/configs are under cli/.venv/ and are not committed.

Remote checkpoint: source commit 25e2542 pushed and synced into D:/pinak. First
CI run identified Unix type stubs rejecting Windows-only subprocess constants;
the follow-up resolves them portably and verifies both --platform linux/darwin
locally. Security and secret scans passed; website verification passed. Final
matrix status must be checked against the follow-up SHA, not the first attempt.
Local twenty-sample performance results are recorded in ACCEPTANCE.md.

Compatibility decision: keep PRAGMA user_version=1 for the unchanged core queue;
add `pinak_extensions(name='mcp',version=1)` and additive tables. Old core readers
remain compatible; unknown MCP extension versions fail closed. A consistent
pre-extension SQLite backup is taken with the backup API under the runner lock.

## Decisions already made

Same repository; product Pinak-MCP; executable pinak-mcp; optional pinak-cli[mcp]
distribution; runtime package pinak.mcp_server; local stdio only; one existing
queue/history store; existing queue lock; supervised local worker; explicit
installation/update; no hosted backend or automatic application launch.

## Decisions to verify through implementation evidence

- Exact released SDK bounds, Python support, and lockfile changes.
- Exact host versions supported by smoke tests and configuration generators.
- Cooperative downloader cancellation and owned-process-tree shutdown on all OSes.
- Additive database migration and minimum readable/downgrade versions.
- Measured response/worker-start/stop limits and bounded progress/log retention.

Use phase notes for detailed evidence; summarize changes here after each phase.
