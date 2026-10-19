# Phase 05 — Installation, diagnostics, and client onboarding

Status: Disposable setup and clean-wheel checks passed; live host acceptance pending.

## Inputs

SETUP_AND_UPDATES.md, examples/, official target-client formats, installed wheel.
R2, R8; scenarios 1–4, 14, 24–26.

## Tasks

1. Deliver tested fresh/existing pipx and venv installation instructions for the
   MCP extra, stable entry point, and absolute-path launch resolution.
2. Implement doctor: interpreter, extra/core compatibility, database readiness,
   binary capabilities, approved root permissions, process ownership, config errors.
   Diagnose without modifying user state or installing binaries.
3. Implement configure as preview-only by default. `--apply` must preserve unrelated
   keys, refuse malformed JSON, back up, atomically merge, and be repeatable.
4. Replace template assumptions with verified schema-backed examples. Test spaces,
   Unicode, JSON escaping, missing PATH, moved venvs, and arbitrary working directories.
5. Document one verified desktop host first; support additional hosts only with
   their actual configuration format and a recorded connection test.
6. Explain privacy, local-source downloads, permissions, queued-vs-running behavior,
   restart expectations, and unsupported cloud-only clients in plain language.

## Outputs and commands

configure/doctor commands, schema-backed examples, setup tests, user installation
and troubleshooting docs, and website docs when appropriate. Run
`pytest tests/test_mcp_setup.py`; validate each JSON fixture and simulate interrupted
config writes in temporary directories. Then test a user-approved real client.

## Acceptance

- Fresh user can install, generate/review config, connect, discover tools, enqueue,
  start, inspect, and find local files using only published instructions.
- Existing non-Pinak client entries remain byte/semantically intact as specified;
  repeated apply does not create duplicates and backup restoration is documented.
- A bad interpreter or missing extra yields an actionable diagnostic.
- Normal CLI remains usable when MCP setup is absent or broken.

## Completion notes

2026-10-19: Generic configure prints client-neutral stdio fields. Claude-format preview/apply/backup/merge/atomic-failure tests passed against disposable files. Core-only and MCP-extra clean wheel installs with actual protocol download passed. USAGE.md documents source setup; PyPI publication has not happened.

Remaining original gate checklist:

Pending: exact installer commands verified, client versions/OS, disposable and
real-client setup results, documentation locations, and commits.
