# PX SOAPdenovo2 physical PX-R001/R002/R003 `exit -15`: source-attested trigger

Owner: agent-lntEk0jlcQ9nyFmHCF66kG-cheetah · host `marceline-dev` · 2026-11-26
Issue: `V9roZ0y80gjXs7WrOCgNbH-moral` (PX, ten NONQUALIFYING additional assemblers)

Status: **research finding only.** No live run, pilot, image build, deploy,
arm/install, merge, MiCall change, frozen-data change, receipt/registry/checkpoint
change or public-site data change was made. All ten assemblers remain
NONQUALIFYING and the issue stays OPEN.

## Question (from the 2026-11-26T04:28Z operator note)

> SOAP R001/R002 exit -15 after 22k/27k contigs; trigger unknown, no scientific
> impossibility claim. Investigating source-attested frozen SPAdes donor to
> avoid rebuild.

## Finding

The SIGTERM was **not** a scientific assembler result and **not** a PX guard
trip. It came from a *separate, already-running host memory-guard service*
(`ivanka-bench-memory-guard`, PID 275) whose source contains a hidden
**soft trip at 3,700,000,000 bytes**, below the documented PX ceiling of
4,000,000,000 bytes. The guard sends `SIGTERM` to the whole MiCall process
tree as soon as its sampled tree RSS crosses 3.7e9 B. High-contig SOAPdenovo2
cases drive MiCall's downstream (post-assembly) processing over that soft trip.

Therefore this is a **recoverable infrastructure/observability failure, not a
scientific impossibility**: the assembler produced 22,337 / 26,945 contigs and
the arm was killed afterwards by an external guard. No frozen image rebuild or
SPAdes donor is needed to explain it.

### Exact source of the trigger

| file | SHA256 | binding constant |
| --- | --- | --- |
| `/workspace/ivanka-benchmark-memory-guard-20261119/benchmarks/memory_guard/proc.py` | `086ce9aca6d73703216e841d8e9b580cab6678e743f868d6e133a50ba0d69e72` | `LIMIT = 4_000_000_000`, `TRIP = 3_700_000_000` |
| `.../memory_guard/guard.py` | `6e096ffb7cae5014595a6aaa889beb2ed7d05172588556adb6a82ffa23e32dbe` | `if used < TRIP: continue` → `enforce(...)` |
| `.../memory_guard/signals.py` | `b5a4dc351da3fc9144bcfad7a26059a849e9c5a58980c26e3c004ad817d88c53` | first breach `os.kill(target, SIGTERM)`; 2 s later `SIGKILL` |
| live registry `policy.max_sampled_process_tree_rss_bytes` | (registry SHA unchanged; read-only) | `4000000000` |
| live registry `policy.max_container_wall_seconds` | (read-only) | `2400` |

`guard.py` audits each action to
`/workspace/micall-frozen-seven-20261117/cap-4gb-memory-violations.jsonl`
with `soft_trip_bytes=3700000000` and `memory_max_bytes=4000000000`.

### Case-by-case evidence (all hashes recomputed here)

| alias | receipt SHA256 | launcher receipt SHA256 / launcher log SHA256 | timing SHA256 | `timing.json` | host-guard audit |
| --- | --- | --- | --- | --- | --- |
| PX-R001 | `8c547c03d8b7d21ad5df4f0b4a8a4974764d136970ecdeeaeb0769bfa92b28fa` | `0097ff265972ffa97a667b89f4ca9434507fbde6a70534d37d12d537ac423232` / `b69673fad188c361c226d3c9faaf079f949aeb2da9a6476368f4eeb41963229d` | `fa6a2d2bce37de5a72a88f8c8cb1707f7a7c06c361fa0f0983e72a825a3b0aa9` | `exit_code=-15`, `seconds=433.703012829` | `1795656633.205` · pid 1380653 · `rss_tree=3702747136` · `SIGTERM` · `command_sha256=f2f57ed362bdb2efbb21ad3fd12d712e5ced1fbcc80c9937c80917d9d6b616d2` |
| PX-R002 | `5dd3fb6b734e77eedbbb07497eca50acad32ff7f3a1fae0dfc8b2f2a7f2739bc` | `251f79b5ed704d3100abe17b07aea48c0b6876dd673dde46c268bb2dfdd4d433` / `f3620eac238f47477047a5933cfb4416726f5e22814fa9485fa4d27a3a8cedb1` | `6db351249b557ec0f7a8c9f8e77c2aac9db4a0aa5ab902a200b321f166335bb1` | `exit_code=-15`, `seconds=329.702546589` | `1795662928.511` · pid 1853427 · `rss_tree=3873705984` · `SIGTERM` · `command_sha256=50e2f91f35767ca3a6a519f1add1af9ef9e00c17e6959da0face484c86ea800f` |
| PX-R003 | `c7572eddd1164362ad59f372f5466123831c8a76c1b5abd2faedc18faab1b8cd` | `b28e940cbc78719dfc412588d8b431925f809f9996a90fdfdd24e80186b28013` / `94a4bb71bacb2e1909bad722203ce8af57c2c941feaca1370282cbb379893a9a` | `d0d0cf26ea23c3e04c015db7f2eec91fd4f2e8be3782477ddf5c73b2c33afbed` | `exit_code=-15`, `seconds=127.417292516` | `1795669623.216` · pid 2355151 · `rss_tree=3706281984` · `SIGTERM` · `command_sha256=811aa97ed113c95f0c334b0b27da00665ff16bb7c496d0081f0e47a1e649698f` |

The guard's `command_sha256` for R001 and R002 was reproduced exactly from the
frozen input manifest read paths:
`sha256("/opt/venv/bin/python /opt/venv/bin/micall analyze sample /reads/<sample>_L001_R1_001.fastq.gz /reads/<sample>_L001_R2_001.fastq.gz /results --denovo --keep_scratch --all_projects ")`.
This binds the audit record to the exact MiCall tree of each arm, not to a
coincident timestamp.

Timing correlation (launcher ident epoch + in-container monotonic seconds vs
audit `observed_utc`): R001 **-0.123 s**, R002 **+0.198 s**, R003 **-0.052 s**.
The internal timer (`benchmarks/inside_container_timing.py`) recorded `status =
subprocess.call(...)` = -15, wrote `timing.json`, and `SystemExit(-15)` became
launcher exit 241 — the exact shape of an externally delivered SIGTERM.

### Alternatives excluded

* **PX sampled-RSS guard**: each receipt records 3,711,180,800 / 3,720,515,584 /
  3,713,961,984 B, all **below** the 4e9 ceiling; the launcher receipts carry no
  `reason`, so `px_execution.classify()` saw no `observed_rss_limit`.
* **Wall limit**: 433.7 / 329.7 / 127.4 s, far below 2400 s.
* **Identity / lease / teardown**: launcher receipts show
  `identity_matches=true`, `cmdline_changed=false`, exact CID bound, and
  `teardown.container_removed=true`; no `identity_lost`, `measurement_unavailable`
  or `teardown_unverified` reason.
* **STOP / manual interruption**: no STOP sentinel was created at 01:23–01:31Z
  or 03:10–03:15Z on 2026-11-26; the last retired STOP predates these arms
  (`handoff/orphan-ray-20261126T0040Z`, 00:40Z).
* **Assembler failure**: the MiCall logs show 22,337 and 26,945 contigs
  assembled successfully in 9 s and 5.7 s before the kill. No zero-contig or
  assembler exception was involved.

## Reconciliation of the four harness defects (do not redo)

The 2026-11-26T07:28Z `[P1-DEFECT-VERIFICATION]` verdict (posted on the separate
cervical/P1 issue, **not** to be duplicated here) already verified that the
real TOML namespace parser, startup None-heartbeat race, lock-before-lease
ordering and strict teardown absence are fixed at PR #520 head
`1b6e88c05f09fc8092d2f9dda031e36db02c87a3`. This run independently re-checked
`git ls-remote` (SSH == HTTPS) for `refs/pull/520/head` and obtained the same
`1b6e88c0`; no duplicate source fix was made. The host soft-trip found here is
a *different* guard, outside that PR.

## Safe, guarded retry plan — NOT executed, operator gate required

Preconditions, all mandatory before any authorized R001/R002 retry:

1. Obtain an independently reviewed, durable guard pin that reconciles the
   3.7e9 host soft trip with the 4e9 PX sampled-RSS ceiling (or an explicit,
   reviewed operator decision that the 3.7e9 trip is the governing limit).
   Do **not** widen or disable any guard on the strength of this finding alone;
   `kernel_enforcement=false` stays declared, sampled RSS is not a kernel cap.
2. Preserve every original attempt immutably: the three receipt SHA256 values,
   runner receipt/log/timing/terminal-evidence SHA256 values above, and the
   sealed `terminal_evidence.json` files. Never delete or rewrite them.
3. Record pre-spawn consumption (actual OCI layers, retained outputs, scratch,
   temporaries) and verify `/workspace` free >= 32 GiB (measured 40 GiB at
   triage). Enforce one PX worker, 4 GiB requested ceiling, sampled-RSS trip
   (governing value per gate 1), 2400 s wall, exact-CID teardown in `finally`.
4. Register the retry as an explicit public **retry supersession** in the
   generic cohort views: both the original failure and the retry must remain
   visible, with the original failure evidence intact. No proxy zero, no
   invented score/time/RAM, no re-execution of any successful case.
5. Execute only inside the operator-authorized bounded window. Fail closed on
   unavailable measurements; keep the original `failure_reason=error` if the
   retry is not authorized or does not complete.

No frozen image, frozen seven, manifest
`9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f`, MiCall
base, scoring, truth, threshold, registry or checkpoint was altered by this
diagnosis. The frozen SPAdes donor hypothesis needs no action for this trigger.

## Validation performed

* Fresh `--no-hardlinks` isolated clone of `ottojung/ivanka`; SSH and HTTPS
  `git ls-remote` agree on main `12434baca8a2b07e6d93e1dcd0565079a582e32a`
  and PR #520 `refs/pull/520/head` `1b6e88c05f09fc8092d2f9dda031e36db02c87a3`.
* Read-only recomputation script (kept outside the repository at
  `/tmp/opencode/lntEk0jlcQ9nyFmHCF66kG-cheetah-v9ro/verify_soap_trigger.py`):
  all case/receipt/log/timing hashes, guard constants, timing deltas and the
  two reproduced `command_sha256` values PASS; no live state touched.
* `git diff --check` on this change: clean.
