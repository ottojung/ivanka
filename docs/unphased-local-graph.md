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
  consistent unique paired signatures (default `--min-joint-pairs 1`,
  `--min-consistent-signatures 1`; raise for stricter use).
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

Results (private `/tmp/opencode/ivanka-graph-TtLs4qf3/private-out/`):

- **S48** `S48-unphased-local-graph.json` SHA256
  `33a7c9261ee76ab03733f3107234c3fe72f062e23639e7699c0fa5c91454e6fe`:
  3 nodes, 2 tentative local-only edges from the emitted 31bp shared local node
  to marker alleles A/G, each requiring direct same-qname Q15 observation
  (4+35 joint pairs/signatures for edges from the emitted allele to markers A/G; observed non-emitted block allele edges preserved separately). No
  transitive edges, no molecule/phase claims.
- **S12** `S12-unphased-local-graph.json` SHA256
  `dc6528fec0aad2cef8a9f8594f464f34260f914fc3dfb7c44e0116187b33675a`:
  0 eligible shared local nodes, 0 edges to emitted shared node; explicit
  `no_eligible_shared_local_node_emitted` and
  `competing_minority_allele_fraction` preserved.

## Tests

`benchmarks/test_export_unphased_local_graph.py` covers S48-eligible emitted
node with direct same-qname edge counts, S12 veto/no node, no transitive
inference, no molecule duplication claims, low-Phred/ambiguous exclusion by
upstream direct evidence, mask/region mismatch, manifest/FASTA hash mismatch,
protected output roots, and phase/molecule/transitive flags false.
