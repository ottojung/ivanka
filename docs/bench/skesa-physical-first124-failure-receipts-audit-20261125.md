# SKESA physical first-124 failure-receipt audit (corrected)

Read-only correction for 17 failure receipts among the first 124 indexed SKESA physical cases (`PX-R001..PX-R124`). Corrects an earlier audit that missed PX-root launcher logs/run JSONs.

## Evidence scope

- Case receipts: 124/124 present for `PX-R001..PX-R124` (`ivanka.px.case.receipt.v1`).
- Diagnostics: 107/124 present (`ivanka.px.diagnostics.v3`); missing exactly the 17 failure cases.
- PX-root run records: 231 run JSON + 236 logs. Bindings use run JSON/log digest recomputation, `bound_cid` / `pilot_cleanup.pilot_container_id`, `argv_sha256`, and terminal-evidence `run_json` hash where present. **Digest match alone is not used as identity** for empty-log cases.
- Output artifacts: native assembler log and terminal evidence where present; private input/sample identifiers/paths, raw sequences, and credentials excluded.
- No reruns, no frozen receipt edits, no common MiCall changes, no live builds/service changes.

## Cohort summary

| Bucket (case receipt) | Count | Cases |
|---|---:|---|
| generic `error` | 13 | PX-R011 PX-R012 PX-R052 PX-R057 PX-R058 PX-R059 PX-R068 PX-R069 PX-R070 PX-R071 PX-R086 PX-R092 PX-R095 |
| `disk_stop` | 2 | PX-R022 PX-R045 |
| `identity_lost` | 1 | PX-R105 |
| `measurement_unavailable` | 1 | PX-R113 |

## Corrected per-case bindings

| Case | Receipt reason/attempt | Run record binding (recomputed log sha256) | Run JSON status/reason/exit | Binding evidence | Native/output evidence | Corrected class |
|---|---|---|---|---|---|---|
| PX-R011 | error/1 | `41c60f6c...bf4af` (5720B) | failed/None/1 | log digest == runner_receipt_sha256 | Native assembler log: SKESA "Reads are too short for selected minimal kmer length"; timing exit 1 | **Scientific/input-boundary**; generic adapter error |
| PX-R012 | error/1 | `75bdee4b...06ac4` (5720B) | failed/None/1 | log digest match | Native assembler log: "Reads are too short..."; timing exit 1 | **Scientific/input-boundary**; generic adapter error |
| PX-R022 | disk_stop/2 | `dae1e125...62fee` (865B) | killed/disk_limit/-9 | log digest match | Native assembler log: "Was not able to assemble anything"; skesa-contigs size 0, stitched/merged contigs present; no terminal_evidence/timing | **Process/infrastructure disk stop** (P0); scientific no-assembly also observed; evidence incomplete |
| PX-R045 | disk_stop/2 | `2118a09d...dc05a` (853B) | killed/disk_limit/137 | run_json sha256 + argv_sha256 match terminal_evidence; log digest match; terminal_evidence `bound_cid` field contains raw CID value (field-form anomaly) | Terminal evidence sealed; MiCall artifacts present; no native assembler log found | **Process/infrastructure disk stop** (P0); native assembler log missing |
| PX-R052 | error/1 | `0a539720...f6130` (5706B) | failed/None/1 | bound_cid == terminal_evidence launcher_container_id; log digest match | Native assembler log: "Reads are too short..."; timing exit 1 | **Scientific/input-boundary**; generic adapter error |
| PX-R057 | error/1 | `2c4ea306...a1ff` (5706B) | failed/None/1 | CID + log digest match | Native assembler log: "Reads are too short..."; timing exit 1 | **Scientific/input-boundary**; generic adapter error |
| PX-R058 | error/1 | `0667ea7a...12e0` (5706B) | failed/None/1 | CID + log digest match | Native assembler log: "Reads are too short..."; timing exit 1 | **Scientific/input-boundary**; generic adapter error |
| PX-R059 | error/1 | `e3b0c442...2b855` (0B, empty) | killed/identity_lost/-9 | `pilot_cleanup.pilot_container_id` == terminal_evidence CID; empty digest globally ambiguous, CID binds run record | Native assembler log: "Reads are too short..."; timing exit 1; terminal_evidence launcher_log is empty-digest | **Scientific/input-boundary** primary; **process/identity-loss + instrumentation evidence loss** secondary |
| PX-R068 | error/1 | `e3b0c442...2b855` (0B, empty) | killed/identity_lost/-9 | `pilot_cleanup.pilot_container_id` == terminal_evidence CID; empty digest globally ambiguous, CID binds run record | No native assembler log; no timing; terminal_evidence launcher_log empty-digest | **Process/instrumentation identity-loss with evidence loss**; scientific cause **unconfirmed** |
| PX-R069 | error/1 | `2a13a453...8491` (5706B) | failed/None/1 | CID + log digest match | Native assembler log: "Reads are too short..."; timing exit 1 | **Scientific/input-boundary**; generic adapter error |
| PX-R070 | error/1 | `18c66ed7...1c34` (5706B) | failed/None/1 | CID + log digest match | Native assembler log: "Reads are too short..."; timing exit 1 | **Scientific/input-boundary**; generic adapter error |
| PX-R071 | error/1 | `d2244f1a...7266` (5706B) | failed/None/1 | CID + log digest match | Native assembler log: "Reads are too short..."; timing exit 1 | **Scientific/input-boundary**; generic adapter error |
| PX-R086 | error/1 | `da72eeae...60f5` (2357B) | killed/identity_lost/0 | CID + log digest match | Launcher log: MiCall completed through resistance/report "Done."; denovo "Assembled 0 contigs"; timing exit 0; full MiCall artifacts present | **Mixed scientific + process accounting**: scientific no-assembly; completed pipeline then killed identity_lost exit 0; case receipt generic error obscures state |
| PX-R092 | error/1 | `84e31377...36e0` (451B) | killed/identity_lost/137 | CID + log digest match | Launcher log ends after early MiCall steps; no native assembler log; no timing | **Process/instrumentation identity-loss/kill**; scientific cause **unconfirmed** |
| PX-R095 | error/1 | `49c9945b...ff9a` (455B) | killed/identity_lost/137 | CID + log digest match | Launcher log ends after early MiCall steps; no native assembler log; no timing | **Process/instrumentation identity-loss/kill**; scientific cause **unconfirmed** |
| PX-R105 | identity_lost/2 | `ed5afd68...2505` (356B) | killed/identity_lost/137 | CID + log digest match | Launcher log ends very early; no native assembler log; no timing | **Process/instrumentation identity-loss** (matches receipt) |
| PX-R113 | measurement_unavailable/2 | `648ba9b6...5f97` (2448B) | killed/measurement_unavailable/0 | log digest match; run bound_cid present; no terminal_evidence | Launcher log: MiCall completed "Done."; denovo "Assembled 22 contigs"; timing exit 0; contigs/conseq artifacts present | **Instrumentation/measurement failure, not scientific**; assembly/pipeline completed |

## Corrected classification totals

| Class | Cases | Notes |
|---|---|---|
| Scientific/input-boundary (short reads for SKESA kmer) | PX-R011 PX-R012 PX-R052 PX-R057 PX-R058 PX-R059 PX-R069 PX-R070 PX-R071 | R059 has secondary process/evidence-loss |
| Process/infrastructure disk stop | PX-R022 PX-R045 | P0; shared-disk aware handling required |
| Process/instrumentation identity-loss or kill | PX-R068 PX-R092 PX-R095 PX-R105 | R068/R092/R095 scientific cause unconfirmed due missing native logs |
| Mixed scientific + process/identity accounting | PX-R086 | 0 contigs scientific; completed pipeline + killed identity_lost exit 0 process/accounting |
| Instrumentation/measurement unavailable | PX-R113 | Scientific assembly completed; measurement accounting failed |

## Explicit unknowns / missing evidence

- **R068, R092, R095**: no native assembler log and launcher log empty/truncated before assembler stage; scientific cause not provable.
- **R059, R068**: launcher log digest is empty SHA-256 (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`), globally ambiguous across 20 run logs; binding is by CID only.
- **R045**: terminal_evidence `source_hashes.bound_cid` contains raw CID value, not SHA-256 digest; run_json/argv/log hashes bind.
- **R022, R113**: no terminal_evidence.
- **R045**: no native assembler log.
- Disk-stop root cause (ENOSPC/quota/shared contention) not provable from retained artifacts.

## Prospective minimal adapter-only repairs (not applied)

New namespace + tests only; no reruns, no frozen receipt edits, no common MiCall changes, no live builds/service changes.

1. **Short-read input classification** (P1): map SKESA "Reads are too short..." to explicit reason; fixture/parser tests.
2. **Identity-lost vs scientific separation** (P0/P1): preserve process reason when run killed identity_lost, especially exit 0/completed pipeline (R086) or pre-assembler kill (R092/R095/R105).
3. **Empty launcher-log/CID provenance guard** (P1): flag empty-digest terminal logs; require CID-bound run record.
4. **Measurement-unavailable contract** (P1): keep completed scientific outputs/timing distinct from measurement failure (R113).
5. **Disk-stop sealing completeness** (P0, shared-disk coordination): always seal terminal_evidence + native log pointer on disk_limit.
