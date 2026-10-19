# Cloud verification record

## Current evidence

Runtime and documentation are implemented; deployment acceptance is in progress.
Do not describe this edition as a verified hosted service or universally compatible client integration.
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
- Docker Desktop startup was attempted, but the Linux engine socket was still
  unavailable. Image execution and native VPS/Render acceptance remain pending.
- CI at source `9461320` built the Linux cloud image successfully. Its remote
  smoke client initially lacked the optional MCP dependencies on the runner;
  the workflow now explicitly installs the hashed cloud lock before that check.
  Do not confuse an image build with a completed runtime acceptance test.

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
