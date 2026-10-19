# Pinak-MCP Cloud — host your own instance

Pinak provides software and setup instructions. **You own and operate the cloud
account, server, domain, storage, bandwidth and credentials. Pinak hosts no shared
MCP or media-download service.**

This optional edition exposes Streamable HTTP at `https://YOUR-HOST/mcp`.
Several trusted people can use one instance. The administrator gives each person
an individual bearer token; each has a separate queue, SQLite database, download
folder and supervised local MCP process. The existing local `stdio` edition is
documented in [MCP(Local)](<../MCP(Local)/README.md>).

## Start here

For a walkthrough, open [step-by-step hosting](HOSTING_STEPS.md). A maintainer can
also hand you a locally built installer ZIP without pushing code or publishing a
release; use the same steps to transfer and deploy that ZIP.

1. Obtain the `pinak-mcp-cloud-install` bundle from a successful main-branch
   [CI run](https://github.com/Prince-1005/Pinak-CLI/actions/workflows/ci.yml).
   GitHub sign-in is required; artifacts expire after 90 days. Use newer builds
   when needed. Never install an untrusted pull-request artifact.
2. Extract and verify `SHA256SUMS`. The bundle includes a wheel, hashed dependency
   lock, deployment templates and these guides. It excludes the website, media,
   Git history and unrelated repository files. There is no need to clone Pinak.
3. Follow [VPS setup](DEPLOY_VPS.md) or [Render setup](DEPLOY_RENDER.md).
4. Create a user and configure a compatible AI client using the endpoint and that
   person's token. [User and file guide](USERS_AND_FILES.md).
5. Complete the checks in [verification](VERIFICATION.md) before sharing access.

The bundle is a source snapshot identified by its commit and wheel checksum. Its
version may equal an earlier snapshot. Do not assume the PyPI release has these
features; use the supplied wheel. No new package version is implied.

## Capabilities and limits

- Fifteen tools: the fourteen existing queue, history, metadata and diagnostic
  tools plus `file_link(job_id, file_index=1)` for a completed file.
- Downloads run on your server, not on the AI user's laptop. They continue when
  an HTTP client disconnects. Stop/restart of the service interrupts its workers;
  unfinished jobs remain saved and require an explicit new `queue_start`.
- Tokens are operator-issued. Remote clients must support Streamable HTTP and
  custom `Authorization: Bearer ...` headers. OAuth-only and legacy SSE-only
  clients are outside this release. Do not claim every AI app supports it.
- One gateway process and one service instance. SQLite and per-user supervision
  are not designed for replicas, shared network filesystems or autoscaling.
- Intended for a small group of trusted users, not public registration or hostile
  tenants. Separate processes and tool checks are not separate OS security users.
- Defaults: 20 provisioned users, one active download run per user, eight active
  tool calls per user, 120 MCP HTTP requests per minute per user, 1,000 saved jobs,
  and a 10 GiB **soft** download-area limit per user. Provision disk and memory
  for the actual group; these defaults do not reserve 200 GiB automatically.
- File links expire after 300 seconds and authorize anyone possessing the link.
  They are not an account login or a promise of private delivery through the AI
  provider. Media is served over HTTPS directly from your instance.

## Guides

- [Architecture, interfaces and implementation phases](IMPLEMENTATION_PLAN.md)
- [VPS / AWS EC2 / Google Compute Engine / Azure VM](DEPLOY_VPS.md)
- [Render Docker service with persistent disk](DEPLOY_RENDER.md)
- [Users, client connection and downloaded files](USERS_AND_FILES.md)
- [Operations, backups, updates and recovery](OPERATIONS.md)
- [Security boundaries and outbound networking](SECURITY.md)
- [Verification evidence and remaining release gates](VERIFICATION.md)

Read the verification status before calling a deployment production-ready.
The instructions describe the intended deployment; native cloud-account
acceptance must be recorded with provider, date, revision and results.
