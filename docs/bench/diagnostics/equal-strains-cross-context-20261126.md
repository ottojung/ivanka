# Matched equal-strain truth evidence across preprocessing contexts

**Descriptive native evidence only; no integrated qualification or causal attribution.**

Match the exact 16 abundant truths from the earlier equal-strain floor-failure
diagnostic to the corrected prospective native comparison. Require identical
original R1, R2 and truth SHA-256 digests and identical counts of read-observed
exclusive canonical truth 31-mers. Compare the earlier integrated 12d8c72f
unstitched output, the current combined candidate's direct native output, and
the earlier strongest successful rival's unstitched output for each truth.

| Context | Median exclusive truth 31-mer recovery |
|---|---:|
| Prior integrated candidate unstitched | 23.36% |
| Current direct native candidate | 99.82% |
| Prior strongest rival unstitched | 96.81% |

14/16 truth recoveries improve, two are equal, none regress. Four remain below
90% of the historical rival's native evidence: s007/truth_1, s009/truth_1,
s012/truth_1, s013/truth_1. This diagnostic relative cutoff is **not** the
official final-alignment floor. The prospective direct native input is raw
untrimmed reads; MiCall uses its own preprocessing and downstream steps.
The comparison cannot isolate the assembler change from preprocessing, and
does not establish long-range phase, final consensus, or a passing gate.

Recompute from the two retained SHA-bound reports:

```sh
python3 benchmarks/equal_strain_cross_context.py \
  docs/bench/diagnostics/equal-strains-read-support-20261126.json \
  docs/bench/diagnostics/p1-adapter-mode-posthoc-partial-20261126.json
```

The remaining four deficits identify a narrow source-blind research target;
they must never be used to feed truth/reference or comparator output into
assembly. Preserve negative/clonal controls and all official thresholds.
