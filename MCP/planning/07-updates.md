# Phase 07 — Updates, migration, and compatibility maintenance

Status: Backup/compatibility checks passed; installer-pair/restore gates pending.

## Inputs

SETUP_AND_UPDATES.md, version metadata/release helpers, lockfiles, migration code,
and seeded data from pre-MCP Pinak. R9; scenarios 2, 9, 26–28, 30.

## Tasks

1. Finalize the support matrix: package, Python, released SDK, protocol, client,
   tool contract, config schema, and database readable-version floor.
2. Test installation upgrades with MCP extras retained for pipx and ordinary
   isolated venvs. Detect stale client executable paths without blanket rewriting.
3. Test backup/migration under exclusive access using SQLite backup API, legacy
   requests, saved options, cancellation states, history, and receipts.
4. Refuse unsafe update/migration while a worker is active; do not force-kill a
   user's run as an installer side effect.
5. Inject failed migrations and incompatible downgraded readers. Document compatible
   package rollback vs backup restoration and its possible post-backup data loss.
6. Add explicit, bounded, opt-in version checks only if implemented; no startup
   update network calls or auto-executed downloads/scripts.
7. Establish maintenance procedure: dependency update branch, support-matrix tests,
   contract/schema diff review, release notes, staged client smoke checks.

## Outputs and commands

Upgrade/rollback guide, migration tests/backups fixtures, lockfile update procedure,
and compatibility evidence. Run `pytest tests/test_mcp_updates.py` and clean wheel
upgrade smoke tests. Re-run real stdio discovery after upgrading an environment
with seeded old jobs; verify jobs are neither discarded nor redownloaded implicitly.

## Acceptance

- Upgrade preserves queue/history/files/config and existing selected options.
- Future-schema and incompatible downgrade errors preserve the original store.
- Broken updates have a tested recovery route with truthful data-loss limitations.
- Ordinary CLI and MCP dependency floors remain independently enforced.
- Version metadata is coherent; no release/version bump is performed without the
  human's release instruction.

## Completion notes

2026-10-19: prepare-update refuses runner locks/active records and snapshots SQLite/settings without installing anything. Unicode seeded queue/history backup integrity and failure preservation passed. Core schema remains 1 with additive MCP extension 1. Published-version/pipx upgrade pairs and restore drills pending.

Remaining original gate checklist:

Pending: upgrade pairs tested, installer versions, readable schema floor,
backup/restore evidence, skipped combinations, and commits.
