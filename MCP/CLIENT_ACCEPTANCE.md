# Desktop client acceptance

## Windows Cursor, 2026-10-19

Environment: Cursor 3.23.12 (installed application package metadata), Windows,
Python 3.12.14, official MCP SDK 2.3.0, source package 2.0.0 / contract 1.0.
The user explicitly authorized this test. Clerk was already connected separately;
it is unrelated to Pinak and its configuration/authentication was not changed.

A temporary `pinak` stdio entry used an absolute interpreter, isolated policy,
portable SQLite directory and output directory under ignored cli/.venv/.
The existing Cursor configuration was backed up before the atomic merge.
Tests ran in a scratch chat with no repository selected. Prompts limited calls
to Pinak tools and excluded shell commands, project file access and other servers.

Observed in Cursor:

- Connected locally; fourteen tools enabled and individually listed in its dialog.
- `server_info`, `queue_list` and `history_list` returned successfully.
- `queue_add` created job 1 for a generated one-second loopback HTTP WAV fixture.
- `queue_start` selected that job; status reached completed with one success.
- `queue_show` reported succeeded, one attempt and one downloaded file.
- `history_list` returned the successful item; `media_info` reported one second,
  PCM s16le, 8000 Hz, mono. Independent local verification matched all 8000 PCM
  frames against the generated fixture. No public media site was needed.
- `queue_show` for nonexistent job 999999 returned a structured error without
  breaking the session.
- A second throttled WAV fixture reached running with progress. `queue_stop`
  returned stopping, then status became interrupted with worker_alive=false.
  Job 2 remained queued with attempts=1 and last_error=Interrupted; partial files
  were retained. No queue records or downloaded files were removed.

Reconnect/disconnect acceptance remains pending. Removing the temporary entry
restored the exact original config bytes, but the existing server processes were
still present after ten seconds; file removal alone is not shutdown evidence.
A WSL Debug Console occluded Cursor's settings controls. Its terminal UI was
not automated; the user was asked to move it before the explicit reload check.

This evidence covers this named Windows host only. It does not certify every
client, macOS/Linux desktop rendering, suspend/resume or long-duration soak tests.
