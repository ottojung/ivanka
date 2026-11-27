# Remap diagnostic guarded pilot controller/scoring/retention plan

Status: **source-only controller and plan**. No benchmark run, no image
build, no MiCall launch, no frozen result change, no qualification claim
and no public acceptance claim are made here. This advances PR548
(source-only runner) and PR549 (opt-in display/registry) without
duplicating their code.

## Scope

PR548 (`remap_runner.py`, corrected head `f783d16`; lint fix on
`8d7bd1d`) provides the exact
frozen-base reference-based plan, immutable receipt with validated
ended whole-container RAM/guard CID binding, additive rows, capacity gate
and read isolation. PR549 (`remap_diagnostic.py`, head `fecff32`) provides
the opt-in publication boundary, display isolation and independently
attested input mapping requirement. This change adds the missing guarded
pilot controller, posthoc canonical scoring wiring and retention plan so
an independently reviewed execution can be wired after preconditions are
satisfied.

## Existing runner functions audited

| Function / module | Role | Reused by controller |
|---|---|---|
| `remap_runner.plan_case` | Exact frozen command plan, read pins, provenance | Plan identity and argv |
| `remap_runner.build_receipt` / `build_rows` | Distinct receipt/rows schema, null unavailable metrics | Receipt emission |
| `remap_runner.capacity_decision` | 32GiB reserve gate | Preflight admission |
| `remap_runner.isolate_reads` / `verify_isolated_reads` | Attested same-read isolated mount | Read provenance |
| `guarded_canary_launcher.build_command` / `assert_reference_blind` | Exact command allowlist, no truth mount | Command safety contract |
| `exploratory_runtime.launch.operate` / `monitor` / `pilot` | Exclusive slot, lease, heartbeat, CID-bound guard, logs | Guarded execution path |
| `px_posthoc.PxScorer` / `expanded.score.score_sequences` | Posthoc canonical scoring, multitruth per-truth | Posthoc scoring only |
| `px_retention` / terminal retention policies | Retained logs/receipts and disposable scratch rules | Retention plan |

## Preconditions (all required before any execution)

1. **Attested same reads**: case reads are original paired FASTQs with
   SHA-256 pins; isolated mount contains only those two basenames.
2. **Frozen common image**: reuse
   `sha256:52e6bed1b52e2cb4c21cdde850b86e82caa96f05b82271978e9cae34305d5eff`
   (image id `da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad`),
   no rebuild.
3. **Guarded exclusive slot**: durable lease/lock held; no concurrent
   benchmark owner.
4. **Reserve 32GiB + reservation**: `capacity_decision` admitted and
   operational reservation present; no execution below reserve.
5. **40m/4e9**: wall 2400s, RSS limit 4,000,000,000 bytes, 2 CPUs,
   `kernel_enforcement=false`.
6. **No truth mounted**: reconstruction argv/mounts contain no truth,
   hidden-truth, haplotype, HXB2 or panel path; panel/truth used only by
   posthoc scorer outside container.
7. **Distinct receipts**: every attempt gets a distinct run/attempt id and
   immutable receipt digest.
8. **Null unavailable metrics**: de-novo-only/native contig/stitcher
   metrics remain null and named unavailable; no zero fabricated.
9. **Retained logs**: launcher/container/timing logs and receipt files are
   retained with hashes.

## Pilot matrix (diagnostic only)

| Cohort | Cases | Scoring | Multitruth diagnostic | Qualification effect |
|---|---:|---|---|---|
| Physical | selected attested physical pilot cases | posthoc canonical reference-panel alignment over final MAX | N/A | none |
| Synthetic | selected attested synthetic pilot cases | posthoc canonical abundant-truth balanced v2 over final MAX | per-truth posthoc diagnostic included | none |

Synthetic multitruth diagnostic is computed posthoc from retained final MAX
and pinned per-case truth manifest/hashes; it is never mounted into the
assembler container and never used as a qualification gate.

## Real guarded execution (not a mock)

`benchmarks/assembler_bench/remap_guarded_exec.py` is the default execution
path used by `execute_case` (no injected runner in production). It:

1. re-checks the 32 GiB reserve immediately before ownership or process spawn
   and refuses to start below reserve;
2. takes the shared exclusive slot lock and durable worker lease, refusing
   contention or an uncleared prior lease;
3. validates plan aliases and both FASTQ digests against the independently
   attested original read-pair manifest
   `/workspace/ivanka-storage-recovery-20261126/remap-input-attestation-20261126/readback.json`
   (SHA-256 `01c59cf…`, 198 physical + 464 synthetic, `truth_opened=false`),
   never a rows/receipt-derived mapping;
4. launches the exact frozen non-de-novo argv under the common fail-closed
   watcher (`monitor.watch`), binding the exact issued CID and sampling whole
   container RSS;
5. maps real guard evidence to the receipt contract without fabrication:
   `peak_rss_bytes` from the watcher peak, `samples` from actual heartbeat
   observations, `observation_ended` from watcher termination, attested
   method/version/scope from the sampler, and a guard receipt carrying the
   same bound CID and exact 2400 s / 4e9 / 2-CPU bounds;
6. requires an exact-CID fresh-absence (unmount) proof before the controller
   may call the posthoc scorer. No unmount proof means no score.

Injected runners exist only as source-test seams; a real manifest is still
required when they are used.

## Execution wiring

`remap_pilot_controller.execute_case`:

1. Write plan and preflight records.
2. Fail closed if preflight is not admitted.
3. Run the real guarded execution path above (or an injected source-test
   double) and retain its plan/manifest binding and guard records.
4. Classify outcome from exit status, wall limit and presence of final MAX.
5. If measured, verify exact unmount proof, then run posthoc canonical
   scorer outside the container; on scoring or unmount error fail closed
   with no fabricated score.
6. Emit `remap_runner.build_receipt` with resource attestation, null
   unavailable metrics, distinct digest, and posthoc metadata.
7. Retain logs and receipt files under attempt directory.

## Retention

- Keep: `plan.json`, `preflight.json`, `execution.json`,
  `posthoc-score.json`, `receipt.json`, `retention.json`, launcher/container
  logs, timing evidence, and final MAX outputs needed for audit.
- Disposable only after terminal proof and hash verification: scratch/tmp,
  subject to common terminal retention policy; never delete receipts/logs.
- Infrastructure/teardown-unverified attempts preserve scratch for diagnosis.

## Blockers / no-op conditions

- Any reserve/capacity deficit: no execution.
- Missing exclusive slot or lock contention: no execution.
- Missing/failing image attestation or rebuilt image: no execution.
- Missing attested reads or hash drift: no execution.
- Truth/reference mount leak: no execution.

## Integration contract at updated heads

- PR548 hardened receipts: a measured receipt requires an ended whole-container
  observation (`observation_ended`, `samples>=2`, exact bound CID, attested
  method/version/scope, peak within 4e9) plus a guard receipt carrying the
  same CID and exact 2400s / 4e9 / 2-CPU / `kernel_enforcement=false` bounds.
  Nonfinite scores/runtimes and missing `conseq_csv_sha256` output evidence
  are refused. The controller forwards these fields from the guarded runner
  unchanged and fails closed when they are absent; it never fabricates a CID,
  sample count or guard observation.
- PR549 join binding: `merge_diagnostic_report(..., attested_inputs=...)` is
  supplied by `remap_pilot_controller.attested_input_mapping(plans)`, derived
  only from attested plan reads and canonical manifests. The controller's
  `require_independent_attested_mapping` refuses rows-derived mappings and
  verifies the mapping envelope digest; diagnostic rows never self-attest.
- Row ingestion path: `remap_runner.build_rows` after receipt emission; posthoc
  scoring metadata is placed inside the receipt before its digest is computed.

## Non-goals

- No frozen source/result changes.
- No acceptance influence, no qualification claim, no public acceptance language.
- No image rebuild, no live cohort run, no deployment.
- No duplication of PR548 runner or PR549 display code.
