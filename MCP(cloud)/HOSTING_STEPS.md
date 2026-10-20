# Host Pinak-MCP on your own cloud server

You supply the cloud account and server. Pinak supplies the application and
configuration files. No request or downloaded file needs a Pinak-operated server.
The instructions below are for the supplied cloud installer, not the local-only
stdio installer. Read [verification status](VERIFICATION.md) for tested scope.

## Route A: an Ubuntu VPS or cloud VM

### 1. Prepare your server and hostname

Create an Ubuntu 24.04 x86-64 VM with a persistent disk. For a small pilot, start
with 2 vCPU and 2 GiB RAM, then measure actual use. Create a DNS A record such as
`pinak.example.com` pointing to its public IP. Allow inbound TCP 80 and 443;
restrict SSH access to the administrator. Keep application port 8000 private.

Install Docker Engine and the Compose plugin using
[Docker's Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
On the server, check:

```sh
docker --version
docker compose version
```

Run Docker commands through an authorized account (or prefix with `sudo` if your
host requires it). Docker access is administrative access to the host.

### 2. Transfer and extract the installer

Use the local `pinak-mcp-cloud-install.zip` supplied by the maintainer. A locally
prepared ZIP does not require publishing or pushing the Pinak repository.
Transfer it from your computer:

```sh
scp pinak-mcp-cloud-install.zip SERVER_USER@SERVER_IP:~/
ssh SERVER_USER@SERVER_IP
mkdir -p ~/pinak-cloud
unzip ~/pinak-mcp-cloud-install.zip -d ~/pinak-cloud
cd ~/pinak-cloud
sha256sum -c SHA256SUMS
```

Install the OS `unzip` utility if it is missing. All checksum lines must report
OK. The archive includes dotfiles such as `.env.example` and `.dockerignore`;
do not lose these when copying the extracted folder. Users do not need Git,
Node.js, website assets or the complete Pinak source repository on this VM.

### 3. Set your hostname and limits

```sh
cp .env.example .env
chmod 600 .env
nano .env
```

Replace the two hostname settings:

```dotenv
PINAK_CLOUD_URL=https://pinak.example.com
PINAK_CLOUD_DOMAIN=pinak.example.com
```

Use your actual domain. URL is the HTTPS origin without `/mcp`, query or trailing
slash. DOMAIN is the hostname without `https://`. Set the maximum user count and
storage limit for your disk capacity. The default 10 GiB download limit is a
soft limit per user; leave extra room for temporary files, state and backups.

### 4. Build and start

```sh
docker compose build --pull
docker compose up -d
docker compose ps
curl --fail https://pinak.example.com/healthz
```

The build downloads base/system/Python dependencies. Caddy sets up HTTPS. Health
should return `{"status":"ok"}`; that confirms liveness, not a completed media
download. If it fails, check DNS, inbound ports and the troubleshooting section
of [the VPS guide](DEPLOY_VPS.md).

### 5. Create an individual user token

```sh
docker compose exec app python -m pinak.mcp_cloud users add alice
```

Save the returned token privately. For another person, repeat with a different
name. Do not put tokens in Git, screenshots, tickets or AI chat messages.

### 6. Connect the user's AI application

Enter these values in its remote MCP settings:

- Transport: Streamable HTTP.
- URL: `https://pinak.example.com/mcp`.
- Header name: `Authorization`.
- Header value: `Bearer THE_USER_TOKEN`.

Reload/reconnect and discover 34 tools. The client must support custom bearer
headers. An application requiring only browser OAuth sign-in is not compatible
with this initial authentication mode. Client configuration file shapes vary;
`client.template.json` shows generic fields, not a universal client config.

### 7. Test a download and retrieve it

Ask the AI to queue a public media URL you are authorized to download, start the
queue and check its status. Enqueue alone does not start downloading. Poll at
most once every two seconds under default limits. After success, ask it to call
`file_link` for the job's first file and open the returned link.

The media is stored on **your cloud server**. The link downloads it to the user's
device and expires after five minutes by default. Anyone holding that link can
use it before expiry. The permanent user token is not embedded in the URL.

### 8. Verify persistence and prepare maintenance

After the test run finishes:

```sh
docker compose restart app
```

Reconnect and inspect the saved job/history and file. Create a second user and
confirm their queue cannot see the first user's records. Follow
[operations](OPERATIONS.md) for backups, updates and disk monitoring. Keep the
named data volume: deleting it deletes the users' saved data and downloads.

## Route B: Render managed containers

1. Extract the same ZIP locally and verify its checksums. Create your own small
   private deployment repository containing only the extracted bundle. Keep
   the supplied `.gitignore`; exclude `.env`, tokens, data and backups. This
   repository is yours; it is not a push to Pinak's repository.
2. Connect that deployment repository to your Render account and create a
   Blueprint using its `render.yaml`.
3. Review the paid compute plan and 50 GB persistent disk before provisioning.
   Use one instance and mount the disk at `/data`.
4. Set `PINAK_CLOUD_URL` to the service's actual HTTPS origin, for example
   `https://YOUR-SERVICE.onrender.com`, and deploy. Render supplies HTTPS; do
   not start the Compose Caddy service there.
5. In the service's administrator shell run
   `python -m pinak.mcp_cloud users add alice` and save the token privately.
6. Configure the AI client with the service URL plus `/mcp` and that user's
   Authorization bearer header, as in steps 6–7 above.
7. Test a real download, a file link, a second user and a restart. Follow
   [Render-specific instructions](DEPLOY_RENDER.md) and
   [backup/update procedures](OPERATIONS.md) before sharing access.

The Render recipe still needs native acceptance in an operator-owned account;
the verification record does not claim a live provider deployment was tested.
