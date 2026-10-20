# Public tool contract 1.1

These thirty-three tools are implemented with the official SDK. Input schemas are
generated from `cli/pinak/mcp_server/models.py`; actual SDK discovery/call tests
verify the protocol. Desktop-client acceptance remains a separate release gate.

## Common rules

Pydantic models, explicit input/output JSON schemas, positive IDs, enums for
states/options, bounded strings/arrays, forbidden unknown fields, and stable
error codes. Validate every call, independent of model behavior or client UI.
Report server name, package version, and contract version through server_info.

Return structured data, with a concise compatible text representation for hosts
that only display text. Do not return ANSI, Rich panels, HTML, media bytes, or
raw exceptions. SDK protocol errors handle malformed JSON-RPC/unknown methods;
normal domain failures use tool errors with `isError` and a structured envelope.
Do not report `ok=true` alongside an execution error.

Success: `ok`, `data`, `warnings`, `request_key` when supplied.
Failure: `ok=false`, `error.code`, `error.message`, `error.retryable`,
`error.recovery`, `error.details` (safe fields only).

`queue_start` success means a run was accepted, not that downloads succeeded.
Empty-list results differ from database errors. Times use UTC ISO 8601 in public
results; IDs remain integers for queue jobs and opaque strings for runs.

## Required tools

- `server_info()`: read-only versions, negotiated capabilities, readiness summary;
  no environment dump or installation-specific secrets.
- `queue_add(url, options, request_key)`: validate and snapshot a request using
  DownloadRequest.capture; return job_id, created/deduplicated, saved options.
  Expose quality, audio mode, approved output folder, force, and validated trim.
  Do not accept arbitrary yt-dlp configuration dictionaries.
- `queue_list(status?, cursor?, limit=25)`: compact job summaries, stable pagination,
  has_more/next_cursor. Maximum page size 100; do not materialize every row first.
- `queue_show(job_id)`: complete saved options, status, attempts, errors, and files;
  include bounded/paginated collections when files or errors exceed response limits.
- `queue_retry(job_ids? | all_failed, request_key)`: exactly one target form; report
  changed and unchanged IDs. Only failed jobs are eligible.
- `queue_cancel(job_ids, request_key)`: waiting jobs only. Define atomic validation
  for the requested set; already cancelled is an explicit unchanged result.
- `queue_remove(job_ids, request_key)`: reuse atomic remove-many semantics, reject
  running/unknown/nonpositive IDs before mutation, deduplicate repeated IDs, keep files.
- `queue_clean_completed(request_key)`: succeeded/skipped only, return deleted
  record count; preserve failed/cancelled/queued/running records, files, and history.
- `queue_start(job_ids? , max_jobs?, request_key)`: selected snapshot, one local worker,
  return run_id, starting/running state and the selected job count. Reject conflicting
  targets/limits before spawning. An empty eligible set produces a clear no-work result.
- `queue_run_status(run_id)`: run state, job counts, active job, bounded progress,
  heartbeat freshness, and errors. Include snapshot timestamp, not invented live speed.
- `queue_stop(run_id, request_key)`: request a stop of an owned live run, return
  stopping/already-finished. Explain that partial files and queue records are retained.
  Never silently stop a CLI runner or another host's run.
- `history_list(filter?, cursor?, limit=25)`: compact download history respecting
  approved read scope and redaction; distinguish history-disabled from no history.
- `history_show(history_id, cursor?, limit=25)`: one record's status, source, options
  and paginated file paths; reject a record with files outside approved roots.
- `library_scan(folder)`: explicitly index supported files in an approved output/read
  root. Report partial scan errors; never start a background or arbitrary scan.
- `library_list(media_type?, cursor?, limit=25)`, `library_search(query?, tag?, cursor?,
  limit=25)`, `library_show(media_id)`: paginated, root-scoped catalog reads.
- `library_tag_add/remove(media_id, name, request_key)`: edit one item's tags.
- `library_collection_create(name, request_key)`, `library_collection_list`,
  `library_collection_show(collection_id)`, `library_collection_add/remove`, and
  `library_collection_move`: manage ordered collections. These tools return
  playlist paths; they do not launch a terminal player through MCP.
- `library_bookmark_add(media_id, seconds, note?, request_key)`,
  `library_bookmark_list(media_id)`, `library_bookmark_show(bookmark_id)`, and
  `library_bookmark_remove(bookmark_id, request_key)`: manage saved audio/video
  moments. Show returns a path and time; it does not begin playback.
- `library_relink(media_id, path, request_key)`, `library_forget(media_id,
  request_key)`: update a moved path or remove only the catalog record. Neither
  deletes or moves a media file.
- `media_info(path)`: local approved file metadata/duration using bounded probing,
  no arbitrary directory traversal or automatic GUI playback/artwork export.
- `diagnostics()`: bounded local checks for SDK/core compatibility, database access,
  output permissions, worker state, and binaries. It must not download binaries,
  install dependencies, open windows, or modify records as a hidden side effect.

Batch URL enqueue/import may be added as typed arrays with atomic validation,
not an arbitrary local file-reading tool. Freeze precise maximum counts in phase 02;
initial targets are 100 IDs/URLs per mutation and 100 KiB structured response.
Results must advertise truncation/pagination rather than silently drop records.
Queue/history pages scan at most limit+1 records and omit entries outside the
configured roots. A page can therefore be empty with has_more=true; advance its
cursor. History entries without files remain visible. queue_show uses a one-based
file-index cursor and truncates errors at 8,000 characters with error_truncated.
Library list/search/collection pages use the same bounded-cursor pattern and
may also return an empty visible page when stored items fall outside approved
roots. History show uses a one-based file-index cursor.
queue_retry(all_failed=true) returns a count rather than an unbounded ID array.
Record-only mutations operate on the shared user queue; output/read roots limit
downloads and returned file information, not independent queue ownership.
Library mutations use atomic receipts in the separate Library SQLite database.
Repeating the same request_key and arguments returns the original result;
reusing a key with different arguments is rejected. Scanning is repeatable and
has no receipt because files can change between scans.

## Readiness and capability fallbacks

Missing FFmpeg must not hide queue inspection. Report actual limitations: a simple
download may work, while audio conversion/merging may fail. Provisioning, if offered
later, must be an explicit operation; do not run it during handshake or diagnostics.

Clients without progress notifications use queue_run_status polling. Clients without
structured-result rendering get the same factual result as readable text. Clients
without roots support use configured local roots. Unsupported protocol versions
produce actionable negotiation errors; do not falsify a successful connection.

## Tool descriptions and annotations

Mark read-only tools accurately and describe mutations explicitly. Destructive
annotations apply to record removal even though files remain. Annotations assist
host UI; they do not enforce authorization. Never promise the AI has performed an
operation before receiving its persisted result. Treat filenames, metadata, and
remote error messages as untrusted data, never instructions for further tool use.

The adapter needs a persistent record-removal receipt so a lost response followed
by a retry can return the original success after the record itself is gone.
