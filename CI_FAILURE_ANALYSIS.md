# CI failure analysis — 25 October 2026

Analyzed local commit `5e04f9e` and all 15 supplied job logs from
[Actions run 40200748151](https://github.com/Prince-1005/Pinak-CLI/actions/runs/40200748151).
The supplied links cover 14 Python/OS matrix jobs and one installation job.

## Findings and fixes

### Cloud storage admission used stale disk usage

Every supplied matrix job reached pytest and failed at
`tests/test_mcp_cloud.py::test_quota_admission_preserves_replay_and_inspection`.
The failure was `KeyError: 'error'` at the expected `STORAGE_LIMIT` response.
Ruff lint, Ruff formatting, Black, and mypy had already passed in those jobs.

The first `queue_add` sampled an empty downloads directory.
`CloudTools.get_storage_usage()` cached that sample for five seconds. The test
then wrote a 1 MiB file and immediately called `queue_start`; admission reused
the empty sample and returned success. This is a production admission bug as
well as a test failure: a newly full directory could admit work until refresh.

`cli/pinak/mcp_cloud/tenant.py` now forces a fresh storage scan for new
`queue_add` and `queue_start` admissions. Receipt lookup still happens first,
so replaying a previously accepted mutation remains possible at capacity.
Inspection and removal remain available.

The regression test now covers both a full job queue and a queue with a spare
job slot. The latter proves that storage independently blocks a new save;
both cases verify that full storage blocks starting work and preserves replay,
inspection, and removal. Tests assert failure before inspecting its error code,
so an unexpected success prints its response instead of an opaque KeyError.

### Headless Linux playback import lacked an audio server

The installation job failed inside `tools/smoke_wheel.py`, before later upgrade
and container checks. Importing `sounddevice` raised `PortAudioError -9999`:
`PulseAudio_Initialize: Can't connect to server`. Installing `libportaudio2`
provides the native library but does not start its PulseAudio backend.

`.github/workflows/ci.yml` now installs PulseAudio and starts a persistent
user daemon with a null sink before the wheel smoke check. `pactl info` makes
server readiness visible in CI logs. The real playback import check remains
enabled; no exception is suppressed and no test is skipped.

## Repository structure and CI implications

- `cli/pinak/` contains the Python CLI, download/queue services, SQLite-backed
  history and Library, playback, local MCP tools, and cloud MCP gateway.
- Local and cloud MCP share typed tool services. Cloud requests cross into a
  persistent per-user subprocess; reproducing quota behavior requires exercising
  that boundary, which the regression tests do.
- `cli/tools/` builds installer bundles and performs installed-wheel, MCP,
  upgrade, container, and performance checks. A successful source test suite
  alone does not establish installation readiness.
- `cli/requirements*-lock.txt` separates core, development, MCP, and cloud
  dependency sets with hashes. The linked failures did not require changing
  dependency versions or hashes.
- `Website/` is a separate Astro/Starlight project with its own npm lockfile,
  browser tests, and GitHub Pages workflow. The supplied links are Python CI
  jobs; they provide no evidence of a current website-browser failure.
- `MCP(Local)/` and `MCP(cloud)/` contain supporting documentation and deployment
  material. Existing audit reports and ignored `.audit-*` files are historical
  evidence, not proof that their findings still apply to this revision.

## Verification

- Reproduced the original quota failure locally before editing.
- Both expanded quota regression cases pass after editing.
- Full Windows/Python 3.10 suite: **703 passed**, **77.60% coverage**; the
  configured minimum remains 75%.
- Ruff lint and format checks, Black, mypy (122 source files), Bandit at
  medium-or-higher severity, actionlint, and Git whitespace checks pass.
- Local MCP benchmark completes, including discovery, paging, metadata,
  and repeated worker start/stop measurements.
- Wheel and source distribution build successfully; `twine check --strict`
  passes for both.
- An isolated PulseAudio server and null sink on local Ubuntu 26.04 support
  real `sounddevice` and `tkinter` imports. WSL's desktop audio and D-Bus session
  were excluded from this isolated check, and the test daemon was stopped.
- A fresh Windows/Python 3.10 wheel environment passes playback imports, CLI
  checks, installed MCP discovery, an actual fixture download, PCM handling,
  queue/history checks, and `pip check`. Its final dependency audit fails as
  described below; the complete smoke command must not be reported as passing.

## Additional finding: Python 3.10 dependency security

The clean-wheel audit reports **43 advisories in two packages**: FileLock
4.1.0 (6) and Pillow 12.3.0 (37). These are the versions selected for Python
3.10, including by the existing lockfile branches. Advisory counts do not
establish that every affected feature is reachable through Pinak.

The audit lists FileLock 4.2.1 and Pillow 13.0.0 as fixed releases. PyPI's
version metadata confirms that both require Python >=3.11:
[FileLock metadata](https://pypi.org/pypi/filelock/4.2.1/json),
[Pillow metadata](https://pypi.org/pypi/pillow/13.0.0/json).
The currently locked FileLock 4.2.4 also requires Python >=3.11.

This finding is separate from the supplied job failures: the Linux installation
job uses Python 3.11 and failed earlier at audio initialization, while the
Python 3.10 matrix jobs do not audit installed dependencies. No advisories were
suppressed and no compatibility metadata was bypassed.

Resolving this fully needs a Python-support decision: move the supported minimum
to 3.11 and raise secure dependency floors, or maintain tested compatible
backports. Dropping advertised Python 3.10 support is a compatibility change
and has not been folded into this targeted CI fix.

## Remaining validation boundaries

GitHub Actions had not been rerun for these changes at the time of analysis. The complete
Linux/macOS/Python-version matrix and later Linux upgrade/container steps still
need confirmation on CI. Docker Desktop's local Linux engine was unavailable.
Website browser tests were not rerun because this fix changes no website code.

Storage quotas remain soft: fresh admission does not reserve disk space, and
active downloads are checked by the existing periodic monitor. Recursive disk
scans now occur for each new admission, trading that scan cost for current
capacity information. This change does not impose a filesystem-level quota.
