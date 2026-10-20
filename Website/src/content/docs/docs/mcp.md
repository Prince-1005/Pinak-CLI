---
title: Choose Local or Cloud MCP
description: Choose where Pinak-MCP runs, understand client requirements, and manage downloads from your AI application.
---

Pinak-MCP connects an AI application to Pinak's download engine and durable SQLite queue through the Model Context Protocol. **Pinak provides software, not a shared hosted service.**

## Choose where downloads happen

- **[Local MCP](../mcp-local/):** your AI application launches a Python process through stdio. Jobs, history, and files live on your device. Repository documentation is in `MCP(Local)`.
- **[Cloud MCP](../mcp-cloud/):** you operate a server with an HTTPS Streamable HTTP endpoint. Several trusted users get separate tokens, queues, databases, folders, and supervised processes. Files live on that server. Repository documentation is in `MCP(cloud)`.

Local requires a client that launches local processes. Cloud requires Streamable HTTP and custom bearer headers. Neither mode guarantees compatibility with every AI application. Cloud does not currently implement OAuth or legacy SSE transport.

## Obtain an installer

1. Open [GitHub CI builds](https://github.com/Prince-1005/Pinak-CLI/actions/workflows/ci.yml).
2. Choose a successful **main-branch push** run, not a pull-request build.
3. Download **pinak-mcp-install** for Local or **pinak-mcp-cloud-install** for Cloud.
4. Extract the artifact, verify `SHA256SUMS`, and read `INSTALL.md` and `BUILD-INFO.json`.

GitHub sign-in is required. Artifacts expire after 90 days; choose a newer successful run if needed. Bundles exclude repository history, website assets, and plans. They include Pinak's shared engine/CLI. Pip and Docker still need network access to fetch dependencies.

These bundles are development snapshots identified by revision and wheel checksum. The source version can equal an older snapshot. Do not assume the published PyPI release contains MCP; use the supplied wheel and its instructions.

## A typical conversation

Ask your AI application:

> Queue this media URL, start the queue, and show me its download status.

Supply a supported URL for media you own or have permission to download. `queue_add` saves the request; **it does not start a download**. `queue_start` accepts a run; success there does not mean the media has finished downloading. Inspect `queue_run_status` and then `queue_show`.

You can also ask:

> Show my recent download history. Then search my Pinak Library for “guitar” and show any bookmarks on the matching item.

`history_list` returns recent records; `history_show` inspects one record. `library_scan` indexes only a folder inside the MCP edition’s approved roots, and Library search, tags, ordered collections, bookmarks, relink, and forget tools organize those indexed files. Local MCP sees approved files on your computer. Cloud MCP sees approved files on **your server**, not your laptop. MCP returns playback paths and bookmark times; use the Pinak CLI/player on a device with a terminal and media output to play them.

## Tools available in both modes

- **Inspect:** `server_info`, `diagnostics`, `media_info`, `history_list`, `history_show`.
- **Save and review:** `queue_add`, `queue_list`, `queue_show`.
- **Run and track:** `queue_start`, `queue_run_status`, `queue_stop`.
- **Maintain:** `queue_retry`, `queue_cancel`, `queue_remove`, `queue_clean_completed`.
- **Library:** `library_scan`, `library_list`, `library_search`, `library_show`, tag, collection, bookmark, relink, and forget tools.

`queue_cancel` prevents waiting jobs from running; use `queue_stop` for a run owned by the current adapter. Retry applies to failed jobs. Removing records or cleaning completed records keeps downloaded files and history. Local CLI and MCP share the user's queue; Cloud users have separate queues. Tool input schemas and returned errors are authoritative.

Cloud adds **`file_link(job_id, file_index=1)`**, producing a short-lived HTTPS link for a completed file. It does not embed the user's permanent bearer token. Anyone holding the link can use it before expiry; treat it as a temporary credential.

## What persists

Saved jobs and options survive restarts. Local workers belong to the local host process; closing it interrupts work. A Cloud client disconnect does not stop server workers. Stopping or restarting the Cloud service interrupts workers; unfinished jobs remain saved and require a new explicit `queue_start`. Persistence is not a promise that interrupted work keeps running or resumes automatically.

## Privacy and verified scope

Media connects directly to source platforms from the device or server doing the work. The AI provider may receive prompts, filenames, returned metadata, and any file links included in tool results.

Local SDK interoperability and Windows Cursor checks passed; this is not universal client certification. Cloud passed local Compose, HTTPS, real download, isolation, and restart checks. A live VPS/Render account deployment has not been verified. See the repository's [Local verification](https://github.com/Prince-1005/Pinak-CLI/blob/main/MCP%28Local%29/VERIFICATION.md) and [Cloud verification](https://github.com/Prince-1005/Pinak-CLI/blob/main/MCP%28cloud%29/VERIFICATION.md).
