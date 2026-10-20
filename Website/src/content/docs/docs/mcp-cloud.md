---
title: Host your own Cloud MCP
description: Deploy a user-operated Pinak-MCP instance with Docker Compose or Render, individual bearer tokens, persistent storage, and expiring file links.
---

You provide and operate the cloud account, server, domain, disk, bandwidth, and credentials. **Pinak does not host a shared cloud MCP or media download service.** Downloads are stored on your server, not initially on the AI user's laptop.

Cloud is intended for a small group of trusted users on **one service instance**. Each user has an individual token, queue, SQLite database, folder, and supervised process. These are not separate OS security users or a sandbox for hostile tenants. Storage admission limits are soft.

Local Compose, HTTPS, real downloads, isolation, and restart persistence have been verified. **Live VPS and Render account deployment remains unverified.** Follow the [verification record](https://github.com/Prince-1005/Pinak-CLI/blob/main/MCP%28cloud%29/VERIFICATION.md) before making production claims.

## 1. Get the Cloud installer

Download **pinak-mcp-cloud-install** from a successful main-branch push [CI run](https://github.com/Prince-1005/Pinak-CLI/actions/workflows/ci.yml). GitHub sign-in is required and artifacts expire after 90 days. Extract all files, including `.env.example`, `.dockerignore`, and `.gitignore`. Verify `SHA256SUMS`. Never trust pull-request artifacts as releases.

The bundle contains a wheel, hashed dependency lock, Dockerfile, Compose/Caddy configuration, Render Blueprint, and hosting guides. You do not need the full Pinak repository. Docker downloads its base image, system packages, and Python dependencies during the build.

## 2. Prepare your VPS

For the documented Ubuntu 24.04 route, start with a persistent disk and a small pilot of 2 vCPU / 2 GiB RAM, then measure your workload. Install Docker Engine and its Compose plugin. Point your own hostname, such as `pinak.example.com`, at the server. Allow ports 80/443, restrict SSH, and keep application port 8000 private.

Upload and extract the bundle on the server. From its folder:

```sh
sha256sum -c SHA256SUMS
cp .env.example .env
chmod 600 .env
```

Edit `.env` with your actual hostname:

```dotenv
PINAK_CLOUD_URL=https://pinak.example.com
PINAK_CLOUD_DOMAIN=pinak.example.com
```

The URL is an HTTPS origin without `/mcp`, query, or trailing slash. Set limits for your server's real capacity and leave disk headroom for temporary files and backups.

## 3. Build and start

```sh
docker compose build --pull
docker compose up -d
docker compose ps
curl --fail https://pinak.example.com/healthz
```

Caddy handles HTTPS in the VPS recipe. Health returning `{"status":"ok"}` confirms liveness, not a successful download. Check DNS and firewall configuration if it fails. For file transfer, prerequisites, and troubleshooting, follow the [complete step-by-step guide](https://github.com/Prince-1005/Pinak-CLI/blob/main/MCP%28cloud%29/HOSTING_STEPS.md).

## 4. Create users and connect

In the administrator's server shell:

```sh
docker compose exec app python -m pinak.mcp_cloud users add alice
```

Save the returned token privately. Create a different user for each person. In a compatible remote MCP client, enter:

- Transport: **Streamable HTTP**.
- URL: `https://pinak.example.com/mcp`.
- Header: `Authorization`.
- Header value: `Bearer THE_USER_TOKEN`.

Replace the domain and token. Clients must support custom bearer headers; OAuth-only and legacy SSE-only clients are outside this setup. The supplied `client.template.json` is a generic example, not a universal application configuration. Reconnect and discover thirty-four tools.

## 5. Download, retrieve, and check persistence

Ask the AI to queue an authorized public media URL, start the queue, and check its status. Poll no faster than once every two seconds under default limits. When complete, ask for `file_link` using the job ID and one-based file index.

The returned HTTPS link retrieves the server's file. It expires after **300 seconds by default** and anyone holding it can use it before expiry. It does not contain the permanent bearer token. Request another link if needed.

For example, ask: “Show my latest download history, then list and search my Pinak Library for the saved audio.” The AI can use `history_list`, `history_show`, `library_list`, and `library_search`. `library_scan` can index only folders inside **your server-side approved roots**; it cannot scan your laptop. Each token sees its own Library database. Bookmark tools return path and time for later playback; Cloud MCP does not open a player in the remote AI client.

Disconnecting the AI client does not stop Cloud workers. Restarting the service interrupts active workers; unfinished records persist and require an explicit new `queue_start`. After the test run completes:

```sh
docker compose restart app
```

Reconnect and inspect the saved job and file. Create a second user and verify their records are separate. Keep the persistent data volume, make backups, and monitor disk space. Do not run replicas or autoscaling against this SQLite deployment.

## Alternative: Render

Create your **own private deployment repository** containing the extracted installer, preserving its dotfiles and excluding secrets/data. Connect it to your Render account and create a Blueprint from `render.yaml`. Review the paid compute and persistent-disk configuration before provisioning; use one instance with the disk mounted at `/data`.

Set `PINAK_CLOUD_URL` to the service's actual HTTPS origin. Render supplies HTTPS; do not run Compose Caddy there. Create a user in the service administrator shell with `python -m pinak.mcp_cloud users add alice`, then connect the client to the origin plus `/mcp` with that user's bearer header. Test a real download, a file link, user isolation, and restart persistence in your account.

Follow the [Render deployment guide](https://github.com/Prince-1005/Pinak-CLI/blob/main/MCP%28cloud%29/DEPLOY_RENDER.md), [operations and backups](https://github.com/Prince-1005/Pinak-CLI/blob/main/MCP%28cloud%29/OPERATIONS.md), and [security boundaries](https://github.com/Prince-1005/Pinak-CLI/blob/main/MCP%28cloud%29/SECURITY.md). If you want media saved directly on your computer, choose [Local MCP](../mcp-local/) instead.
