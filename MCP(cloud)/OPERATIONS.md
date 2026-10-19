# Operating your instance

## Configuration and capacity

The environment template contains all supported limits:

- `PINAK_CLOUD_URL`: required canonical HTTPS origin, no path/query/credentials.
- `PINAK_CLOUD_DATA`: persistent absolute root; the container requires `/data`.
- `PINAK_CLOUD_MAX_USERS`: 20, valid 1–100. Disabled users still count.
- `PINAK_CLOUD_STORAGE_BYTES`: 10737418240, per-user **soft** download-area limit.
- `PINAK_CLOUD_MAX_JOBS`: 1000 retained records per user, including completed jobs.
- `PINAK_CLOUD_CALLS_PER_MINUTE`: 120 MCP HTTP requests per user; handshake/list
  requests count too. 429 returns Retry-After. This resets on service restart.
- `PINAK_CLOUD_LINK_SECONDS`: 300, valid 30–3600.

Use one app instance and one gateway process. Do not run `uvicorn --workers N`,
replicas or a shared SQLite volume across hosts. The gateway startup lock rejects
two supervisors using the same data root. Each user's adapter may retain memory
while the service runs; the provisioned-user maximum is not a memory reservation.
Tune container memory/pids/CPU and group size for measured concurrent work.

Storage checks block new queue adds/starts at the configured limit and request a
cooperative stop of an active run after periodic checks. Download/postprocessing
buffers and graceful shutdown can exceed that limit. State, logs, caches, backups
and temporary files are not counted as download storage. Monitor the entire disk
and maintain headroom; use OS/filesystem hard quotas where strict enforcement is
required. Do not claim the application provides an exact hard byte ceiling.

## Health and logs

`/healthz` returns only liveness; it deliberately accepts platform health probes
without authentication and reveals no state. Use authenticated `diagnostics` for
per-user readiness and an actual fixture download for an end-to-end check.

The app and Caddy templates disable access logs to avoid file-capability URLs.
Per-user runtime logs use existing bounded rotating Pinak logging under that
user's platform log directory. Child stderr is discarded instead of creating an
unbounded second log. Inspect app startup failures through provider/container logs.
Do not enable request-header/body or URL logging when troubleshooting tokens.
Provider ingress logs are controlled by the operator and may still record URLs.

## Stop and recover

An AI client closing does not stop its run. Use `queue_stop` for normal user stop.
For maintenance, ask users to stop their runs, verify terminal run states, then:

```sh
docker compose stop app
```

The adapter closes its owned worker using existing grace/watchdog handling.
Partial files remain. After a restart, users inspect their queues and explicitly
start unfinished jobs. There is no automatic restart of every queued download.
If forcibly killed, stale running jobs are recovered only by an exclusive runner
after taking the normal queue lock. Never delete lock/database files to force it.

## Consistent backups (VPS)

Stop the app before copying data, including registry and every user database.
Use a stopped service's volume through a one-off Compose command; no SQLite writer
may be running during this whole-root backup. The copy includes DB WAL sidecars,
media, policies and token hashes. Store the encrypted backup off the server.

```sh
docker compose stop app
mkdir -p backups
chmod 700 backups
docker compose run --rm --no-deps --entrypoint tar app -C /data -czf - . > backups/pinak-data.tar.gz
docker compose up -d app
```

Protect and verify the archive, then copy it to your chosen private backup store.
Keep an immutable copy of the matching installer ZIP and its checksum/revision.
For Render first stop all users' runs and enable the service's paid maintenance
mode to block incoming MCP mutations. Allow in-flight calls to finish and confirm
no worker is active. With all writers quiesced, use the operator shell:

```sh
tar -C /data -czf /tmp/pinak-data.tar.gz .
sha256sum /tmp/pinak-data.tar.gz
```

Transfer `/tmp/pinak-data.tar.gz` over the service's configured SSH/SCP connection,
verify its hash locally, encrypt/store it off the service, then disable maintenance
mode. Remove the temporary copy after confirming the backup. Never tar a changing
SQLite database: if you cannot quiesce every writer, postpone this procedure and
take individual SQLite backup-API copies instead. Render documents private file
transfer in its [disk guide](https://render.com/docs/disks).
Do not expose a backup endpoint, put backups in the
deployment Git repository, or assume a live filesystem snapshot is SQLite-safe.

Restore only into a stopped service. Preserve current data first, validate the
archive, extract the entire root with correct ownership and start compatible code.
Restoration loses changes after the snapshot and can restore previously revoked
credentials; rotate tokens and verify user access after a restore. Rehearse this
in a disposable instance before relying on a backup. Never automatically restore
or reset a busy/corrupt database.

## Updates and rollback

1. Verify a new bundle's source revision and checksums; retain the current bundle.
2. Stop downloads and the app, then take a consistent backup.
3. Replace the wheel/lock/templates with the new bundle, preserve `.env` and data,
   build the image and start the service. On Render commit the new bundle to your
   private deployment repo and deploy after the same quiescing/backup steps.
4. Check health, both users' queue/history, a download, a file link and token rules.
   Resume unfinished jobs explicitly.
5. If incompatible, stop all writers and restore compatible code. Restore a
   database snapshot only when necessary and after accepting post-backup data loss.

Do not use `pip install pinak-cli` inside a running container as an update. Images
are rebuilt from the supplied wheel and dependency lock. Source snapshots may
share version 2.0.0; identify the installed build by revision and image identity.

## Common failures

401: fix token/header; 403: fix Host/Origin or a blocked destination; 429: wait.
`RUNNER_BUSY`: another run owns that user's queue; inspect it instead of killing
Python processes. `STORAGE_LIMIT`/`JOB_LIMIT`: reclaim space or inactive records
deliberately. `ADAPTER_UNAVAILABLE`: inspect startup/storage and reconcile pending
mutations before retrying. Disk full/read-only: preserve existing records and
partials, repair storage, then inspect/retry failed work. Source restrictions or
missing FFmpeg must remain truthful failed jobs, never fake success.
