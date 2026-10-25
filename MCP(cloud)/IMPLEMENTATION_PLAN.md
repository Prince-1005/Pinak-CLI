# Cloud implementation plan and delivery record

## Goal and fixed decisions

Provide an optional user-operated cloud server. Pinak will not operate accounts,
servers, storage or a public media-download API. First hosting targets are Docker
Compose on an Ubuntu VPS/cloud VM and one Render Docker web service with a disk.
Use individual bearer tokens for several trusted users. OAuth, Kubernetes,
serverless functions, public registration, replicas and object storage are deferred.

Runtime belongs to the Python package, under `pinak.mcp_cloud`, so it is included
in the application wheel. This folder contains operator docs and deployment
examples. Keep package version and changelog unchanged for this implementation.

## Architecture and interfaces

`AI client → HTTPS ingress → authenticated /mcp gateway → per-user stdio adapter
→ existing durable queue/engine → per-user files`.

The gateway uses the official pinned MCP SDK's stateless Streamable HTTP manager.
It forwards calls over SDK ClientSession to a lifespan-owned local adapter for each
user. Each adapter receives its own environment before Python imports core history
and queue modules. Never switch process-global database paths between HTTP calls.
HTTP disconnects do not own adapter lifetime. The adapter owns the worker and its
existing watchdog, stop, lock and recovery semantics.

Public interfaces:

- `python -m pinak.mcp_cloud serve --host 127.0.0.1 --port 8000`.
- `python -m pinak.mcp_cloud users add|rotate|revoke NAME`; `users list`.
- `POST /mcp` (MCP transport), authenticated on every request. SDK handles protocol
  negotiation and unsupported methods. No custom REST queue API.
- `GET /healthz`: generic liveness, no secrets or storage diagnostics.
- `GET|HEAD /files/TEMPORARY-CAPABILITY`: one completed file, expiration and
  identity checks, range support, attachment delivery and no caching.
- Existing fourteen MCP tools retain their schemas and result envelope. In cloud
  mode `server_info` reports transport, user, limits and disconnect behavior.
- `file_link(job_id, file_index=1)` returns a 300-second file capability, expiry,
  byte size and an explicit sharing warning. No arbitrary path input.

Operator configuration is environment-based. `PINAK_CLOUD_URL` is the public
HTTPS origin; `PINAK_CLOUD_DATA` is an absolute persistent-storage path. Remaining
limits are documented in the environment template. HTTP is allowed only for an
explicitly configured localhost test. One gateway lock prevents two processes
from supervising the same data directory.

## Phases and acceptance

### 1. Foundation and identity

Implement validated settings and a separate versioned operator registry. Generate
256-bit random tokens, print once on explicit admin request, retain hashes, and
provide rotation/revocation without a remote administrator endpoint. Validate user
names before constructing directories. Acceptance: invalid settings fail closed;
tokens cannot authenticate after revocation; plaintext tokens are absent from DB.

### 2. Remote transport and isolated workers

Implement authenticated SDK Streamable HTTP, Host/Origin validation, bounded body
size, rate limiting and per-user adapters with dedicated data/config/cache/output
paths. Reuse the current tool service and durable mutation receipts. Acceptance:
two users may both have job 1 and the same request key without sharing state;
cross-user file paths fail; reconnect can inspect and stop its own run.

### 3. Storage and file retrieval

Add job-count admission, soft storage admission and periodic cooperative stop when
the download directory exceeds its limit. Do not silently delete files. Serve
only files belonging to completed jobs through expiring capabilities; validate
size/mtime and containment again on redemption. Rotation/revocation invalidates
outstanding links. Acceptance: metadata-only calls never return media bytes;
expired, modified, missing and out-of-root files cannot be retrieved; ranges work.

### 4. Network and deployment

Route downloader HTTP(S) through a loopback proxy which rejects private/loopback/
link-local/reserved addresses, validates every new target and pins the resolved
public address when connecting. Preserve certificate checks. Package a non-root
runtime with FFmpeg, a PID supervisor, persistent storage and HTTPS templates.
Acceptance: actual download passes through the proxy, private targets and redirect
targets fail, shutdown leaves no worker claiming jobs, no app port is exposed on VPS.
See the documented sandbox limitations before hosting untrusted people.

### 5. Installer, documentation and operations

Produce a separate compact cloud installer artifact containing the application
wheel, hashed runtime dependency lock, templates, guides and checksums. Both
operators can use that artifact without Pinak's repository. For Render, a user
creates their own small private deployment repository containing the bundle.
Document user provisioning, client headers, downloads, backup/restore, update,
rollback, capacity management and platform-specific health/ingress behavior.

### 6. Verification and release gate

Run lint/type checks, local MCP regression, real remote MCP calls, actual fixture
download/PCM validation, two-user isolation, file retrieval and restart checks.
Build the wheel, inspect contents and verify the extracted cloud bundle. Build
and exercise Docker/Compose, then deploy each guide to a clean provider account
with a real domain/certificate and record acceptance. Keep unexecuted platform
checks explicitly pending; a passing unit test is not cloud-provider certification.

## Commands and dependencies

From `cli/`: `python -m pytest tests/test_mcp_cloud.py`; `ruff check .`;
`ruff format --check .`; `black --check .`; `mypy pinak`; `python -m build`.
Use `python tools/package_cloud.py DIST --output OUTPUT --source-revision SHA`
after the wheel is built. Docker templates build from the extracted output.

For a private local delivery, add `--archive /absolute/path/pinak-mcp-cloud-install.zip`
to the packaging command. The ZIP is created outside OUTPUT and includes required
dotfiles. Use a fresh output directory and ZIP filename; existing outputs are
refused to prevent mixing stale builds. Label uncommitted source revisions as
local working trees, and verify the resulting SHA256SUMS before transferring.
No push or release publication is required to create or use that local archive.

Dependencies: Python 3.11+, pinned MCP 2.3.0 and Uvicorn for the optional cloud
extra; Python 3.12 in Docker, system FFmpeg/FFprobe, persistent local filesystem,
HTTPS ingress and a client supporting remote HTTP with bearer headers. No hosted
Pinak dependency, download relay service, Redis or external database is required.

Completion notes and exact verification results belong in [VERIFICATION.md](VERIFICATION.md).
