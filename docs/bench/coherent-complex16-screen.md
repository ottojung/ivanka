# Four-haplotype coherent-path diagnostic (16 original HXB2-v2 cases)

This source-pinned screen measures all 16 original
`complex_mixture-s000` through `s015` cases from the HXB2-derived,
SHA-256-attested 400-case v2 cohort. It is a **nonqualifying** complement
to the already frozen 32-case `minority_30pct` and `equal_strains`
diagnostic. Neither screen adds, replaces, or relaxes release criteria.

## Why the extra family is necessary

An independent matched comparison of the unchanged 400 inputs between
Rust candidate `224fa079` and original-pair Rust candidate `c6869ae`
found six alignment regressions within the 16 `complex_mixture` cases,
including `s011` (9400 → 4604) and `s006` (9425 → 5509).
These are previously observed results, **not** results of the coherent
candidate. Studying only the two-family 32-case mixed-strain screen risks
missing four-haplotype phase and dominant-consensus failures.

## Scope and isolation

- Every case is selected by its original immutable family and identity,
  not by an assembler score or alignment to known truth.
- The selected `complex_mixture` cases have four nominal haplotypes
  (65%, 25%, 8%, 2%). The runner independently authenticates all 16
  paired FASTQ mates and case manifests before each MiCall invocation.
- The Rust coherent assembler is pinned to `d3a6a141`; its dedicated
  fork-built MiCall image is pinned by full immutable ID, along with
  common MiCall and original paired reads.
- The image reads original FASTQs. Biological truth is available only to
  the independent evaluator after the assembly has finished.
- Original sampled haplotype counts, chimeric-mate and contamination
  metadata are **diagnostic only**. They never affect selection or the
  unchanged fixed-truth score.
- Full MiCall `--denovo --all_projects` retains success/failure journals,
  final MAX score, measured in-container wall time, and other diagnostics,
  with 1,800 seconds per arm and an 8 GiB free-space guard.
- Failed, interrupted, changed or missing source records cannot become
  successes. Resume checks each completed case's recorded execution,
  image and case identities byte-for-byte.

Run only from the isolated pinned source checkout and after completion
of the existing physical-198 and two-family 32-case diagnostics:

```sh
python3 -m benchmarks.expanded.coherent_complex_screen \
  --out /workspace/ivanka-coherent-complex16-screen-20261116
```

The resulting evidence may inform a **new**, separately attested
canonical seven-assembler 198-real + 400-synthetic qualification run.
It cannot substitute for that run, the 90%-of-best-rival floor, the
strict all-nonnegative-exponent alignment and runtime Ψ gates, or
independent molecular validation.
