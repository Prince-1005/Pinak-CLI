# Pinak-MCP status ledger

Last planning review: 2026-10-19.

## Current evidence

- Current runtime: Pinak CLI with reusable engine, SQLite queue, and local history.
- MCP runtime/extra/entry point/client registration: **not implemented**.
- This MCP folder: specification, phases, proposed examples, and verification gates.
- Planning work does not establish any runtime phase as completed.

## Phase status

- 01 Foundation: planned.
- 02 Contracts/shared services: planned.
- 03 Worker lifecycle: planned.
- 04 MCP transport/tools: planned.
- 05 Installation/client setup: planned.
- 06 Recovery/hardening: planned.
- 07 Updates/compatibility: planned.
- 08 Verification/release: planned.

## Next action

After implementation is requested, begin phase 01. Resolve and record the released
SDK version and Python/OS compatibility before adding dependencies. Then freeze
schemas in phase 02. Do not advertise the example install/configure commands as
working before phase 08 evidence exists.

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
