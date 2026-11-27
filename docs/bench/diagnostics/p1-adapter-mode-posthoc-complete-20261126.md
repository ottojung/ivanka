# Completed adapter-mode native posthoc (2026-11-26)

**Read-only diagnostic; not integrated MiCall, not qualification.**

The 59 previously unevaluated pairs are now evaluated from the already retained native outputs. The original partial report and original 256-arm run report are unchanged. Before reading generating truth, the supplemental reader checked both native outputs, logs, original read pair and sample-derived seed identities against the execution report. No assembler, container or reference-assisted reconstruction was run. The supplemental reader used a 1.5 GiB address-space bound and wrote a bounded JSONL report; the benchmark admission reserve was not changed.

All 128 pairs (16 per family) are now evaluated. Across the 192 abundant truths, only the seeded PCR-jackpot family changes; all 112 other pairs have byte-identical outputs.

| Family | Abundant truths | Mean observed canonical truth 31-mer recovery old → new | Mean exclusive recovery old → new | Mean native local alignment old → new |
|---|---:|---:|---:|---:|
| clonal | 16 | 99.95% → 99.95% | 99.95% → 99.95% | 99.94% → 99.94% |
| complex_mixture | 32 | 74.89% → 74.89% | 72.41% → 72.41% | 85.09% → 85.09% |
| coverage_hole | 16 | 99.17% → 99.17% | 99.17% → 99.17% | 45.96% → 45.96% |
| discordant_pairs | 16 | 99.60% → 99.60% | 99.60% → 99.60% | 99.58% → 99.58% |
| equal_strains | 32 | 88.36% → 88.36% | 87.73% → 87.73% | 93.17% → 93.17% |
| hcv_hiv_30pct | 32 | 99.52% → 99.52% | 99.52% → 99.52% | 99.48% → 99.48% |
| minority_30pct | 32 | 72.19% → 72.19% | 69.96% → 69.96% | 89.31% → 89.31% |
| pcr_jackpot | 16 | 42.63% → 92.44% | 42.63% → 92.44% | 3.91% → 3.93% |

The means give equal weight to each abundant truth with nonzero denominator. Native alignment is the maximum local alignment fraction to each truth, not the coverage union across all contigs. PCR read-evidence rescue does not establish a final consensus or improved integrated alignment. Coverage-hole recovery is high despite short native alignments; minority and complex mixtures retain substantial exclusive read-evidence deficits. These observations motivate separate targeted experiments, not relaxed gates.

Revalidate the complete report with the existing readback verifier:

```sh
python3 benchmarks/native_adapter_mode_readback.py \
  docs/bench/diagnostics/p1-adapter-mode-native-20261126.json \
  docs/bench/diagnostics/p1-adapter-mode-posthoc-complete-20261126.json
```

Exact supplemental report and reader SHA-256 values appear in the complete JSON. This report uses only synthetic identifiers and numerical summaries. The retained host source reports are in the native adapter-mode audit directory and the native-posthoc completion directory.
