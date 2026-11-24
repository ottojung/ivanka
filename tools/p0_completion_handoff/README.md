# Read-only P0 completion handoff watcher

## What it does

A single supervised, idempotent watcher that observes the **terminal state**
of the supervised frozen-original P0 controller at
`/workspace/ivanka-p0-novelty-canary-20261123/p0-frozen-continuation-health.json`.

It deliberately separates three different terminal meanings:

| Controller state | Watcher phase | Action |
| --- | --- | --- |
| `RUNNING_SOURCE_FROZEN_P0`, `BOUNDED_BATCH_DONE`, `PREFLIGHT_READY`, `WAITING_FOR_THREE_INDEPENDENT_CANARIES` | `RUNNING` | log only |
| `PAUSED_DISK_RESERVATION` (any `PAUSED*`) | `PAUSED` | log only; never a completion |
| `FATAL_MANUAL_REVIEW_REQUIRED` | `FATAL` | one board notice: preserve evidence, inspect capacity, **do not blindly restart**, no rescore |
| terminal 198/198 completion states | `COMPLETE` | run exact PR433 readback + PR435 decision **once**, preserve anonymized output with SHA-256, one board notice with the exact next action |

The controller's `P0_FULL_SEVEN_QUALIFIED` label is only a **trigger** for
independent reconciliation. The watcher never emits a scientific pass or a tag:
PR435's fail-closed decision is preserved verbatim and the expanded 464-synthetic
seven-way gate (Intent 006) is explicitly called out as still required.

## Safety invariants

1. **Read-only on every benchmark root.** The watcher reads the health snapshot
   and invokes the merged PR433/PR435 tools with `--out` paths *outside* both
   audited roots. It never writes to the controller, candidate, frozen MiCall
   trees, receipts or scratch.
2. **No duplicate workers.** It scores nothing, starts no MiCall/assembler, and
   changes no threshold. The two tools only re-derive diagnostics from retained
   receipts when a full cohort genuinely exists.
3. **One expensive pass.** `manifest.json` records SHA-256 of both preserved
   reports. A restart or repeated poll reuses verified artifacts and never
   re-runs the tools. A tampered/missing artifact forces exactly one
   re-preservation, not repeated polling rescoring.
4. **Idempotent board notices.** A JSON journal plus the manifest's
   `board_notification` record prevent double-posts across restarts and after
   partial infrastructure failures.
5. **Fail closed.** Hash/schema/claim/count validation rejects malformed or
   over-claiming reports as `INTEGRITY_FAILURE`, posts that verdict once, and
   never converts it into a pass.
6. **Bounded infrastructure retry.** Tool exits/timeouts and board-post errors
   are retried with exponential backoff (3 attempts per event, at most
   `max_attempts` total per transition), then recorded as exhausted rather
   than looping forever.
7. **Anonymized output.** PR433/PR435 emit only counts, category names and the
   three public pinned digests; the watcher checks `contains_sample_identifiers`
   is false and `qualification_claim`/`expanded_claim` are `NONE`.

## Deploy

```sh
SRC=/workspace/ivanka-completion-watch-W828YF4l6XKNvnCtjHdrZy-sparkled-20261124
STATE=/home/lubko/.local/state/ivanka-p0-completion-handoff
mkdir -p "$STATE/artifacts"
cp "$SRC/tools/p0_completion_handoff/config.example.json" "$STATE/config.json"
# edit config.json: set source_commit to the exact reviewed commit SHA
install -m 0755 "$SRC/tools/p0_completion_handoff/service/run" \
  "$STATE/run"
ln -s "$STATE" /run/service/ivanka-p0-completion-handoff
/command/s6-svscanctl -a /run/service
/command/s6-svstat /run/service/ivanka-p0-completion-handoff
```

The service exits as soon as the terminal handoff is durable and then holds
(`sleep 86400`) so s6 cannot silently restart a finished review front. To stop
it deliberately, remove the symlink and run `s6-svscanctl -a /run/service`.

## Verify

```sh
python3 -m unittest tools.p0_completion_handoff.test_watcher -v   # 12 synthetic cases
python3 -O -m unittest tools.p0_completion_handoff.test_watcher    # identical under -O
ruff check --select E4,E9,F,B006,B018,B023 tools/p0_completion_handoff
tail -f "$STATE/service.log"
```

Synthetic coverage: phase classification, complete handoff, hash-attested
artifacts, restart idempotency, journal loss, tamper-triggered re-preservation,
FATAL notice, PAUSED not treated as finished, integrity failure fail-closed,
board outage retry/success, board outage exhaustion, and anonymization checks.
All external boundaries are stubbed; no live controller or board is touched.

## Handoff contract

On complete evidence the board notice names:

* the exact source commit and repository;
* controller state and 198/198 attestation;
* the PR435 fail-closed decision and its scope (`PHYSICAL_ORIGINAL_198_ONLY`);
* SHA-256 of both preserved reports and the three pinned digests;
* the exact next action: independent re-run of the PR433 readback and PR435
  decision, then the 198/198 all-r re-audit with missing arms and high-r tails
  tracked in `h4u6MKP9T9prsOqr3ZULCZ-liver`, with no tag/pass until independent
  review and the expanded 464-synthetic seven-way gate (Intent 006).
