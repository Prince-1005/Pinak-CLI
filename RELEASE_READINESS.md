# Release readiness — Pinak 1.4.2

This record describes the current release fixes. Historical design notes are in
[PINAK_DOCUMENTATION.md](PINAK_DOCUMENTATION.md); current user instructions are
in [README.md](README.md) and [cli/OPERATIONS.md](cli/OPERATIONS.md).

## Resolution of the final audit findings

- **R01 — Event-independent release verification:** CI uses Gitleaks CLI 8.30.1
  with a fixed SHA256 instead of an action that rejects `release` events. The
  same Git-history scan is required for push, PR, release, and manual callers.
- **R02 — Working secret rules:** `.gitleaks.toml` extends the default rules.
  CI requires a synthetic GitHub-token canary to be detected before scanning
  history. No real credentials are used by the canary.
- **R03 — Contributor hooks:** the nested pre-commit Mypy hook uses repository-root
  paths, and Ruff/Black/Mypy hook revisions match the development lock. The
  operating guide documents installing and running that hook configuration.
- **R04 — Playback prerequisites:** user documentation explains Linux PortAudio,
  matching Tkinter, optional OpenCV, output devices and headless limits. A Linux
  CI job installs the OS prerequisites and checks imports in a clean wheel
  environment without opening windows or playing audio.
- **R05 — Docker context:** `.dockerignore` excludes audit environments, generated
  distributions, caches, local settings and audit outputs. Docker build inputs
  include the license and required package documents/tools. CI builds the
  downloader image and checks its version/help commands.
- **R06 — Current documentation:** source installation uses clone-relative paths;
  the project tree and command lists include the media/IPC features, runtime lock,
  tools and release files. History locations distinguish config and data paths.
  Python 3.14 is included in the package classifiers. Old design claims remain
  explicitly historical.
- **R07 — Release identity guard:** `cli/tools/check_release.py` compares package,
  module and manifest versions before verification/build/upload. A GitHub release
  must use `v<VERSION>`; manual publishing requires an exact `version` input.
  Automated regressions cover accepted identities, wrong/missing inputs, and
  version-file drift.
- **R08 — Portable documentation links:** the PyPI long description uses absolute
  repository URLs. Published documentation links to tracked records and the renamed
  historical guide. Local historical audit links use repository paths with GitHub
  line anchors rather than machine-specific editor paths.

## Release policy

Automatic release creation remains disabled in `.github/workflows/release.yml`.
Pushes run CI and do not publish to PyPI. A maintainer must publish a GitHub
release tagged, for example, `v1.4.2`, or manually dispatch `publish.yml` with
`version=1.4.2`. Both paths validate release identity, run the reusable checks,
build and verify fresh distributions, and only then invoke PyPI trusted publishing.

No API token is needed to run the secret scan. PyPI trusted publishing must match
repository `Prince-1005/Pinak-CLI` and workflow `publish.yml`.

## Verification

Local verification on 17 October 2026 passed **461 tests on Python 3.10 and
3.14**, with **76.59% coverage** on 3.14. Ruff, Black, Mypy, Bandit, Actionlint,
the actual repository-root pre-commit Mypy hook, release-identity failure cases,
and secret-detector canary checks passed. The clean wheel check passed entry
points, playback imports, dependency consistency and advisory auditing with no
known vulnerabilities. The rebuilt wheel matches all application source modules.
Docker's local Linux engine was unavailable; its build and entry-point checks
are enforced by the new Linux CI installation job.

The first GitHub run also exposed POSIX type-check failures in Windows API
branches, a background updater racing with isolated configuration tests, and
vulnerable setuptools supplied by older Python bootstrap environments. Platform
guards now pass explicit Linux/macOS/Windows type checks; REPL tests suppress the
uncontrolled update worker. Development/build environments require setuptools
83 or later, and clean-wheel/container bootstraps upgrade pip and setuptools
before auditing the installed environment.

The release check commands are:

```sh
python -m pip install --require-hashes -r cli/requirements-lock.txt
python -m pip install --no-deps -e ./cli
pre-commit run --config cli/.pre-commit-config.yaml mypy --all-files
cd cli
ruff check .
ruff format --check .
black --check --line-length=100 .
mypy pinak --config-file pyproject.toml
pytest --cov=pinak --cov-fail-under=75
python -m build --outdir release-dist/1.4.2
python -m twine check --strict release-dist/1.4.2/*
python tools/smoke_wheel.py release-dist/1.4.2
```

On a host with the playback prerequisites installed, add
`--check-playback-imports` to the wheel smoke command. Linux CI also builds and
runs the Docker downloader image. Optional GUI/audio imports do not prove a
physical display or speaker is available; use `pinak --doctor` on the target
device. Source and PyPI versions may differ until a maintainer publishes.
