# Adapter-mode-corrected native comparison (2026-11-26)

**Not integrated MiCall, not a qualification result.**

The earlier direct-native control used an explicit empty seed FASTA. The frozen
adapter only passes `--seeds` when its sample-derived seed file is nonempty.
The new comparison reproduces that distinction. It compares the 950fe331
combined binary (SHA-256 `8569290d...c3786`) with the exact 7a445488
PCR extension binary (`ec5eb835...31563`, source unchanged at 19386765),
with frozen adapter SHA-256 `966c6970...00900`. Full pins, input digests,
output/log digests, seed flags and observations appear in the native report.

Use original, untrimmed R1/R2 reads and the same retained same-sample
`assembly_*/seeds.fasta` (exactly one per case). Predeclare the eight families
and all 16 cases each. Invoke each binary with `--reads1 R1 --reads2 R2
--output OUT`; append `--seeds SEED` if and only if the file is nonempty.
Alternate old/new and new/old order by case index. No hidden truth, references
or comparator outputs are opened by the native runner. This is not equivalent
to an integrated MiCall run, whose actual trimmed read input and downstream
stitch/remap/counting differ. Native limits were 30 s per arm, 512 MiB address
space (not a container RSS cap), 600 s total, 33 GiB free disk and 4 GB host
MemAvailable. Each child ran in a separate session with empty environment;
check the input and binary digests before and after each invocation.

## Results

- 256/256 native invocations succeeded; all 128 pairs have identical input
  and seed hashes. 112/112 non-PCR pairs produce byte-identical FASTA.
- All 16 seeded PCR-jackpot pairs change. Posthoc mean read-observed canonical
  truth 31-mer recovery is 42.63% → 92.44%; two native alignment fractions
  improve, none regress. This does **not** imply comparable improvement in final
  MiCall consensus alignment, or long-range phase.
- Posthoc evaluation stopped at its reserve guard after 69/128 cases. The
  remaining 59 were not evaluated; their native executions are complete.
  All PCR, equal-strain, coverage-hole and complex-mixture cases and five
  minority cases were evaluated. The native equality proof for the 112 controls
  is independent of the partial posthoc evaluation.
- The current combined candidate's equal-strain mean observed exclusive-k-mer
  recovery is 87.73% across its 32 evaluated abundant truths. Do not compare
  this mean directly to a different subset's historical median or infer a
  passing floor.

Run the report verifier (does not invoke an assembler):

```sh
python3 benchmarks/native_adapter_mode_readback.py \
  docs/bench/diagnostics/p1-adapter-mode-native-20261126.json \
  docs/bench/diagnostics/p1-adapter-mode-posthoc-partial-20261126.json
```

The original execution and posthoc scripts are retained on the benchmark
host with SHA-256 a014fa28975a82af354a609dfe168b7054de2329197d137aa999312f2aeb59e4
and e34c81bd50db81de0ebaf5856554a9e3a7a85d6f96db50c0ba1908c47fcf6587.
Posthoc uses existing canonical-k-mer, read-support and alignment evaluators
only after validating both output hashes. The reports contain synthetic
identifiers, hashes and counts, not raw sequence or clinical sample IDs.
