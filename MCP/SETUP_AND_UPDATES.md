# Installation, client configuration, updates, and rollback

Everything in this document is a target workflow, not an available command today.
Verify package-manager/client commands against current official documentation
during implementation. Do not install or change a user's client while implementing
examples. Test examples in disposable configuration directories first.

## Installation model

Use `pinak-cli[mcp]` in the same repository/distribution. Product identity is
Pinak-MCP and executable is `pinak-mcp`; no separate PyPI name is required.
Proposed first-time command after publication: `pipx install "pinak-cli[mcp]"`.
For an existing pipx installation, document a tested extras-aware upgrade path;
do not tell users to run install again and assume the extra appeared.

Development: create/use an isolated venv in `cli/`, install editable `.[mcp]`,
and invoke that venv's absolute Python path. Avoid relying on shell activation
inside desktop apps. Regular CLI installation must not require Node.js; the MCP
Inspector is a developer verification tool, not a user runtime dependency.

## Planned commands

- `pinak-mcp serve --transport stdio`: protocol only on stdout; default supported
  transport is stdio. No banner, prompt, update check, or automatic binary install.
- `pinak-mcp doctor [--json]`: explicit local diagnostics and remediation; exits
  nonzero on blocking checks and distinguishes warnings from fatal errors.
- `pinak-mcp configure --client claude-desktop`: by default prints a proposed
  configuration and exact target location without writing it.
- `pinak-mcp configure --client claude-desktop --apply`: explicit request to merge
  only Pinak's entry; validate JSON, back up, atomic replace, preserve other entries.
- `pinak-mcp --version`: package and tool contract versions, no network requests.

Support other clients by generating their documented formats and testing them;
do not label one JSON schema universal. Prefer reviewed examples before adding
automatic editing of additional host configurations.

## Configuration templates

See [examples](examples/README.md). Placeholders are intentionally not executable.
The user configuration should specify approved output/read roots and limits.
Launch configuration supplies an absolute executable/interpreter and a user config
path. The repository's examples contain no tokens or user-specific absolute paths.

On Windows the official tutorial locates Claude Desktop JSON under
`%APPDATA%/Claude/claude_desktop_config.json`. Recheck this and app policy before
automating edits. Host restarts are user actions; do not terminate their AI app.

## Versions and dependency updates

Keep Pinak-MCP and Pinak CLI at one package version. Protocol version, public tool
contract version, local database schema version, and configuration schema version
are separate identifiers; do not treat them as interchangeable.

Choose and lock a released official SDK version after proving Python/OS support.
Publish a support matrix for Python, SDK, core, protocol, and tested client versions.
If a newer SDK requires newer Python, either select a supported compatible SDK or
explicitly require newer Python only for the MCP extra; keep ordinary CLI support
intact. Record the reason, markers, tests, and installation error behavior.

No automatic upgrades or migrations hidden inside download tools. Update checking
is opt-in and must use a bounded request to an official package/release source.
No network means check unavailable. Never download and execute a remote script
as an update mechanism.

## User upgrade procedure to deliver

1. Show current version, target compatibility notes, and the installation method.
2. Stop owned runs, close MCP hosts, verify all writers are quiescent.
3. If schema changes, make a SQLite backup using its backup API, including WAL-aware
   consistency. Do not copy only the live `.db` file or delete its sidecars.
4. Upgrade through the original installer with extras retained; test pipx and venv
   paths separately. Regenerate a stale executable path only when necessary.
5. Run doctor, inspect saved jobs/history, complete a real stdio handshake, restart
   the host, and perform a small local smoke download.
6. Resume work explicitly. Existing successful downloads must not run again just
   because the package was upgraded.

## Migration and rollback

Version migrations, validate old data first, run transactionally under coordinated
exclusive access, preserve queued JSON options/defaults, and reject future schemas.
Database ownership must coexist with core user_version and queue initialization.

Prefer additive migrations readable by the declared compatibility floor. A package
downgrade is not automatically safe after an incompatible migration. Document
last compatible releases and restoration procedure; keep the current database as
an archival copy before restoring an older backup. Restoration can discard changes
made after the backup, so make that consequence explicit before user action.

Test update/downgrade using seeded legacy queue/history and Unicode paths, failed
migration injection, and a running-worker refusal. Keep installer configuration
and secrets outside the repository; publishing docs never publishes user data.
