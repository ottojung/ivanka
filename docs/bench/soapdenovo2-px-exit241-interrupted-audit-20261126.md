# SOAPdenovo2 PX-R001 / PX-R002 exit241: interrupted processing, reason unknown

Read-only evidence audit, 2026-11-26. No rerun, no OCI build, no live workload,
no MiCall change and no contig filtering were performed. All prior receipts and
retained outputs remain untouched.

## Privacy boundary

Cases are referred to only by the anonymized aliases **PX-R001** and
**PX-R002**. Raw clinical sample identifiers, read-file names and read or
scratch paths are deliberately omitted. Reproduced below are source/image
digests and receipt/log digests only.

## Exact pins and digests

Source-pinned adapter (branch
`bench/minimal-8458f9e5-soapdenovo2-readlen-20261124`):

- adapter commit `39cfa22fad92157680382d1ea124b70b2e8515b3`
  (parent `02aff63992d68ba4a9c98e6917ad27bb402a58f1`)
- source commit `7560c0b9d59e253cb0c819eca40d60f8636b4a11`
- frozen upstream master `8458f9e5d34c39a6694b1fb6a40e055d7ce89553`
- source patch sha256 `47a94054ebddcd05012c00015f8f2d805a79357d789f7c34d867769d3288a327`
- image sha256 `bac9c5c1b45ea8e9f0d9501357bd9bf1ebe2412fefa73598ce96e5ce0fd6d8e6`
- native binary sha256 `87eed4aa2e2b0944584d57e054f0a0b139ecf5fc39b52f05266d321eda617811`

The pinned adapter fix raised `max_rd_len` / `rd_len_cutoff` from 100 to 251 for
251 bp physical mates (six focused tests passed); two successful pilots on the
same image are retained as a reference point.

| case | runner receipt / launcher log sha256 | terminal receipt sha256 | terminal sealed_at (UTC epoch) |
| --- | --- | --- | --- |
| PX-R001 | `b69673fad188c361c226d3c9faaf079f949aeb2da9a6476368f4eeb41963229d` | `8c547c03d8b7d21ad5df4f0b4a8a4974764d136970ecdeeaeb0769bfa92b28fa` | 1795656634.7205782 |
| PX-R002 | `f3620eac238f47477047a5933cfb4416726f5e22814fa9485fa4d27a3a8cedb1` | `5dd3fb6b734e77eedbbb07497eca50acad32ff7f3a1fae0dfc8b2f2a7f2739bc` | 1795662929.8822665 |

The launcher-log digest in each run record equals the `launcher_log` digest in
the corresponding sealed terminal evidence. Paired-read digests (bytes only,
no names) are `680e9daf…41862` / `95717103…468f` for PX-R001 and
`e5a1563f…cb82d` / `6f7bca61…b558` for PX-R002; they match across the case
receipt, resource record and terminal evidence.

## Contig counts and size distribution

The native assembler log (stdout with stderr folded in) records a normal
completion with no error: 24,191,421 / 20,907,322 kmers processed, contig
output produced, zero scaffolds. No separate stderr file was retained.

| measure | PX-R001 | PX-R002 |
| --- | --- | --- |
| contigs reported at de novo stage | 22337 | 26945 |
| assembler contigs longer than 64 bp | 22337 | 26945 |
| contigs longer than 100 bp | 10055 | 7338 |
| bases in contigs longer than 100 bp | 2,131,602 | 1,375,825 |
| longest contig (bp) | 653 | 541 |
| N50 / N90 (bp) | 247 / 127 | 235 / 112 |
| retained combined FASTA total bases | 3,021,144 | 2,782,849 |
| shortest output contig (bp) | 64 | 64 |
| output contigs under 100 bp | 12282 | 19607 |
| output contigs under 200 bp | 15499 | 23142 |
| output contigs under 500 bp | 22311 | 26940 |

The burden is an avalanche of short fragments rather than long contigs: most
output sequences are below 100 bp and essentially all are below 500 bp.

## Measured resource use

- PX-R001 peak RSS `3711180800` bytes = 3539.257812 MiB.
- PX-R002 peak RSS `3720515584` bytes = 3548.160156 MiB.
- Method `container_process_tree_sampled_rss`, version
  `ivanka.px.whole-container-rss.v2`, scope `whole_container_process_tree`;
  `kernel_enforcement: false`.
- Current per-arm policy is 2400 s wall and 4,000,000,000 bytes sampled RSS.
  The two peaks are 92.8% / 93.0% of the byte cap — below it, not over it.
  Sampled RSS is not proof of kernel-enforced memory isolation.
- Successful pilots on the identical image peaked near 83 MB, so the
  multi-gigabyte observation is confined to these two cases.

## Exit cause: proximate signal and residual uncertainty

- In-container timing records `exit_code: -15` (SIGTERM) after 433.703 s
  (PX-R001) and 329.703 s (PX-R002).
- The runner records `exit_code: 241`, status `failed`, and no `reason` field.
  241 is the unsigned-byte form of -15 (256 - 15), i.e. the same termination
  signal in a different encoding.
- A **direct** MiCall OOM kill / SIGKILL is inconsistent with -15: the OOM
  killer delivers SIGKILL (-9, runner 137). However this does **not** exclude
  indirect memory pressure, an external watchdog issuing SIGTERM, or OOM
  termination of another process in the same container process tree. The
  sampled peak being below the byte cap does not settle those alternatives.
  **Reason: unknown.**
- Last observable activity is the de novo completion line and the writing of
  the combined-contig and BLAST CSV outputs; the next logged stage is absent.
  Downstream stitching, remapping and consensus stages were interrupted.

## Distinction from `wall_limit`

These are not wall-clock failures. The runs ended at 433.7 s and 329.7 s,
well under the 2400 s policy. Genuine wall failures carry a different record
signature: status `killed`, `reason: wall_limit`, runner `exit_code: 255`, and
no in-container timing (two physical cases were recorded at 1,161,555,968 and
1,235,058,688 bytes peak RSS). A near-wall success at 2285 s on another case
confirms the wall policy is real but is not implicated here. The SOAPdenovo2
cases instead show status `failed`, exit 241/-15 and no recorded reason.

## Scientific interpretation (bounded)

Empty stitched and merged contig outputs, zero G2P mapped/valid calls and
absent consensus/coverage outputs are consequences of interrupted processing:
the pipeline never reached those stages. They are **not** proof that no
haplotype is scientifically recoverable. At interruption the raw assembly held
only short fragments (longest 653/541 bp), so no final dominant consensus had
been formed. Recoverability for these two cases remains untested.

Classification: **interrupted processing, reason unknown**. Not a confirmed
host OOM, not a wall timeout, and not an inherent scientific impossibility.

## Preservation decision

No MiCall modification, no arbitrary reference- or score-specific filtering,
no adapter change and no rerun were made. All receipts, logs, terminal
evidence and retained outputs are preserved unchanged.
