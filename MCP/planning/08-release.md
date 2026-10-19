# Phase 08 — End-to-end acceptance and release preparation

Status: planned. Dependencies: every earlier phase verified.

## Inputs

VERIFICATION.md, R1–R10, all failure scenarios, completed phase notes, clean builds,
support matrix, setup examples, user docs, existing release/website workflows.

## Tasks

1. Run the exact repository lint, Ruff format, Black, MyPy, coverage >=75%,
   security/secret scan, and clean installation gates. Add MCP combinations to CI
   without silently weakening the existing core OS/Python matrix.
2. Build wheel/sdist, validate metadata with Twine, inspect packaged files, and
   smoke both core-only and MCP-extra installations outside the repository cwd.
3. Execute real SDK stdio and local-download scenarios from the installed artifact;
   verify file bytes, persisted queue/history, stop/reconnect, receipt replay, and
   no leftover owned processes. Confirm MCP works without Node at user runtime.
4. Record at least the required Windows and macOS/Linux desktop client acceptance
   evidence. Inspector-only testing is insufficient for a desktop-support claim.
5. Ensure all docs/website commands match executable help and tool schemas. Build
   and validate website docs if changed; keep Website/MCP plans out of the wheel.
6. Complete a requirement-by-requirement and scenario-by-scenario audit. A missing
   result, unsupported claimed client, or untested lifecycle path blocks completion.
7. Prepare release notes and user upgrade/rollback steps. If the human authorizes
   commit/push, verify workflows on the final SHA. Publishing/tagging is a separate
   explicit release action, not an automatic consequence of this plan.

## Outputs and commands

Release candidate, reproducible evidence manifest, final support matrix, user docs,
and a concise remaining-limitations report. Run all commands in VERIFICATION.md,
installed-artifact integration tests, package smoke helpers, and applicable
website checks. Preserve logs/artifacts with credentials and private URLs redacted.

## Acceptance

- R1–R10 and scenarios 1–30 have current authoritative evidence.
- A new user can configure a supported local host and complete an actual download.
- CLI-only users can still operate without SDK installed.
- Host exit, worker failure, retries, updates, and rollback have tested outcomes.
- No claim of zero bugs, universal host support, exactly-once downloads, or complete
  privacy from the AI provider is made.

## Completion notes

Pending: final commit SHA, CI URLs/results, wheel hashes, tested host versions,
audit links, known limitations, release authorization/status, and maintenance owner.
