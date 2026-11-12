# Intent 001: Ivanka executes entirely in Rust

**Status: required target; not yet implemented.**

## Contract

All Ivanka functionality required to produce its assembled FASTA for MiCall
must be implemented and executed in the **Ivanka Rust executable**. This
includes read-backed contig selection, ranking, filtering, trimming, supported
island selection, and tiling. The public production entry point is the Rust
binary, not a Python script that invokes the Rust assembler. **MiCall calls
Ivanka directly**, with no Ivanka-owned wrapper or intermediate selector.

Python is permitted only for **benchmarking and tests**: generating
synthetic data, executing benchmark jobs, scoring and analyzing results,
and reproducing scientific experiments. Benchmark code must not be installed into
the Ivanka production execution path or used to change its emitted contigs.
MiCall's own implementation language and its downstream processing are not
constraints on the *Ivanka* implementation: MiCall can invoke a Rust process
from its existing integration code, but may not delegate assembly to an
Ivanka Python wrapper.

## Acceptance evidence

1. The executable launched at MiCall's assembler boundary is the Rust Ivanka
   binary itself. The installed `ivanka` path resolves to that executable,
   not to a script, Python interpreter, shell trampoline, or helper service.
2. The entire read-to-contigs path, including read-backed selection and
   trimming/tiling, runs without a Python interpreter or Python modules.
3. Integration tests inspect the actual child process, verify its executable
   identity, and confirm that it is invoked directly by MiCall.
4. Regression and parity tests compare the Rust implementation against the
   frozen reference-blind read-backed behavior, including empty FASTA,
   read pairing, retained read evidence, trimming offsets and overlapping
   tiles. A new candidate must also pass the genuine full MiCall benchmark.
5. Benchmark Python stays outside the deployed assembler image and cannot be
   consulted by the Rust process at runtime.

## Scope and transition

The existing frozen passing image uses a Python read-backed selector and is
**historical evidence, not compliance with this intent**. Moving the selector
into Rust is pending; do not present the old wrapped image as satisfying this
contract. Preserve frozen evidence while implementing and qualifying the
Rust-only direct integration. No reference sequences or evaluation scores may
enter Ivanka; the separate reference-blindness rule remains absolute.

See [Intent 002](002-default-invocation-parity.md) for the required invocation
contract, and [the assembly objective](../assembly-objective.md) for the
scientific goal.
