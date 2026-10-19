# Phase 02 — Contracts, policy, and shared services

Status: implemented and locally tested; global acceptance pending.

## Inputs

TOOL_CONTRACT.md, REQUIREMENTS.md, current queue/history functions and schema.
R3, R5–R7; failure scenarios 5–11, 23.

## Tasks

1. Freeze every public tool's input/output model, error code, pagination contract,
   and limits. Commit representative JSON fixtures and schema compatibility tests.
2. Implement service functions around the engine/queue; avoid parsing Rich output
   or spawning `pinak` for each metadata operation. Preserve CLI semantics.
3. Add efficient paginated SQL reads; validate filters/cursors and parameterize
   queries. Bound recorded files/errors without silently hiding truncation.
4. Implement output/read-root checks, path normalization, symlink/junction tests,
   redaction, and no arbitrary executable/flag/config injection.
5. Design and implement additive run/receipt storage and its coordinated schema
   migration. Use transactions for queue mutations plus idempotency receipts.
   Current public queue functions open their own transactions: extract reusable
   transaction-aware primitives where needed, retaining existing public wrappers.
   Do not nest independent SQLite writers or claim a receipt is atomic when it
   commits separately from the mutation.
6. Preserve history_enabled behavior and queue/history atomic completion.
   Unknown IDs in atomic remove-many must never partly remove records.

## Outputs and commands

Typed schemas, service/policy/store modules, migration fixture builder, and tests:
`pytest tests/test_mcp_contracts.py tests/test_mcp_store.py`. Run existing
`test_queue.py`, `test_queue_management.py`, `test_history.py` and type/lint checks.

## Acceptance

- Tests cover same-key replay, mismatched-key conflict, expired receipt behavior,
  deletion response replay, limits, paginated ordering and parameterized cursors.
- Old queue/history data survives migration exactly, with defaulted legacy options.
- Read-only errors do not masquerade as empty results; errors never leak secrets.
- Forced enqueue can be deliberately repeated with a new key, but replaying the
  original key cannot create another forced job.
- No worker lifecycle is claimed complete yet; phase 03 consumes these services.

## Completion notes

2026-10-19 local evidence: Contract 1.0 and policy version 1 implemented. Core user_version remains 1; additive MCP extension version 1, consistent pre-extension backup, atomic receipts and pagination tested with real SQLite. Unknown extension versions fail closed.

The original release-gate checklist below remains open where not covered above.

Pending: frozen contract version, schema transition/floor, test evidence,
transaction boundaries, unresolved decisions, and implementation commits.
