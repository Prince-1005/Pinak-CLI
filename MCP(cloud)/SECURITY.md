# Security and trust boundaries

This release is for a small group of **trusted users on an operator-owned host**.
It is not a public SaaS, hostile-tenant sandbox or unlimited downloader. The
operator can access every user's media/database and is responsible for the host,
network, domain, costs and access. Pinak receives none of these credentials.

## Inbound requests

HTTPS terminates at Caddy or the managed host. Keep the application port private.
Only operator shell commands administer identities; no remote signup/admin API.
Use a separate random token for every person. Every MCP HTTP request is checked
against the enabled registry record; a protocol session identifier never grants
access by itself. SDK stateless transport avoids shared session ownership between
users. Accept only the configured Host and Origin, with the generic health probe
as the sole exception. No wildcard CORS policy is provided.

Requests are bounded to 64 KiB and rate-limited after authentication. Tool inputs
and outputs retain core validation and size limits. Use a provider/edge firewall
for internet denial-of-service protection; application limits do not protect
against arbitrary TCP/HTTP volume. Keep dependency locks and host software updated.

## User data and processes

Each authenticated identity maps to an operator-created name, independent DB,
config/cache/output paths and stdio process. Do not accept tenant names, data-root
overrides, shell commands, downloader dictionaries or arbitrary file paths from
an HTTP user. Subprocess launch uses a small environment allowlist, not cloud
account credentials. Tokens and link capabilities are hashed in operator SQLite.

Processes run under the same non-root OS account inside one container. This is
logical tool-level isolation, not separate OS/container users. An operator, host
compromise, vulnerable media parser or deliberately modified software can cross
that boundary. Do not invite untrusted public users or mount sensitive host data.

## Outbound downloads

Cloud users can submit only HTTP(S) URLs without credentials on ports 80/443.
The bundled loopback proxy resolves each target, rejects any nonpublic address
(including metadata/link-local/loopback/private addresses), and connects to a
validated numeric address so a second DNS lookup cannot redirect it privately.
Redirects require new proxy connections with the same checks. The downloader
receives an explicit proxy setting; urllib-based image fetching inherits it.
TLS verification remains enabled. Do not disable certificate checks to fix media.

This proxy protects the supported Python HTTP(S) download routes. It is **not an
OS network sandbox** and does not prove every external binary/plugin honors a
proxy. FFmpeg and future extractors may add network paths. For stronger isolation,
apply host/provider egress restrictions that deny private and cloud metadata
networks for the entire container, remove privileged instance roles, and verify
all media paths you enable. Fail closed for unsupported protocols rather than
assuming a URL check makes arbitrary remote processing safe.

## Files and secrets

Permanent tokens only belong in protected client settings. File links contain a
different random bearer capability, expire in five minutes by default, and may be
seen by an AI provider if returned in a chat. Anyone seeing one can use it before
expiry. Do not treat it as a private account-bound browser session. Revoke/rotate
invalidates links. Link retrieval rechecks user status, file root and identity;
no directory listing is exposed. No-cache and no-referrer headers reduce leakage
but cannot erase copies someone already downloaded or URLs a provider logged.

Exclude `.env`, databases, caches, downloads and backups from Git and images.
The provided deployment repo ignore file does so. Restrict logs/backups and
rotate secrets after exposure or restoring an old registry. Metadata and filenames
remain untrusted data; AI clients should not interpret them as instructions.

## Before sharing access

Verify HTTPS, wrong-token rejection, user isolation, private destination rejection,
file expiry/revocation, restart persistence, operator backups and available disk.
Record actual client/platform versions. The [verification record](VERIFICATION.md)
distinguishes completed checks from work still required for production acceptance.
