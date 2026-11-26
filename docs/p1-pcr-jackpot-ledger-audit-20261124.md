# PCR-jackpot read-backed support audit (draft evidence, not a rescue)

This is an isolated source candidate. It corrects how repeated observed pair
sequences are counted in read-backed scoring. It does **not** change the
seeded native path used by the measured `pcr_jackpot` cases and is **not** a
fix for any gate failure. No MiCall, controller, image, threshold or scoring
policy change is included.

## Reproduction of the reported violations

The SHA-pinned `gate_multitruth.check_sample(minimum_ratio=0.90)` was applied
to a readback snapshot of candidate `12d8c72` and to the frozen original
results:

* gate SHA256 `03290864ac2aad23b1a0a8d7054c94291ae1f9602588f5241158f913895ba9f6`
* frozen results SHA256 `7e1e81ce253fec2e4052db4843bfc580491c89bbc320a21374058f4297482203`
* readback snapshot SHA256 `b99a3e2277d4588b89200479b1b864a2c756e40cd5487b352d8fc5ffd2a5ed02`

On 16 `pcr_jackpot` cases, 14 violate the combined score >=90% of the best
available rival in both sets; the pinned per-truth comparison fails only
`s013` in both sets. Every candidate Ivanka combined score is byte-identical
to the corresponding frozen score. The reported violations are inherited
baseline outcomes, not a candidate regression.

## Causal notes for the seeded native path

* The cohort generator draws jackpot reads from 13 fixed 270-base fragments
  of a single ~9.6 kb haplotype. Partial native evidence is all that exists;
  the applicable gate is the **relative** final-MiCall comparison to the best
  rival, not absolute reconstruction.
* Each measured case logs a caller-supplied seed, so the native multi-contig
  path is taken and `read_backed::scoring::count` is not executed. The change
  here cannot alter those measurements.
* Post-hoc comparison of final MiCall MAX consensus intervals shows the best
  rival retaining roughly 9 distinct read-supported regions (~2.4-2.6 kb)
  where Ivanka retains roughly 4-5 (~0.7-0.9 kb). These are native
  read-supported subsequences; no reference-derived or fabricated phase is
  involved. Any future native-fragment retention change must preserve that
  property and be tested before any integrated pilot.

## Code change

Repeated byte-identical observed pair sequences are counted once for depth,
breadth and supporting-pair totals. Molecule identity is **not** inferred
(UMIs would be needed); raw observation frequency is retained solely as an
exact tie-break. No truth, reference, family label or abundance threshold
enters the assembler.

## Validation

`cargo test --locked --all-targets`: 77 unit and 51 contract tests pass.
`cargo fmt --all -- --check`: clean. `cargo clippy --locked --all-targets`: no
warnings in changed files. `benchmarks/reference_isolation.py`: PASS.
The added fixture is red on the base commit (`[57, 1000]` observations chosen
as support) and green here (`[19, 2]`, with raw counts `[57, 1000]`).
Standalone default-CLI canaries are byte-identical to base on jackpot and
control families, with and without supplied seeds.

## Status

Draft only. Do not merge. All 14 combined and 1 per-truth jackpot failures,
the low-depth failures, and both mandatory gates remain explicit and FAILED.
No integrated pilot, full replay, physical parity, clinical or release claim
is supported by this evidence.
