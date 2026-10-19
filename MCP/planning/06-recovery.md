# Phase 06 — Failure recovery, resource limits, and hardening

Status: planned. Dependencies: phases 01–05 verified.

## Inputs

All 30 FAILURE_RECOVERY.md scenarios; real adapter/worker/client implementation.
R5–R8 and R10. Earlier phase tests are the starting evidence, not a replacement
for this fault-injection audit.

## Tasks

1. Map each scenario to an automated test or a reproducible manual check.
2. Inject DB busy, corruption, disk-full/write denial, worker spawn failure,
   network loss, timeouts, disconnects, stale progress, and response loss.
3. Verify bounded retry/backoff, receipt replay, no partial bulk mutations, no
   fabricated success, retained partial files, and same-store CLI fallback.
4. Exercise symlink/junction escapes, malformed metadata, oversized arrays/results,
   malicious filenames, URL-secret redaction, and permission refusal.
5. Stress many clients/status requests and large queues; measure resources and
   latency, enforce concurrency limits, coalesce progress, and rotate bounded logs.
6. Confirm shutdown and process ownership on actual supported operating systems.
   Native OS gaps cannot be waved away by a mock on another OS.

## Outputs and commands

Fault-injection tests, fixed failure paths, scenario-to-evidence checklist,
troubleshooting instructions, and performance measurements. Run all `test_mcp_*`
tests plus the full core suite, lint/type/security checks. Verify CLI recovery after
killing an actual adapter/worker process and after a simulated interrupted DB write.

## Acceptance

- Every scenario has an observed outcome and documented next safe action.
- No silent output folder/transport/database fallback, secret leak, uncontrolled
  retry loop, runaway worker, stale lock theft, or unrelated process termination.
- Metadata operations remain usable while a job fails or a run stops.
- Unknown/stale status is explicitly represented; it is never success or empty data.
- All genuinely missing manual evidence remains marked unverified in status.

## Completion notes

Pending: scenario coverage, stress measurements, known limitations, per-OS cleanup
evidence, unresolved external dependencies, and implementation commits.
