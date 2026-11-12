# Intent 002: Default Ivanka invocation is identical in MiCall and benchmarks

**Status: direct default implementation and invocation checks available; full qualification pending.**

## Contract

**There is one supported, unconfigured Ivanka invocation**, used identically
by MiCall in ordinary operation and by the qualification benchmark. Ivanka
must be invoked with the default algorithm and **an empty environment**. Its
only command-line arguments are the three necessary paired-read/output inputs:

```text
/absolute/path/to/ivanka --reads1 R1.fastq.gz --reads2 R2.fastq.gz --output contigs.fasta
```

The paths naturally differ between samples; the *executable*, argument names,
order and default behavior do not. MiCall calls this binary directly, not a
Python wrapper. Use an absolute executable path so a truly empty environment
requires no `PATH`; a launch equivalent to `env -i` or
`subprocess.run(..., env={})` expresses the intended child environment.

No environment variables may configure or tune Ivanka when MiCall invokes it,
including `IVANKA_*` seed budgets, selector controls, trimming/tiling
thresholds, thread or resource tuning, or hidden experimental switches.
Neither MiCall nor the benchmark may pass optional seed files, config files,
CLI overrides or alternate binaries. The generic CLI may retain separately
supported inputs such as `--seeds`, but they are **not allowed** in this
three-argument MiCall/qualification invocation. The benchmark must never
receive a specially tuned execution path. The ordinary built-in Rust defaults must pass unmodified.
The benchmark may configure its **own** runner, image selection, timeouts,
scoring and output paths, but may not change the Ivanka child environment or
invocation contract.

## Acceptance evidence

1. MiCall's integration launches the Rust binary with **exactly**
   `--reads1`, `--reads2`, and `--output` in the agreed order,
   with no additional flags and an empty child environment.
2. A contract test captures the real MiCall subprocess executable, argument
   list and environment, and compares them to a direct unconfigured
   standalone invocation on the same reads. Their FASTA results must be
   byte-identical; a valid zero-contig assembly still exits successfully.
3. A build/integration guard prevents installing an Ivanka wrapper in place of
   the Rust binary, and rejects benchmark-tuned environment settings or
   additional CLI arguments at the assembler boundary.
4. Both mandatory numerical gates must be passed using this identical
   default executable and invocation: the **full unchanged physical
   198-sample MiCall/IVA benchmark** and the **expanded 198-real +
   400-synthetic seven-assembler benchmark**. Passing only one gate,
   unit tests, or reproducing tuned image settings is **insufficient**.
5. The default invocation is declared passing only when all required
   per-sample, runtime and alignment Ψ(r) criteria pass; any
   failures remain visible, and original benchmark records are preserved.

## Scope and transition

The native Rust candidate uses built-in 50/20 seed budgets and read-backed
postselection with no environment-controlled algorithm. MiCall launches
the Rust ELF by absolute path, with `env={}` and only the three reviewed
arguments. Historical wrapped images do **not** meet this intent;
implementation tests and byte-identical output parity cannot substitute
for the still-required physical and expanded numerical qualification. Do not alter the
previously passing release or re-label its results as proof of the new default.

See [Intent 001](001-rust-only-execution.md) for the Rust-only execution
contract, and [the qualification procedure](../testing-improvement-procedure.md)
for benchmark integrity.
