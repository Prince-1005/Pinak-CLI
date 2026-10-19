# Maintaining Pinak-MCP

## Compatibility baseline

- Package: current source 2.0.0, shared with CLI; these MCP changes are unreleased.
- Python: 3.10–3.14, Windows/macOS/Linux CI; preserve ordinary CLI support.
- Official SDK: 2.3.0, optional `mcp` extra. No Node dependency at user runtime.
- Transport: local stdio. SDK client 2.3.0 and Inspector 2.11.0 interoperability
  tested; current SDK protocol is 2026-07-28. Do not infer every older protocol or
  desktop-client version is certified from that negotiation.
- Tool contract: 1.0. Policy: config_schema_version=1, unknown fields rejected.
- Database: core user_version=1; additive pinak_extensions.mcp=1. Pre-MCP source
  revision 73de91e766a8073afe356521534ca2239fe7c488 is the tested core reader floor.
- Desktop acceptance: Windows Cursor 3.23.12 discovery/download/metadata/error/stop/
  disconnect/reconnect passed; macOS/Linux desktop checks remain open. The Claude
  JSON generator is tested against disposable configuration files; generic stdio
  output is launch information, not a universal host configuration format.

## Dependency and contract updates

1. Use a dedicated dependency-update branch. Inspect released SDK metadata and
   actual installed APIs before changing the SDK pin in cli/pyproject.toml and
   the startup/doctor version checks. Review Python compatibility and changelogs.
2. From cli/, regenerate the MCP lock without silently relaxing core constraints:

   ```sh
   uv pip compile pyproject.toml --extra dev --extra mcp --universal --python-version 3.10 --generate-hashes --constraint requirements-lock.txt --output-file requirements-mcp-lock.txt
   ```

3. Diff tool input/output schemas and error envelopes. Existing clients must not
   receive silently renamed tools, changed meanings or arbitrary downloader flags.
   Decide whether contract/config/extension versions need independent changes.
4. Keep schema changes additive when possible. Coordinate migration with the
   existing queue lock, validate a consistent backup, roll back failed DDL, refuse
   future schemas, and state the oldest compatible reader. Never copy a live DB
   without its WAL or automatically restore over newer user data.
5. Run lint, both formatters, MyPy, coverage/security checks, native OS matrix,
   installed wheel smoke, real stdio/download, cancellation and process ownership
   tests. Repeat client acceptance for formats or protocol behavior that changed.
6. Update usage, compatibility, failure and phase evidence together. A version
   bump, tag and PyPI publication require a separate release instruction.

## Upgrade and restoration rehearsal

`cli/tools/smoke_mcp_upgrade.py` accepts distinct old/current wheels. It creates
temporary environments and seeded Unicode queue/history, upgrades with the MCP
extra, checks actual SDK stdio, downgrades to the compatible core reader, and
re-upgrades while replaying durable mutation receipts. It never runs the seeded
network download jobs. Supply `--pipx-python` to also check an isolated pipx home.

The current and pre-MCP fixture wheels both identify as 2.0.0 because no release
bump is authorized. The test deliberately force-reinstalls local wheels; this is
a source-revision compatibility drill, not evidence of a new published version.
CI fetches the pinned pre-MCP revision and runs the ordinary venv drill.

Tests in test_mcp_backup_recovery.py interrupt snapshot/migration writes and
restore into a disposable database. A real user restore requires every writer
stopped, a retained archive of the current database, verified backup integrity,
compatible installed code, and acknowledgement that later records are absent.
The implementation does not automatically perform destructive restoration.

## Resource and failure checks

Defaults: eight active tool calls, one queue runner, 100 records per page, 100 IDs
per mutation, 100 KiB result, seven-day receipt retention, and 512 KiB logs with
two backups. Status writes coalesce; no media bytes/artwork go to the model.

Metadata probing uses an isolated helper, a ten-second watchdog and twelve-second
outer deadline. The helper reports its actual PID/creation time and a unique
token before parsing media. This matters on Windows, where a venv launcher has
a different PID. Timeout cleanup verifies the actual identity and its owned
Job Object or POSIX process group. Never kill a process using a saved PID alone.

Snapshots use SQLite's backup API into a private temporary file, verify integrity,
flush, then atomically publish. An interrupted .tmp is not a usable .bak. An
existing incomplete pre-migration backup blocks migration instead of being trusted.

Keep fault fixtures local and deterministic: no dependence on public video sites,
login credentials or downloaded copyrighted samples. Retain redacted evidence;
do not commit temporary policy files, client configs, DBs or private URL logs.

## External acceptance still required

Follow VERIFICATION.md on a real Windows desktop host and a macOS/Linux desktop
host. Record app version, OS/Python, launch fields, discovery, successful download,
CLI history, stop/disconnect/reconnect and invalid-path/missing-binary feedback.
Machine suspend/resume and prolonged resource checks require an appropriate test
machine. SDK, Inspector and native process tests do not substitute for that UI
evidence. Keep unobserved checks explicit in README.md's verified scope rather
than inventing results.
