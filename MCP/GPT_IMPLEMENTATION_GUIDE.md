# Instructions for GPT implementation sessions

This is project guidance for future implementation, not evidence of current
completion. Respect the human user's latest scope and repository instructions.

## Start every implementation session

1. Read MCP/README.md, REQUIREMENTS.md, ARCHITECTURE.md, TOOL_CONTRACT.md,
   FAILURE_RECOVERY.md, and IMPLEMENTATION_STATUS.md. Then read the active phase.
2. Inspect current git status, package versions, applicable AGENTS.md, engine,
   queue/history behavior, workflows, and tests. Preserve unrelated changes.
3. Verify current SDK/client documentation and installed dependency APIs. Record
   the selected released SDK version and support matrix in status/phase notes.
4. State the concrete phase outcome and inspect its prerequisites before editing.
   Do not infer that files or checkboxes prove runtime behavior.

## Execution rules

- Work sequentially through phases 01–08. Continue authorized work without asking
  about routine implementation details. Ask only about a material unresolved
  product choice or a genuinely required permission.
- The currently chosen model is one local stdio server plus a supervised local
  worker, shared package/database, and optional dependencies. Do not replace this
  with a hosted backend, separate repo, task-queue service, or shell wrapper.
- No runtime implementation should be created merely while reviewing this plan.
  A later request to implement authorizes the corresponding implementation work.
- Keep dependency upgrades, schema changes, and changes to regular CLI behavior
  explicit. Do not increment the package version or publish a release unless the
  user authorizes release work; planning alone authorizes neither.
- Do not silently remove a difficult requirement, substitute mock-only proof for
  a real stdio session/download, or call queue-only MCP a complete delivery.
- Keep public command names and schemas stable after phase 02, or record a
  justified compatibility change and update all fixtures/docs together.
- Do not introduce new files named `mcp.py` that shadow the installed SDK.
- Do not edit real client config, install globally, or start a visible app while
  validating configuration generators; use temporary roots/fixtures first.
- Never expose secrets in logs, test snapshots, Git patches, or tool responses.

## Required phase completion record

Append evidence to the phase's Completion notes and update IMPLEMENTATION_STATUS.md:

- status: planned / in progress / verified / blocked;
- implementation commit(s) and changed files;
- exact commands, environment, exit results, and test coverage of requirements;
- failure scenarios exercised and their observed outcomes;
- tested Python/OS/SDK/client versions and skipped checks with reasons;
- unresolved risks and the next concrete task.

Do not mark verified while a required gate is missing, failing, only mocked when
real execution is required, or contradicted by code. Mark a phase blocked only
with the specific external input needed; do unaffected work first.

## Suggested task prompt

> Implement Pinak-MCP phase NN using MCP/README.md and its linked contracts.
> Inspect current code first, preserve CLI behavior and saved data, and satisfy
> the phase acceptance checks. Update phase notes/status with evidence. Do not
> publish packages or register real clients without authorization.

## Handoff and context recovery

Persist progress in tracked Markdown, not only chat memory. On continuation,
resume the first unverified requirement from the status ledger. Recheck running
processes before restarting them. A timeout is not evidence a worker stopped.
Include exact ownership/run IDs, database fixtures, and reproducible commands in
handoffs without committing machine-specific credentials or live databases.
