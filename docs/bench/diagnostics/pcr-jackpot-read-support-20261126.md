# PCR-jackpot native read-support deficit — 2026-11-26

This retrospective diagnostic concerns the completed prospective P1 candidate
`12d8c72f`, not the frozen original Ivanka arm or the unexecuted combined
candidate. All 16 PCR-jackpot cases were read. The per-case best rival is
selected by the existing final MiCall score among successful frozen rivals.
The existing 90% relative floor is unchanged.

For each case, intersect distinct canonical exact 31-mers from the single
synthetic truth with those in the original paired FASTQ reads. Compare this
set with the retained unstitched contigs from the candidate and selected
rival. On the 14 relative-floor misses, median recovery was 40.22% versus
99.87%. Across those misses, 720–2032 rival-only truth 31-mers were observed
in the reads, each in at least three distinct read strings. Distinct strings
are not independent molecules; PCR duplicates, errors and overlapping reads
can create correlated support. The metric is neither phased reconstruction
nor final consensus quality. Absolute complete reconstruction may remain
unidentifiable even when the relative performance deficit is real.

The retained aggregate JSON includes SHA-256 digests of the inputs and result
ledger, not sequence data. It does not alter historical receipts, qualify any
candidate, or choose contigs for assembly. Truth and rival outputs are used
only after assembly has finished, by this independent diagnostic.

Reproduce with the retained candidate results root, frozen synthetic outputs
root and original synthetic input root:

```sh
python3 benchmarks/pcr_jackpot_read_support.py \
  --candidate-root "$CANDIDATE_ROOT" \
  --frozen-root "$FROZEN_SYNTHETIC_ROOT" \
  --data-root "$SYNTHETIC_INPUT_ROOT" \
  --output /tmp/pcr-jackpot-read-support.json
```

The candidate root must include its completed results.jsonl. The script
requires all 16 distinct case IDs, successful candidate and at least one
successful rival per case, matched nonempty read files, and one truth
sequence. Output must not already exist. This is not a new acceptance gate.
