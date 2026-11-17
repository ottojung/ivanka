# Intent 002: Default Ivanka invocation is identical in MiCall and benchmarks

**Status: direct default implementation and invocation checks available; full qualification pending.**

## Contract

**There is one supported, unconfigured MiCall integration**, used identically
in ordinary operation and in the qualification benchmark. MiCall invokes
Ivanka's default Rust algorithm with **an empty child environment** and the
three required paired-read/output arguments. When MiCall has nonempty,
independently read-derived G2P contigs from the **same sample**, it also
passes them as `--seeds`:

```text
/absolute/path/to/ivanka --reads1 R1.fastq.gz --reads2 R2.fastq.gz --output contigs.fasta [--seeds same-sample-g2p-contigs.fasta]
```

The bracketed flag is conditional notation, not literal CLI syntax. MiCall
must not invent a seed file merely to satisfy this contract. The paths and
presence of same-sample seeds naturally differ between samples; the
*executable*, decision rule, argument order and built-in behavior do not. MiCall calls this binary directly, not a
Python wrapper. Use an absolute executable path so a truly empty environment
requires no `PATH`; a launch equivalent to `env -i` or
`subprocess.run(..., env={})` expresses the intended child environment.

No environment variables may configure or tune Ivanka when MiCall invokes it,
including `IVANKA_*` seed budgets, selector controls, trimming/tiling
thresholds, thread or resource tuning, or hidden experimental switches.
Verified same-sample read-derived `--seeds` is the **only permitted optional
Ivanka argument** at the MiCall boundary. Seed sequences must not come from
reference genomes, reference-conditioned selection, synthetic truth or
benchmark evaluation. Neither MiCall nor the benchmark may pass config
files, other CLI overrides or alternate binaries. The benchmark must never
receive a specially tuned execution path: it must use MiCall's ordinary
seed-forwarding rule, even when a particular sample has no seeds. The
built-in Rust defaults must pass unmodified.
The benchmark may configure its **own** runner, image selection, timeouts,
scoring and output paths, but may not change the Ivanka child environment or
invocation contract. Seed provenance, invocation parity and all image checks
must be verified by the external benchmark infrastructure, not by adding
checkers or diagnostic scripts inside the MiCall candidate containers.

## Acceptance evidence

1. MiCall launches the Rust binary with `--reads1`, `--reads2`, `--output`,
   and **only when applicable** `--seeds` naming nonempty same-sample,
   independently read-derived G2P contigs; the child environment is empty.
2. Integration tests capture the real MiCall subprocess executable, arguments
   and environment **with and without seeds**. A direct invocation with the
   **same reads and seed file** must produce byte-identical FASTA; a valid
   zero-contig assembly still exits successfully.
3. A build/integration guard prevents installing a wrapper in place of the
   Rust binary and rejects benchmark-only arguments, settings and
   reference-conditioned seeds. Seed provenance and the normal MiCall
   forwarding rule must be verified **outside the assembler container**.
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
the Rust ELF by absolute path with `env={}`, the three required arguments
and optional, proven read-derived same-sample `--seeds`. Historical wrapped
images do **not** meet this intent;
implementation tests and byte-identical output parity cannot substitute
for the still-required physical and expanded numerical qualification. Do not alter the
previously passing release or re-label its results as proof of the new default.

See [Intent 001](001-rust-only-execution.md) for the Rust-only execution
contract, and [the qualification procedure](../testing-improvement-procedure.md)
for benchmark integrity.
