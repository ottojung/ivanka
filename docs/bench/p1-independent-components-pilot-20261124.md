# P1: independent original-fragment components

This is a Rust-only research candidate based on the exact physical milestone
`v0.1.0-alpha.7` (7dbdbaef). It is not a MiCall qualification result.

The unseeded default writer previously selected one read-backed primary
contig even when the native candidates included an independently supported
second component. On a representative mixed HCV/V3 case, the native
candidates were 9637 and 550 nt but the default FASTA contained only 9637 nt.
The frozen historical MiCall result had only the long component before
remapping; its V3 recovery was correspondingly poor.

The existing primary ranking and rendering are unchanged. Count the set of
at most sixteen candidates supported by each original pair once. Greedily
append an additional component only if it has broadly supported 31-mer
positions (at least four fifths), at least twenty independent pair votes,
at least a tenth of all pairs with any candidate evidence, and at least
four fifths of its own votes unexplained by previously selected candidates.
A pair that already supports a selected component cannot vote again.
Thresholds are conservative read-evidence heuristics, not estimates of
biological abundance or extra acceptance gates. No reference, known truth,
environment setting or benchmark-only option enters the executable.
The existing same-sample seeded path is unchanged.

## Standalone diagnostic

64 fixed synthetic cases from the frozen cohort; both binaries read the same
original compressed paired reads with an empty environment and default CLI.
Withheld truths are opened only after both FASTAs are written. The common
local alignment scorer is used here only as a posthoc diagnostic of raw
assembly, not the qualifying final MiCall score.

| Family | Cases | Mean old | Mean new | Minimum new per-truth fraction |
| --- | ---: | ---: | ---: | ---: |
| HCV + V3, 15% | 16 | 5168.84 | 9991.00 | 0.9964 |
| HCV + V3, 30% | 16 | 5168.29 | 9994.43 | 0.9981 |
| HCV + HIV, 15% | 8 | 5006.32 | 9730.38 | 0.6214 |
| HCV + HIV, 30% | 8 | 5005.54 | 9948.19 | 0.9435 |
| Equal strains | 4 | 9041.21 | 9041.21 | 0.8138 |
| Clonal | 4 | 9993.80 | 9993.80 | 0.9991 |
| Coverage hole | 4 | 4596.34 | 4596.34 | 0.4596 |
| PCR jackpot | 4 | 333.83 | 333.83 | 0.0257 |

Every old FASTA was a byte-identical prefix of its new counterpart; all
48 mixed-virus cases gained standalone score, 16 controls had no score
loss. Five controls emitted extra sequences without a standalone score
gain, so integrated runtime and downstream remap regressions must be
measured rather than assumed absent. In particular, the incomplete
HCV+HIV 15% and coverage-hole/pcr-jackpot cases need further investigation.

127 Rust tests pass (76 unit + 51 contract), including independent-support
and pair-mask tests; structural source lint, default rustfmt and workflow
Clippy gates pass. This experiment does not change any frozen original
MiCall arm, input, comparator image or result. Use a separately identified
Rust-only image and genuine integrated pilots, then re-establish both
physical and synthetic numeric gates for any changed candidate.
