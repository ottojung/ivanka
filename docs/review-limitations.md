# Native assembler limits and validation obligations

This document describes **current behavior**, not guarantees that a
benchmark pass implies clinical or molecular validity.

| Area | Current behavior | Validation needed before changing it |
|---|---|---|
| Low seed depth | Original read-backed seeds need >=15 sampled occurrences of a canonical 31-mer; insufficiently supported reads can yield a successful empty FASTA | Synthetic low-coverage controls plus full MiCall A/B qualification for a lower threshold or adaptive fallback |
| Contig ranking | Extension-supporting read records per assembled base dominate unless span favourites are reserved; a short fragment can displace a long one | Tests of dominant-contig retention and authentic 198-sample final-MAX score/runtime Psi |
| Extension ties | A 50/50 A/C/G/T vote is accepted when minimum ratio is 1; lexical base ordering breaks ties | Sequencing-error, mixture and phased controls; genuine benchmark to assess a stricter ratio |
| Pair evidence | Original read identifiers/order are validated, but native extension indexes mates independently | Deterministic properly paired placement and original-molecule/allele accounting; independent genotype/phase checks |
| Resource bounds | Read pairs are unlimited by default and stored with reverse complements and index hits; `--max-pairs` can bound input | Stress tests and measured memory budgets for any streaming or memory-limit redesign |
| Index width | Sparse hit offsets are `u16`; reads above 65,535 bases now error rather than disappearing | Explicit long-read representation and correctness tests before widening |
| Overhang cache | Up to 256 entries; observations with over 1,000 overhangs are recomputed | High-depth benchmark and bounded-byte caching with exact-output tests |
| Read-backed wrapper | Native default output cap 16, wrapper post-selection default 1 source candidate, possibly several overlapping tiles | Same source/read evidence, fragment-depth and downstream performance checks |

The high-exponent runtime Psi condition is exact but sensitive to the
largest absolute regression. A noisy container may control tail
dominance; repeat runs are useful diagnostics. They do not change the
pre-agreed Psi test or permit dropping an unfavourable sample.

The 198-sample passing tag is immutable. A proposed change to ranking,
extension votes, proper pairing, cache policy or seed thresholds must
be independently qualified as a **new** candidate before it is called
numerically passing. A pure documentation or input-validation correction
must not be reported as a newly repeated 198-sample experiment.


## Qualification provenance

The frozen 198-sample numeric pass was measured with a Python read-backed
selector/trim/tile wrapper and 50 primary / 20 supplementary native seeds.
The Rust CLI now defaults to the same 50/20 seed budgets, but without
the read-backed selector, trimming and tiling it is still not the fully
qualified execution configuration. The same physical cohort was used to tune
several heuristic thresholds, so a pass is not evidence of held-out
generalization. The source- and base-pinned image builder is
`scripts/build_read_backed_image.sh`. See
`docs/read-backed-selection-experiment.md` for the complete boundary.

Any new native implementation of the wrapper should be introduced
behind explicit options with a frozen Python-versus-Rust differential
harness, a versioned configuration manifest and read-pair accounting
checks. Only a fresh physical 198-sample MiCall A/B comparison can
replace the existing numeric qualification, while separate held-out
cohort evaluation is needed for an unbiased performance claim.
