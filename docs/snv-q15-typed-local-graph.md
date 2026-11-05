# Typed local graph consumer for SNV Q15 node (#175) + direct pair links (#176)

`benchmarks/export_snv_q15_typed_local_graph.py` consumes two authenticated,
source-bound read-only reports:

- `ivanka.unphased_snv_original_fastq_q15.v1` (local SNV node screen, #175)
- `ivanka.snv_q15_direct_original_pair_links.v1` (direct original pair links, #176)

It emits `ivanka.snv_q15_typed_local_graph.v1`, a research-only typed local
graph that preserves per-allele observed node identity and explicit unknown or
unobserved edges.

## Contract

- Inputs must be independently SHA256-pinned by the caller.
- The two reports must have identical `source_sha256` for audit TSV, ordinary
  FASTA, and original R1/R2 FASTQs.
- Candidate identities and qualification flags must align exactly; mismatches
  fail closed.
- Supported alternative-containing combinations require the same original R1/R2
  Q15 pair evidence and distinct consistent paired-sequence support from report
  #176. The consumer cannot weaken report thresholds.
- `reference_reference` co-observation is recorded as non-variant context only.
- Unqualified candidates are withheld; S12 parent-6 positions 344/394 remain
  withheld when the aligned conservative reports mark them unqualified.
- No transitive closure/edge imputation, no concatenated 31-mers to fabricate
  full-length phased sequences, no duplicated original QNAME coverage, no PCR
  duplicates treated as independent molecules, and no ordinary MiCall MAX/contig
  mutation.

## Relation to PR #171

This is a compatible typed local-graph consumer for the SNV Q15 report pair,
following PR #171's conservative safety posture (explicit unknowns, no phase/
molecule/MAX claims, source-bound inputs). It does not replace
`export_unphased_local_graph.py`, which consumes #169/#170/#164 shared-unphased
artifacts.

## Frozen report validation (read-only, no MiCall/IVA/frozen198 runs)

Using aligned immutable reports on marceline-dev:

- S48 node SHA256: `2ca6eb0f9639f5f2d4e2199f96c95d2f64aa5d881e27df6b8e41d627addd2c22`
- S48 links SHA256: `1bedd0bae50be0602940303c9fac83213441d2c960d027087169d9c0932ecabb`
- S48 graph output SHA256: `9c58bc0bc3c303624d6d3fa76784c6c84f51577b6db4e4ab7c89ad216371f7a2`
  - 2 supported direct alt/ref combinations: 217 G alt / 395 T ref (33 IDs/signatures), 677 T alt / 395 T ref (17 IDs/signatures).
  - 217 A>G / 677 C>T alternative/alternative withheld (1 observed joint ID/signature, below floor); no transitive path created.

- S12 node SHA256: `8eaafc26ee6e9be48ddade7d3dd8328f85fa9e06c51b5ac2f6b8f4c3b358f87d`
- S12 links SHA256: `5764c48dd686027c7d94d5315dcbd65b9b5a205473dab58e7d1b9ec3d20517fc`
- S12 graph output SHA256: `74206cfcbf44e0a60d8e779182f78c22a6bed582d4ffef3c276805ad9261f3b9`
  - 0 accepted edges. Positions 344/394 withheld due unqualified conservative node status (parent-offset/9-pair-class ambiguity in aligned reports); position 458 has no supported cross-candidate alternative combination.

Private graph outputs were written only under `/tmp/opencode/ivanka-TtLs4qf3-artifacts/`.
