# Cloud verification record

## Current evidence

Runtime, documentation and local deployment verification are implemented.
Do not describe this edition as a Pinak-hosted service or universally compatible client integration.
No Pinak-managed server is deployed or required.

Automated cloud coverage includes validated settings, individual token hashes,
rotation/revocation, expired/modified/out-of-root file denial, private-address
proxy denial, real per-user MCP subprocesses, fifteen-tool discovery, separate
queue/database state, protected output roots, file ranges, actual audio download
through a test-wired proxy with PCM verification, and data/link persistence after
a gateway restart. A test-only connector maps a synthetic public source to a
local WAV fixture; production has no private-destination bypass setting.

Local Windows / Python 3.12 evidence from this implementation:

- Full existing-plus-cloud regression passed with 76.94% coverage (75% gate).
- Cloud tests passed, including official SDK calls over real local HTTP,
  actual WAV/PCM delivery, private metadata-address redirect denial, rate/body
  bounds, quota admission and receipt replay after a limit is reached.
- Additional recovery checks cover an actually killed user adapter, preserved
  queue state after replacement, revocation shutdown without affecting another
  user, refusal of a second gateway supervisor, and a quiesced archive restore.
- Whole-package Mypy passed; changed Python files passed Ruff, Ruff formatting
  and Black. Bandit reported no medium/high cloud findings.
- Application wheel built and strict Twine validation passed. The cloud bundle's
  checksums, documentation links, JSON templates and wheel packaging isolation
  passed. Extracted-bundle Docker Compose configuration validated.
- Clean wheel installation passed local stdio discovery and an actual download
  with PCM/queue/history checks when FFmpeg was explicitly placed on PATH.
  An earlier unprovisioned attempt timed out while resolving media prerequisites;
  installation instructions require explicit FFmpeg provisioning where needed.
- Docker Desktop's Linux engine subsequently became available. The exact local
  installer image and revised Compose smoke helper passed as described below.
- CI at source `9461320` built the Linux cloud image successfully. Its remote
  smoke client initially lacked the optional MCP dependencies on the runner;
  the workflow now explicitly installs the hashed cloud lock before that check.
  Do not confuse an image build with a completed runtime acceptance test.

CI at source `fcd48c4` subsequently passed **all 18 jobs**, including Windows,
macOS and Linux on Python 3.10–3.14, security checks and clean package installation.
Its Linux cloud container check verified a service running as UID 10001, official
remote SDK initialization/discovery, fifteen tools, separate users and queue/data
persistence after container restart. The job published a cloud installer artifact.
[CI evidence](https://github.com/Prince-1005/Pinak-CLI/actions/runs/39275702505).

Installer delivery improvements add Compose capability/verification adjustments, an
explicit ZIP output for the installer, allowlisted deployment templates that
exclude ignored local secrets, and a step-by-step hosting walkthrough. Packaging
tests cover dotfiles, checksums, secret exclusion and archive self-inclusion.
These improvements are included in the repository delivery.

## Final local deployment verification — 2026-10-20

- Seventeen cloud/packaging tests passed against the final local source. Formatting,
  lint checks, strict wheel metadata validation, installer checksums, required
  dotfiles and documentation links passed. Secret-exclusion and archive
  self-inclusion tests passed.
- Built the exact installer image locally as `pinak-cloud-verify:local-20261020`.
  Ran the revised Compose smoke helper with the supplied capability restrictions,
  non-root UID 10001, health check and persistent volume. Official SDK discovery,
  fifteen tools, two-user isolation and restart persistence passed.
- Started the supplied Caddy reverse proxy and app together on a loopback-only
  HTTPS port. The test client validated the temporary local CA certificate;
  certificate verification remained enabled and the Windows trust store was not
  modified. Authenticated MCP discovery, a real public HTTPS source download,
  completed-file retrieval and wrong-token 401 rejection passed.
- The delivered WAV's 13,228 PCM bytes matched the official CPython reference
  fixture byte-for-byte: SHA256
  `65ec0e77ab753cacc20f37a6c6b9987ca159044c0fddfc6053ceb8ce1d8ec31f`.
  Source: `https://raw.githubusercontent.com/python/cpython/3.12/Lib/test/audiodata/pluck-pcm16.wav`.
- A separate disposable container passed the Render-style `PORT=10000` and
  persistent `/data` contract, remote SDK calls, user isolation and restart.
  The Render template validated against Render's published JSON schema at
  `https://render.com/schema/render.yaml.json`.
- Test containers, networks and volumes were removed. Only local image/build
  caches and verification logs remain; no Pinak cloud service was deployed.

Local evidence: `cli/.venv/cloud-compose-verify.log`,
`cli/.venv/cloud-https-verification/result.json`, and
`cli/.venv/cloud-render-environment-result.json`. These are local test artifacts,
not credentials or files that users need to install.

## Provider boundary

Delivery scope: the tested installer and hosting guide are complete. Live
VPS/Render account deployment is deferred. The checks below remain prerequisites
for any future claim of native provider certification.

No live VPS or Render account was provisioned. Public DNS/ACME certificate issuance,
provider billing/control-panel behavior and a named third-party AI client's remote
configuration have not been certified by these checks. The Render recipe and VPS
guide use the tested container contracts; actual account deployment remains an
operator step. This limitation does not require the user to run our software
tests; the local verification above was performed by the implementer.

These tests do not certify every external extractor, client, proxy or provider.

## Required release evidence

- Ruff, both formatter checks, Mypy and relevant security checks.
- Existing local MCP/core regression, including normal queue shutdown/recovery.
- Remote SDK client handshake and tool calls, not just direct service functions.
- Two users: IDs/request keys, records, run stop ownership and file access.
- Quotas/rate/body bounds; source redirect/private-address blocking; disk failure.
- Cloud installer wheel/lock/templates/checksums and a clean install.
- Docker image startup as non-root, health, persistent data and graceful stop.
- Compose topology/configuration and a clean VPS with real DNS/HTTPS/client.
- Render single-instance deployment with disk, real HTTPS/client and restart.
- Backup/restore and update rehearsal on disposable data.

Provider acceptance needs an operator-owned account/domain and actual deployments.
Record revision, provider/plan, OS/image, client/version, date, commands, outcomes
and remaining limits, without credentials, private media or capability URLs.
Until that evidence exists, provider instructions are setup recipes awaiting
native acceptance, not a promise that every deployment path has passed.
