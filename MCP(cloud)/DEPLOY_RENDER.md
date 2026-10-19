# Deploy to your own Render account

This guide targets one Docker web service with one persistent disk. Check the
recorded [verification status](VERIFICATION.md); do not treat an unexecuted
provider setup as certified. Persistent disks require an eligible service plan;
review current [Render disk documentation](https://render.com/docs/disks) and
billing before creating resources. Pinak supplies neither a hosting account nor
credits. Disk-backed services run as a single instance.

## Prepare a small deployment repository

Download/extract and verify the cloud installer ZIP. Create your own private Git
repository and put the extracted deployment files, wheel and hashed lock in its
root. Do not upload tokens, `.env`, backups or media. You do not need to clone or
fork the full Pinak repository. Commit the included `.gitignore` first.

Connect that repository to Render and create a Blueprint from `render.yaml`, or
create a Docker web service with the equivalent settings:

- Dockerfile and build context: repository root.
- One instance; no autoscaling, no second worker.
- The template selects Render's paid `1c-2g` compute plan. Review current cost
  and sizing before provisioning; larger concurrent workloads need more resources.
- Persistent disk mounted at `/data`; the template starts with 50 GB. Resize for
  your group before large downloads. One user's 10 GiB soft limit is not the
  entire instance's capacity policy.
- Health path `/healthz`; no build/start override is required. The image reads
  Render's `PORT` and listens on `0.0.0.0`.
- `PINAK_CLOUD_DATA=/data` and `PINAK_CLOUD_URL=https://YOUR-SERVICE.onrender.com`.
  Set URL to the service's actual hostname; replace it with your custom HTTPS
  origin when configured. Do not include `/mcp` in this variable.

Automatic deploys are disabled in the template so committing a replacement wheel
does not interrupt a live download before maintenance. Deploy deliberately after
the backup/stop checks. The template allows 45 seconds for shutdown. Supported
fields are described in [Render's Blueprint reference](https://render.com/docs/blueprint-spec).

Use Render-managed HTTPS; do not run the Compose Caddy service on Render. Keep
the service's admin/SSH shell restricted to administrators. Never add the Docker
socket or privileged host mounts to this deployment.

## Provision users

After deployment, open the service's operator shell and run:

```sh
python -m pinak.mcp_cloud users add alice
python -m pinak.mcp_cloud users list
```

Copy Alice's token privately. Connect a compatible client to
`https://YOUR-SERVICE.onrender.com/mcp` with that user's bearer header. Verify
health, a real download, the resulting file link, and a second user's isolation.
Restart/redeploy once and confirm both queue records and files remain on disk.

## Render-specific operating requirements

- The platform's request or client timeout does not cancel a saved background run.
  Poll `queue_run_status`; do not hold one tool call open for an entire download.
- Client, platform and any added proxy must preserve Authorization and MCP
  protocol headers. A platform or CDN request log might contain `/files/` links;
  restrict log access and avoid third-party URL analytics.
- The persistent disk is not available during image builds. Install software at
  build time, and initialize identities/data at runtime through the entry point.
- Disk snapshots are not a substitute for a consistent SQLite backup. Quiesce
  the service and use [the backup procedure](OPERATIONS.md).
- Disk-backed updates may involve downtime. Stop runs deliberately before
  deployment, check saved work after it, and resume explicitly.
- Export encrypted backups outside this service. Account deletion, disk deletion
  or exhausted storage can otherwise lose all users' records and media.

The first real Render acceptance must record the service configuration, image
revision, HTTPS result, client version, two-user checks, actual file retrieval
and restart persistence in VERIFICATION.md without publishing secrets.
