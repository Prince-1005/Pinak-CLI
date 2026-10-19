# Deploy on your own VPS or cloud VM

Status and acceptance evidence: [VERIFICATION.md](VERIFICATION.md). Use an Ubuntu
24.04 LTS x86-64 VM, persistent local disk, Docker Engine and the Compose plugin.
Start with at least 2 vCPU / 2 GiB RAM for a small pilot and measure your workload.
Video merging, multiple users and large media need more memory, CPU and disk.
Install Docker from its [official Ubuntu guide](https://docs.docker.com/engine/install/ubuntu/).

## Prepare the host

Create a DNS A record, for example `pinak.example.com`, pointing to the VM. Only add
an AAAA record when IPv6 is actually routed to that server. Allow inbound TCP
80 and 443 for HTTPS and restrict SSH to your administrative addresses. The app's
8000 port must remain private. On AWS use security groups, on GCP use VPC firewall
rules, and on Azure use the VM's network security group for the same policy.
Keep the machine's cloud instance role minimally privileged; downloads do not
need cloud-management credentials.

Download/extract the cloud installer to a permanent directory on the server.
Verify checksums before running files:

```sh
sha256sum -c SHA256SUMS
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set both `PINAK_CLOUD_DOMAIN=pinak.example.com` and
`PINAK_CLOUD_URL=https://pinak.example.com`. Use the hostname only for DOMAIN;
use the origin with `https://` and no path/trailing slash for URL. Choose user
and storage limits that fit your disk. The default per-user limit is not a disk
reservation and is not a hard filesystem quota.

## Build and start

```sh
docker compose build --pull
docker compose up -d
docker compose ps
curl --fail https://pinak.example.com/healthz
```

The app has only an internal Compose port. Caddy obtains/renews certificates and
terminates public HTTPS. There is no Caddy access log containing download tokens.
The initial container entry point prepares `/data` ownership, then drops to UID
10001 before launching Python. Persist the named `pinak-data` volume; deleting it
deletes identities, queues and media. Keep Caddy certificate volumes too.

## Add people and connect

```sh
docker compose exec app python -m pinak.mcp_cloud users add alice
docker compose exec app python -m pinak.mcp_cloud users add bob
```

Each command prints a different token once. Deliver it privately to that person;
do not paste tokens into tickets, repository files or AI prompts. Configure the
client endpoint `https://pinak.example.com/mcp` with their Authorization header.
Complete the first download and two-user checks in [USERS_AND_FILES.md](USERS_AND_FILES.md).

## Diagnose setup problems

- Certificate failure: verify DNS, port 80/443 access, no conflicting service and
  `docker compose logs --tail=100 https`. Do not disable HTTPS to bypass it.
- 403: public URL, Host or Origin differs. Correct the canonical origin rather
  than accepting every host/origin.
- 401: token absent/revoked, or client cannot send custom bearer headers.
- App unhealthy: inspect `docker compose logs --tail=100 app`, disk permissions
  and available space. Health means the process answers, not that downloads work.
- Source failure: some media platforms restrict datacenter IPs. Hosting does not
  bypass login, DRM, geographic or source-site restrictions.

Proceed to [operations](OPERATIONS.md) before inviting the whole group.
