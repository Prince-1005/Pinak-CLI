# Verification and release gates

Existing gates remain mandatory. Run from `cli/` in an environment containing
the test/development tools and the implemented optional MCP extra. The test files
below exist; current evidence and missing gates are recorded in
IMPLEMENTATION_STATUS.md and ACCEPTANCE.md.

## Baseline commands

```sh
ruff check .
ruff format --check .
black --check --line-length=100 .
mypy pinak --config-file pyproject.toml
pytest --cov=pinak --cov-report=term-missing --cov-fail-under=75
bandit -r pinak -x tests -q -ll
pip-audit --local --skip-editable
python -m build
twine check --strict dist/*
```

Use the repository's actual dependency installation/lock workflow. On Windows
use a writable TEMP/TMP if the test environment requires it. Local socket/download
fixtures may need environment permission; an access-denied sandbox result is not
a product regression, nor a reason to omit real network-fixture verification.

## Required test groups

- `test_mcp_contracts.py`: field validation, response schemas, error codes, limits,
  annotations, null/unknown values, redaction, and request-key conflicts/replays.
- `test_mcp_store.py`: old schema/data migration, transaction rollback, queue/history
  preservation, future-schema refusal, busy/corrupt distinction, removal receipts.
- `test_mcp_worker.py`: start/status/stop, lock race with CLI and second host,
  startup handshake loss, no-job snapshot, cooperative cancel and listener failures.
- `test_mcp_process_lifecycle.py`: actual child processes, adapter EOF/kill, orphan
  watchdog, hung FFmpeg termination, PID reuse/ownership refusal, lock release,
  and restart recovery. Platform-specific branches must run on their native OS.
- `test_mcp_stdio.py`: actual SDK client launches installed module/executable;
  handshake, tools/list, calls, errors, concurrency, framing, clean stdout, EOF.
- `test_mcp_download_e2e.py`: local HTTP server with deterministic media fixtures;
  actual download into approved output, exact bytes/files and queue/history result,
  retry/replay, interrupted partial transfer, multi-ID management after restart.
  Include actual FFmpeg audio processing where a tested binary is available.
- `test_mcp_setup.py`: supported host JSON examples, path quoting/Unicode, arbitrary
  cwd, config merge/backup/atomic write, malformed config, permissions, repeat apply.
- `test_mcp_updates.py`: seeded old installation state, extras-aware installer path,
  schema upgrade, failed upgrade, live-worker refusal, downgrade compatibility.

Mocks are appropriate for deterministic error injection and unavailable third-party
sites. They do not replace actual protocol or worker lifecycle integration. CI
must not depend on YouTube/Instagram availability or download copyrighted fixtures.

## Manual client acceptance

Record OS, Python, package, SDK, client version, and date for each tested host.
At least one Windows desktop host and one macOS/Linux desktop host must connect
using published examples. Verify discovery, enqueue, start, concurrent status,
download success, history visibility in CLI, stop/disconnect/reconnect, and a
clear missing-binary or invalid-path error. Restart the host after config changes.
Screenshots are supplementary; retain structured outputs/logs with secrets removed.

Never claim an untested client supported merely because its name appears in docs.
Inspector validation is required in development but does not establish desktop
client support on its own.

## Performance and resource gates

Provisional targets on provisioned local machines: metadata tools <=1 second,
accepted worker start <=2 seconds, graceful stop <=10 seconds, orphan stop initiation
within the documented 30-second threshold when the system is running. Measure and
record p95 across repeated fixtures; network download completion has no fixed SLA.
Any changed thresholds require rationale and documentation, not hidden test relaxation.

One worker per database, no unbounded thread/task/subprocess queues, bounded logs
and status writes, no full file/media response bodies, no child process or socket
left after controlled shutdown. Inspect process handles and locks in tests.

## Packaging, CI, and documentation gates

- Test core without MCP extra and MCP with extra from clean installed wheels.
- Preserve the existing Windows/macOS/Linux Python matrix; add compatible MCP
  combinations, including the declared lower Python bound for the extra.
- Run core coverage >=75%; add branch-focused assertions for critical new failure
  paths rather than relying on the aggregate percentage.
- Wheel includes runtime modules, excludes root MCP plans, Website assets, secrets,
  test databases, and logs. Use current package smoke/release helpers.
- If website docs change: build, validate references, and run applicable browser tests.
- SDK/tool/config/database support matrix, installer examples, troubleshooting,
  privacy notes, and update/rollback docs agree with the implemented commands.
- Verify remote workflows for the actual final commit, if push/release is authorized.
- A public release still needs explicit human authorization; phase completion
  does not itself publish a package or tag.

## Requirement audit

Map R1–R10 from REQUIREMENTS.md and scenarios 1–30 from FAILURE_RECOVERY.md to
tests or dated manual evidence. Record missing/skipped evidence as incomplete.
No universal zero-bug claim, no exactly-once claim, no false successful downloads,
and no end-to-end completion claim before this audit passes.
