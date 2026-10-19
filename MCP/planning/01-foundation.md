# Phase 01 — Compatibility and package foundation

Status: planned. Prerequisite: read all documents listed in MCP/README.md.

## Inputs

Current pyproject/lockfiles, release helpers, Python >=3.10 support, CLI startup,
engine/queue/history, and official SDK release documentation. R1–R2, R9–R10.

## Tasks

1. Establish a clean baseline and preserve unrelated files.
2. Choose a released official MCP SDK version after testing its Python/OS support.
   Record exact version, public import API, protocol support, and dependency bounds.
3. Add optional `mcp` dependencies and reproducible lock/install handling. Keep
   SDK import lazy; missing extra gives an actionable nonzero command exit.
4. Create `cli/pinak/mcp_server/` package and planned entry point `pinak-mcp`.
   Separate serve from doctor/configure/version argument dispatch without exposing
   unimplemented tools as working features.
5. Establish strict typed models/config loading, stderr logging, and isolated test
   fixtures. Configuration paths must use user app directories, not repository cwd.

## Outputs and commands

Support matrix and dependency rationale in completion notes; package skeleton,
optional-extra installation tests, and baseline stdout/import isolation tests.
In isolated environments: install core, run `pinak --version`/`--help`; separately
install editable `.[mcp]`, inspect the actual SDK version, and run entry-point tests.
Use `pytest tests/test_mcp_contracts.py` once created, lint/type checks, and a clean
wheel build. Do not register a live client in this phase.

## Acceptance

- Core commands/imports work without SDK installed; no MCP import or migration
  runs as a side effect of ordinary CLI startup.
- Extra installs on every declared lower/upper Python/OS target or a documented
  extra-specific Python floor is implemented and tested explicitly.
- Executable resolves outside the repository and produces no import-time banner.
- No version bump, release, backend service, or independent downloader introduced.

## Completion notes

Pending: implementation commit, selected SDK/version matrix, exact commands,
exit results, unverified environments, and next phase readiness.
