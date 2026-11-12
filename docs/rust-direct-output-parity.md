# Direct Rust read-backed output parity

**Scope: native assembly output equivalence, not a new MiCall qualification.**

The ordinary, environment-free Rust `ivanka` was invoked with **only**
`--reads1`, `--reads2`, `--output`. For every sample, an independent
invocation of the previously default-configured Python-wrapped image
assembled the **same original paired FASTQs**. Both final FASTAs were
hashed and compared byte-for-byte, including headers, contig choice,
supported-island clipping, tile boundaries and overlaps.

| Item | Attested observation |
|---|---|
| Original paired-read samples | 198 |
| Exact output matches | **198/198** |
| Missing outputs, mismatches or failed commands | **0** |
| Original FASTQ manifest SHA-256 | `4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192` |
| Wrapped comparison image ID | `96734c50c99bc3d5b2a5b4606297b91658c4cd18eed917ce789057953b0ff32a` |
| Direct Rust test binary SHA-256 | `919631e9720fd3bfa9a371710e30d382c4cd948940dc29bde173b78c80acc85c` |
| Full recorded comparison JSONL SHA-256 | `a75c007be92b1271490a647952c386564a47c2510dad63b8e81ffb37545c2474` |
| Recorded comparison artifacts on marceline-dev | `/workspace/ivanka-rust-direct-exhaustive-parity-20261112/` |

Under concurrent, non-isolated direct assembly runs, the sum of
wall-clock measurements across the 198 samples was approximately
**792 seconds for Rust** and **1,299 seconds for the wrapper**, with
196/198 individual Rust runs faster. These are not the independent
in-container MiCall monotonic timings, and do **not** establish the
required all-exponent runtime Ψ criterion. The manifest reflects
execution under real host contention and is not a definitive runtime
benchmark.

**Remaining obligations:** Verify the source-pinned, committed Rust image
as MiCall's direct ELF subprocess with `env={}` and exactly three CLI
arguments; run the complete authentic 198-sample MiCall comparison and
strict alignment/runtime Ψ(r)>0 verification for every real r≥0;
also pass the mandatory expanded seven-assembler benchmark. Historical
wrapped-image numerical success is not automatically inherited.
