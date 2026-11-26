# PX elapsed intervals between MiCall log markers (2026-11-26)

This is a retrospective diagnostic, **not a benchmark score or a CPU profile**.
It follows the 250 exact successful launcher-log matches in the native-runtime
diagnostic, preserving that report's SHA-256 and original canonical index hash.
Each interval begins at a named log marker and ends at the next marker; the two
postprocessing passes are summed. It may include internal work not named by the
marker. Nothing is reassigned to a stage outside the observed log span.

| Interval | Seconds | Share of official elapsed time |
|---|---:|---:|
| remap | 12599.97 | 28.63% |
| aln2counts | 7063.06 | 16.05% |
| fastq_g2p | 6553.35 | 14.89% |
| coverage_plots | 6313.24 | 14.35% |
| native_assembly | 4873.20 | 11.07% |
| sam2aln | 3456.01 | 7.85% |
| sample_setup | 706.88 | 1.61% |
| merge_entropy | 691.77 | 1.57% |
| assembly_tail | 532.31 | 1.21% |
| resistance | 30.82 | 0.07% |
| resistance_report | 2.41 | 0.01% |
| run_tail | 1.71 | 0.00% |
| startup | 0.45 | 0.00% |
| cascade_report | 0.43 | 0.00% |
| sample_tail | 0.03 | 0.00% |
| Official minus logged span | 1180.76 | 2.68% |

Total official elapsed: 44006.40 seconds. All 250 logs match the expected marker sequence. Maximum absolute per-arm difference between the logged span and official elapsed is 13.040 seconds.

## Implications

The largest observed interval is remapping; the next are alignment counting,
FASTQ G2P, and coverage plotting. A faster native assembler alone cannot remove
these intervals. This does not establish that any particular stage is inefficient,
nor does it justify changing the frozen clinical baseline or excluding stages from
benchmark timing. Investigate alignment/counting reuse only in a separately
reviewed prospective experiment, and keep equivalent clinical outputs and the
original benchmark gate intact.
