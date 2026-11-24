# Existing scratch archive migration and disposal (2026-11-24)

Scope: existing P0 scratch archives only. This document records the consumer
inspection, the fail-closed migration contract, the first deployed batch and
the two deferred migrations. No MiCall source, frozen image, original
measurement, active controller script, candidate, active sample or raw input
was changed. The host is `marceline-dev`; the repository is
`https://github.com/ottojung/ivanka.git` at base `581713e6`.

## Inventory observed on this host

| Root | Attested scratch archives | Compressed bytes | Notes |
| --- | ---: | ---: | --- |
| `ivanka-p0-novelty-canary-20261123/physical-cases` | 188 completed, 185 archives left after this batch | 7,383,138,076 B (6.876 GiB) now; about 6.66 GiB at the 183-case founder measurement | current frozen-Rust-only candidate |
| `ivanka-p0-prospective-allprojects-20261122/p0-physical-selective-cases` | 125 | 3,990,346,994 B | disallowed modified-MiCall trial, diagnosis only |
| `.../p0-physical-unique-timing-cases` | 69 | 3,195,990,304 B | same trial |
| `.../p0-physical-updated-micall-iva-cases` | 45 | 354,105,393 B | same trial |
| `.../p0-physical-resource-interruption-provenance-20261122` | 1 | 62,862,137 B | interruption evidence, explicitly preserved |

Each candidate case has `scratch.tar.gz` plus
`scratch-archive-attestation.json` (`ivanka.p0.frozen-rust-only-reversible-scratch-archive.v1`).
The attestation records the archive SHA256, the byte size and SHA256 of every
member, the source execution receipt/score/conseq hashes and `qualification: false`.
A representative archive has 136 members: 77 CSV, 24 PNG, 17 FASTQ, 7 FASTA,
6 Bowtie index, 3 SVG, 1 SAM and 1 log. Read-level CSVs and FASTQ are about
98% of uncompressed bytes. The scientific FASTA/log members total about
18 KB per case.

## Exact consumer inspection

- `ivanka-p0-novelty-canary-20261123/continue_frozen_p0.py` is the pinned live
  controller (s6 `ivanka-p0-frozen-native-novelty-20261123`, observed PID 36866).
  `certified()` reads only `frozen-physical-plan.json`, `prospective-execution.json`,
  `posthoc_score.json` and `conseq.csv`; `run_next()` invokes the archiver only
  for a *new* case. Completed archives are never read, so retiring them cannot
  change controller behaviour.
- `tools/p0_completion_handoff/watcher.py` (service `ivanka-p0-completion-handoff`)
  invokes `benchmarks/independent_frozen_psi_audit.py --root <candidate root>`,
  which reads the same final files. A readback after this batch attested
  **188 of 198** cases with **zero rejection reasons**; status remains
  `PARTIAL_DIAGNOSTIC_COHORT_INCOMPLETE` only because the controller is still
  running. The watcher is therefore compatible with archive removal.
- `benchmarks/retained_artifacts.py` and the separate future-retention agent own
  loose-scratch policy for new arms. This migration does not edit those files.
- Original paired FASTQ inputs live under the frozen root and are referenced by
  hash in `prospective-start.json`. No raw input was opened for writing or deleted.

## Migration contract (`benchmarks/migrate_scratch_archives.py`)

1. Single worker: an exclusive `flock` on `<root>/.existing-scratch-migration.lock`,
   independent of the controller lock. The staging directory defaults to
   `<root>/.scratch-migration-tmp` so the atomic promotion never crosses a
   filesystem boundary; a 256 MiB bounded temporary budget is enforced.
   Retained members are streamed one at a time to a temp file, hashed, then
   atomically promoted under `<case>/retained-scratch/`. No whole archive is
   extracted and no discarded member is written to disk. Temp files are cleaned
   on every abort path and stale receipt temp files are removed on retry.
2. Fail-closed preflight: 64-hex case, regular files only, attestation schema
   and status, pinned image/qualification flag, terminal receipt fields and
   score floors, attestation-to-receipt hash equality, no active `/proc` FDs in
   the case, and free space above the 24 GiB P0 floor plus reserve.
3. Streaming verification: the compressed archive SHA256 must equal the
   attestation; every member must be regular, unattested/duplicate members are
   rejected, and each member's byte count and SHA256 must match the attestation.
   A conflicting retained destination aborts the case without deleting anything.
4. Retention receipt `scratch-retention-receipt.json` is written atomically
   (fsync + rename) before deletion with `archive_removed: false`, then the
   archive is unlinked and visuals removed, then the receipt is finalised with
   post-deletion `df`, visual hashes and `archive_removed: true`. A crash between
   the two writes is recoverable: a later run verifies promoted members against
   the receipt and finalises idempotently. A finished case is skipped as
   `already_migrated`.
5. The receipt lists every retained and discarded member with its SHA256 and
   byte count, the old archive SHA256/bytes, the unchanged attestation SHA256,
   terminal receipt hashes, visual hashes, and free bytes before/after. The
   original archive attestation is retained untouched as historical provenance.
6. Classification: FASTQ/SAM/BAM/Bowtie indexes, visuals (PNG/SVG/PDF/etc.),
   `temp.fasta*`, `aligned.csv`, `remap.csv`, their `unstitched_` counterparts and
   read-level alignment tables are discarded. Contig/seed/genome FASTA, logs and
   non-intermediate metric CSVs are promoted when absent.

## Deployed initial batch (completed current candidate only)

Three completed cases with no active FDs were migrated after unit tests, a
real-data dry run and an independent re-derivation of every archive/member hash
by separate code (`independent_verify.py`; no shared imports with the tool):

- `a826c3929a7c9e8bc63113e8e6629667bb052eca0f8fdcceed0697cb6c79715b`
  archive `36c017b21117f76fe00bbc38d992ce4dd1289238f692fbd9cf5c82f3f93aff1a`,
  60,512,213 B; 72 retained (3,956,742 B) and 64 discarded (304,267,882 B);
  636,160 B of visuals removed.
- `0057f862413b3e94500dbf30edc02b99905351cfff0244e27b4da79b5ee94cc0`
  archive `0b7a53287f36327c3c798fafb95fe685deac14a35cb676927221f55b4f489763`,
  42,368,469 B; 72 retained (1,863,221 B) and 44 discarded (243,326,162 B);
  228,901 B of visuals removed.
- `032539af3db0e8e87dc69afcaaea2f0bb27ba92e5b0f0a5074cf986267872147`
  archive `217916befd216a28a0c940b4320ca16f567b719ea83451f83f7715ede7deb735`,
  36,381,635 B; 72 retained (1,887,641 B) and 44 discarded (213,748,297 B);
  458,170 B of visuals removed.

Validation evidence: all 14 migration unit tests pass (including stale-temp,
mid-stream abort, malformed receipt and visual-record recovery cases found by
independent review); `ruff check` is clean;
independent post-migration verification reports all three archives absent,
old SHA preserved in both attestation and receipt, every member hash covered
by the receipt, and every promoted member byte-exact; the SHA256 of every
pre-existing non-visual case file is unchanged; no `.part` temp files remain;
a second `--apply` run reports `already_migrated` three times. `df -B1 /workspace`
available bytes went from 34,106,470,400 to 34,244,292,608 (**+137,822,208 B**);
per-case free-byte deltas are in each receipt (the controller completed another
case during the batch, so the global delta includes its scratch). The controller
continued from 184/198 to 188/198 with state `RUNNING_SOURCE_FROZEN_P0` and no
integrity rejection.

## Deferred work

- Remaining candidate archives: only after each case is complete and the
  controller/watch gates described above are rechecked. The tool is safe to
  rerun with `--limit` under the single-worker lock; this batch deliberately
  stopped at three cases.
- Legacy disallowed modified-MiCall trial and failed-arm scratch (~7.0 GiB in
  the four legacy roots above) is **inventory only**. Its receipts are
  diagnostic, not qualification, but they are unique scientific evidence and
  must keep logs and all original inputs. Do not migrate it without an explicit
  proof of non-consumption and owner approval.
- Existing frozen original CSV compression (sibling issue
  `81xrwbJjxS8HPJiEa3xNQv-ingenuity`, lossless zstd readers) is
  dependency-gated: no data migration until every reader supports transparent
  plain-or-compressed reads and uncompressed-content SHA verification. This
  change adds no compression and does not mutate the original 4,634 terminal
  receipts or checkpoints.
- PX stores and other projects are out of scope. The future-retention agent
  (`rx3JXLdibYrXq4l1ZAJ8FA-tortoise`) owns new-run policy; no duplicate edits.
