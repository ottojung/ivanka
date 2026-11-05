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
- Only genuinely supported direct alternative-containing links belong in
  the graph edges collection. Rejected combinations live exclusively in
  negative_unknown, never in a misleading false-status graph edge.
- Unqualified candidates are withheld; S12 parent-6 positions 344/394 remain
  withheld when the aligned conservative reports mark them unqualified.
- Reject repeated/missing unordered candidate pairs, impossible distinct
  signature counts, mismatched source pair totals/Q15 quality floors, and
  contradictory qualification flags.
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
- S48 strict graph output SHA256: `996c63134648dae6653f165697ed31cd15f7ea28efb65b904dc0213b9be866a6`
  - 2 supported direct alt/ref combinations: 217 G alt / 395 T ref (33 IDs/signatures), 677 T alt / 395 T ref (17 IDs/signatures).
  - 217 A>G / 677 C>T alternative/alternative withheld (1 observed joint ID/signature, below floor); no transitive path created.

- S12 node SHA256: `8eaafc26ee6e9be48ddade7d3dd8328f85fa9e06c51b5ac2f6b8f4c3b358f87d`
- S12 links SHA256: `5764c48dd686027c7d94d5315dcbd65b9b5a205473dab58e7d1b9ec3d20517fc`
- S12 strict graph output SHA256: `db40f002db1424907d03753211d3ce6e2a295aee72beb9aff84c38407e578953`
  - 0 accepted edges and 1 qualified SNV site node. Positions 344/394 are
    not graph nodes, but their evidence and rejection reasons remain
    available in diagnostics. Position 458 has no direct supported
    cross-candidate alternative combination.

Private initial graphs were written under `/tmp/opencode/ivanka-TtLs4qf3-artifacts/`.

## Trust and CI boundaries

The command-line program verifies the *report bytes* against two separately
caller-pinned SHA256 digests and checks the reports refer to exactly the
same original read/FASTA/audit source SHA256s. It does **not** replay FASTQs
inside this graph stage; provenance and original mate/Q15 counts must have
been previously authenticated using the #175 and #176 source contracts.
The sample label supplied on the CLI is not independently authenticated
by the graph builder. These limitations appear explicitly in graph metadata.

Genuine S48/S12 replay tests use private preserved reports on marceline-dev.
They are skipped on GitHub CI workers where those files are absent; synthetic
counterexamples still run in CI and cover unsupported edges, missing direct
evidence, transitive mistakes, forged source signatures and contradictory
node/link counts.

## Final isolated genuine replay output

The source-bound CLI outputs were preserved separately in the
/workspace/ivanka-lab/snv-strict-typed-graph-20261105/ directory,
using exact caller-pinned report hashes. In S48 the graph has six nodes,
two accepted direct allele-combination edges and eleven unknown/withheld
diagnostics. S12 has one qualified site node, zero edges, and fifteen
unknown/withheld diagnostics. Unqualified sites cannot become graph nodes.

Both reports are experimental local-read diagnostics only. No original
input or full MiCall MAX was modified, and no full-length haplotype
phase or independent molecule identity is claimed.
