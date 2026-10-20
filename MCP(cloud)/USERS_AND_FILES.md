# Users, clients and files

## Operator actions

Run these inside the app container (prefix with `docker compose exec app` on VPS):

```sh
python -m pinak.mcp_cloud users add alice
python -m pinak.mcp_cloud users list
python -m pinak.mcp_cloud users rotate alice
python -m pinak.mcp_cloud users revoke alice
```

Names contain lowercase letters, numbers, `_` or `-`, start with a letter and have
at most 32 characters. Creation and rotation print a random token once. The
registry stores its SHA-256 hash; the token cannot be recovered by listing users.
Save it in a password manager and send it privately. Rotation replaces the old
token immediately and invalidates that user's existing file links. Revocation
disables all new requests, invalidates links and requests adapter/worker shutdown
within the two-second supervisor check plus the normal graceful-stop interval.
It preserves files and records. Rotation re-enables a revoked account; a running
operation that was already accepted is not rolled back by token rotation.

There is no remote administrator tool, registration page, shared token or API to
delete accounts/media. Account deletion and file retention are deliberate operator
tasks after stopping that user's work. Disabled accounts still count toward the
configured maximum; raise it deliberately if needed.

## Connect an AI application

Your client must support **Streamable HTTP with a custom Authorization header**:

```json
{
  "transport": "streamable-http",
  "url": "https://pinak.example.com/mcp",
  "headers": {"Authorization": "Bearer YOUR_INDIVIDUAL_TOKEN"}
}
```

These are generic connection fields, not a universal client configuration file.
Translate them to your application's documented settings. Keep the secret in the
client's protected settings or secret facility; do not enter it into a chat.
Discover thirty-four tools. `server_info` identifies the authenticated cloud user.
Clients requiring browser OAuth sign-in or only accepting a URL without a header
are not supported by this initial authentication mode. Local stdio setup remains
available for those desktop applications that support it.

Example prompts:

- “Queue this public media URL as audio, then start my queue.”
- “Show the saved options and error for job 1.”
- “Check my run's status; do not add it again.”
- “Stop my current run and keep partial files.”
- “Create a download link for the first file in completed job 1.”
- “Show my recent download history, then search my Pinak Library for guitar.”
- “Scan my approved server download folder and save a bookmark at 01:30 on the matching audio item.”

The AI must call `queue_start` after `queue_add`; enqueue alone does not download.
Poll `queue_run_status` for progress. A call's timeout is not proof that a mutation
failed. Poll at most once every two seconds to leave room within the default
request limit for other tools. If a request times out,
reconcile using the same `request_key` and arguments. IDs and keys belong
to each user's independent database; Bob's job 1 is not Alice's job 1.
`history_list` and `history_show` expose saved attempt records. Library tools
index and organize server-side media in that user's approved roots, with separate
per-user catalog databases. They cannot inspect or play media on the AI user's
laptop. Bookmark show returns a path and time; it does not open a remote player.
Library tag, collection, bookmark, relink and forget edits use request keys for
atomic replay. Forgetting a catalog record keeps the server file.

## Where downloads go

Files live on the cloud disk at `/data/users/NAME/downloads`, with saved state in
that user's `state` directory. A path returned by a tool is a **server path**, not
a path on your laptop. Users cannot select another person's output directory or
inspect files outside their configured root. Only the operator can configure the
host filesystem. The default is one concurrent queue run per person.

`file_link` accepts `job_id` and a one-based `file_index` (default 1). It only
issues links for completed jobs with a saved file at that index. Links expire
after five minutes by default; request another if necessary. The response includes
the actual configured expiry and byte size. Anyone holding the URL can download
that one file before expiry, including someone seeing the AI response. Do not
share it publicly. The server checks expiry, user-enabled status, containment,
file size and modification time before retrieval; rotating/revoking the token
invalidates issued links. Responses are attachments with no-store headers.

Browser downloads use the link itself as the temporary credential, so the user's
permanent token is never embedded in a file URL. Range requests allow resumption
while the link remains valid. Expiry prevents a new request, but does not forcibly
terminate a transfer already accepted before expiry. Changed/deleted files become
unavailable. There is no file browsing, directory listing or arbitrary path URL.

Queue record cleanup keeps media and history. Operators must reclaim disk space
explicitly, after checking job/history references and active runs. File links stop
working when their files are removed; they are not a media backup.
