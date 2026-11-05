# Optional typed SHARED/UNPHASED local graph (research prototype)

`benchmarks/export_unphased_local_graph.py` builds a **read-only, typed JSON
graph** from authenticated local evidence. It is a research representation, not
a consensus/assembly pipeline change.

## Inputs (required, source-authenticated by SHA256)

- **#169** `ivanka.shared_unphased_observation_export.v1`: shared unphased local
  observation with source checksums and strict raw FASTQ mate provenance flags.
- **#170** local node FASTA + `ivanka.unphased_shared_local_nodes.v1` manifest:
  consumed only when `locally_supported_unphased_node_emitted` is true. Vetoed
  manifests (e.g. S12 18.6% competing allele) produce no eligible shared node.
- **#164** direct original-pair marker sidecar
  `ivanka.shared_unphased_evidence_direct.v2`: same original strict read-pair
  QNAME observations of complete local block and marker, Q15, with consistent
  distinct pair-sequence signatures.

## Safety invariants

- Shared local node is **one node** with observed local sequence; no molecule
  duplication and no competing-haplotype assignment.
- Missing insert bases are **never imputed**.
- A node/segment connects to a haplotype-specific marker only when the **same
  original strict read-pair QNAME** directly observes both at Q15 with enough
  consistent unique paired signatures (default `--min-joint-pairs 5`,
  `--min-consistent-signatures 5`; raise for stricter use).
- Edges are **tentative/local-only**, never full-length phase.
- **No transitive inference**: only direct v2 same-qname observations become
  edges; no path traversal.
- Negative/unknown evidence is explicit in `negative_unknown`.
- Original reads/FASTQ and MAX consensus immutable; no 198/IVA/reference/gate
  changes; no independent-molecule or haplotype-depth claims.

## CLI

```bash
python3 benchmarks/export_unphased_local_graph.py \
  --observation-json S48-shared-unphased.json \
  --local-node-fasta S48-local.fasta \
  --local-node-manifest S48-local.json \
  --direct-v2-sidecar S48-direct-v2.json \
  --output PRIVATE/S48-unphased-local-graph.json \
  --expected-observation-sha256 <sha256> \
  --expected-local-fasta-sha256 <sha256> \
  --expected-local-manifest-sha256 <sha256> \
  --expected-direct-v2-sha256 <sha256> \
  --artifact-dir FROZEN_RUN/SAMPLE/ivanka \
  --screen-ledger PRIVATE/frozen198-v2-direct-summary.json \
  --screen-sha256 5d6caefe76cfee3ec368223482e2e36e91dd82d5ce92d52dc54b93eccda4c716 \
  --sample SAMPLE \
  --original-fastq-r1 ORIGINAL_R1.fastq.gz \
  --original-fastq-r2 ORIGINAL_R2.fastq.gz \
  --protect-root /workspace/denovo-example-io-1 \
  --protect-root /workspace/ivanka-isolated-pairs-full198-results-20261103
```

## Isolated S48/S12 (Nov 5 2026, marceline-dev, private outputs)

Read-only authenticated artifacts used (no source/FASTQ mutation, no full198/IVA):

| artifact | SHA256 |
|---|---|
| S48 observation #169 | `98c67849282762ea64b1e688ad56329e4cec0c4ad9b3752d3d49d7167608d08c` |
| S48 local FASTA #170 | `2be5ca970ade7ffbb80cb1c1e484b40228028711345f812128328aaf49c27b55` |
| S48 local manifest #170 | `a851655b3e2e530b69549d470550d30489a92a7323814b3a1004dd899be70db3` |
| S48 direct v2 #164 | `f42a097d371238da02d8fd00f279555048c5b6716cd0ac024d48c9752c08f92a` |
| S12 observation #169 | `4b491b2b322f5bb4bd83dd5a6809b038ae2fd4a536a49b27f8bbc155f54da802` |
| S12 local FASTA #170 (empty/veto) | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| S12 local manifest #170 | `c92855ec4bae72254a628f07321db48b416b52317facb6d2464d037e238d841f` |
| S12 direct v2 #164 | `7fca53dcad1a291b9e7851f97712acdf44f571e04db521c4dcc2fce9e8b9597f` |

Results (private `/workspace/ivanka-lab/unphased-local-graph-reviewed-20261105/`):

- **S48** `S48-unphased-local-graph.json` SHA256
  `be1bf10da124a536a846d0c2a2df3f9cbf6bec97c38b672c0682d1706d41a0f6`:
  4 nodes, one tentative local-only edge from the emitted 31bp shared local node
  to one directly observed marker allele, each requiring direct same-qname Q15 observation
  (35 directly observed paired QNAMEs and 35 consistent paired-sequence signatures for the one accepted local edge; four-pair marker evidence was withheld). No
  transitive edges, no molecule/phase claims.
- **S12** `S12-unphased-local-graph.json` SHA256
  `4e1d950479619ae986f5bc0436405ff6da68bd992ce8e0e3c63f5e7a1403fce5`:
  zero promoted graph nodes and zero edges; explicit
  `no_eligible_shared_local_node_emitted` and
  `competing_minority_allele_fraction` preserved.

## Tests

`benchmarks/test_export_unphased_local_graph.py` covers S48-eligible emitted
node with direct same-qname edge counts, S12 veto/no node, no transitive
inference, no molecule duplication claims, low-Phred/ambiguous exclusion by
upstream direct evidence, mask/region mismatch, manifest/FASTA hash mismatch,
protected output roots, and phase/molecule/transitive flags false.


## Independent original source replay and stronger safeguards

A self-consistent set of JSON paths and SHA256 values does not establish
independent source provenance. The CLI now requires the caller's selected
original per-sample MiCall directory, exact sample identity, independent
frozen-cohort direct-mask ledger and externally known SHA256, original R1/R2
FASTQ mates, and caller-pinned SHA256s for all four graph input artifacts.

Before publishing it replays both source-bound stages from the original
data: first the complete #170 read-derived local node and exact safety
decision, then the #164 v2 same-original-strict-QNAME direct links. Both
reattest original paired FASTQ mate sequence and Phred qualities. It checks
exact reference membership, region, masked interval, source hashes, and
exact original FASTA and manifest. Missing or altered evidence fails closed.
A pure in-memory graph constructed without replay is explicitly marked
source_verification.empirical_use_permitted=false.

Tentative local edges now require at least FIVE direct original paired
QNAMEs and FIVE consistent distinct paired-read sequence signatures,
rather than the previous default of one. These signatures are not proven
independent physical DNA molecules. Transitive/distant haplotype phase
remains unknown. Where the #170 local node is vetoed, NO marker or other
unqualified sequence is promoted to a graph node: S12 has zero nodes
and zero edges, with observed evidence retained only as unknown diagnostics.

Genuine immutable S48 original FASTQ/MiCall replay produced four typed
nodes and one tentative direct local edge supported by 35 paired reads
and 35 consistent paired sequences; its four-pair association was withheld.
S12 had no nodes or edges. Private verified result SHA256s:
S48 be1bf10da124a536a846d0c2a2df3f9cbf6bec97c38b672c0682d1706d41a0f6
S12 4e1d950479619ae986f5bc0436405ff6da68bd992ce8e0e3c63f5e7a1403fce5

No original MiCall MAX, IVA baseline, reference panel, raw FASTQ,
frozen 198 numerical qualification or signed-power PSI changed.
The full repository regression suite passes 606 Python tests, six skipped.
