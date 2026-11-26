# Completed prospective readbacks — November 26, 2026

This supersedes the interim case counts in
[current workplan status](current-workplan-20261124.md). It does not change
the founder-ordered workplan, thresholds, source-frozen baseline or published
alpha.4 release.

## P0: prospective alpha.7 physical 198

The 7dbdbaef source-pinned candidate image
73f29f0233da2ecd1ab126178cba4deb9e246bff5a6f770ab021a8f36d71081b
completed 198/198 physical cases. On November 26 at 19:22 UTC the existing
readback code was rerun against all 198 candidate receipts, MAX output hashes
and original frozen competitor checkpoints. Excluding the report-generation
timestamp, the recomputed result exactly equals the retained
[all-r report](diagnostics/p0-physical198-final-20261124.json), SHA256
a2db2e009793de59252ad55affab49715180a92f98a2aa3036a150865a3d9fbd.

All 198 cases clear the 90%-of-best-available and IVA floors; the minimum
best-available ratio is 0.9150943396226415. R042 improves from 102 to 179,
meeting the 161.1 floor. The strict all-r score and runtime comparisons
against IVA pass on 198 complete pairs. The other five comparators have
missing successful pairs; diagnostic paired subsets pass, but full
seven-way qualification remains blocked. This result belongs only to
7dbdbaef, not a later unexecuted candidate.

## P1: prospective 12d8c72f synthetic 464

At 19:22 UTC the immutable readback evaluator completed successfully
against the sealed 464-case attempt. All receipts verify, zero identity
errors, and the exact candidate result ledger SHA256 is
903ff012e4e35b0bc7b83c147c56f8ff3c5adc017d188a4679438c7e16eea10d.
See the [aggregate readback](diagnostics/p1-full464-readback-summary-20261126.json).
This is ATTEMPTED_NOT_QUALIFIED, not a run in progress.

56 cases have candidate failure or floor errors: 16 shared low-depth
failures and 40 other cases. There are 25 combined floor misses and 49
individual truth floor misses (these overlap at case level). Runtime
strict all-r remains false on every available comparator subset.
The complete seven-way gate also has genuinely failed comparator arms.
Do not replace the frozen original results or use absent measurements as
zeros.

[Ultradeep runtime diagnostic](diagnostics/p1-ultradeep-runtime-20261126.md)
shows a large historical timing residual outside the logged native assembly
duration; the 16 cases have identical ordered contigs and final consensus
bytes. [PCR-jackpot diagnostic](diagnostics/pcr-jackpot-read-support-20261126.md)
locates a separate native read-evidence deficit. Continue P1 science with
prospective reference-blind repairs and matched-resource timing; do not
confuse either diagnostic with a passing biological gate.

## PX

Continue the ten-tool exploratory cohort in parallel under the independent
watchdog. At most one guarded worker, 32 GiB shared free reserve, 2400 s
wall and 4e9-byte sampled whole-container RSS ceiling remain binding.
No project-specific incremental storage ceiling. Sampled enforcement is
not a verified kernel memory cap. P2 physical diagnostics and P3 comparator
repairs retain their ordered priority.
