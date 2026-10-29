# Riva experiment inventory (2026-10-28)

## Integration policy

- **One canonical MiCall A/B integration:** PR #7, branch `fix/podman-seeded-comparison`.
- **Archived performance trial:** PR #10 closed after the unchanged 7-sample benchmark finished in 839.3 seconds; branch `experiment/podman-bowtie-threads` is retained, not merged.
- Former draft PRs #1 and #3–#6, #8–#10 were closed only after source branches/commits were preserved or incorporated.
- This index lists worktrees; it does not imply that untested experiments are accepted or should be merged.
- The benchmark FASTQs, IVA baseline caches, result directories, and historical slow-seven dataset remain private and outside Git.

## Preserved worktrees

| Branch | Checkout | HEAD | Worktree changes |
|---|---|---|---|
| `main` | `/workspace/riva` | `3942a8b7f0` | clean |
| `experiment/riva-approx-overlaps` | `/workspace/riva-approx-overlaps` | `b0509bc0a7` | modified |
| `experiment/bounded-branching` | `/workspace/riva-bounded-branching` | `5b34741dcb` | clean |
| `fix/riva-cycle-boundary` | `/workspace/riva-cycle-boundary` | `f4b35b25b1` | clean |
| `fix/dense-seed-postings` | `/workspace/riva-dense-seeds` | `8f2447f9b6` | clean |
| `experiment/riva-diverse-contigs` | `/workspace/riva-diverse-contigs` | `63a082201a` | clean |
| `experiment/riva-dominance2` | `/workspace/riva-dominance2` | `c4e8140a0f` | clean |
| `experiment/riva-error-overlaps` | `/workspace/riva-error-overlaps` | `1769d3fa85` | clean |
| `experiment/read-overlap-extension` | `/workspace/riva-extension` | `a2bac45024` | modified |
| `fix/riva-extension-cycles` | `/workspace/riva-extension-cycles` | `9af720b10d` | clean |
| `experiment/branch-resolved-overlaps` | `/workspace/riva-extension-stops` | `5b34741dcb` | clean |
| `benchmark/full-micall` | `/workspace/riva-full-micall` | `1a30c921b4` | clean |
| `feature/g2p-seeds` | `/workspace/riva-g2p-seeds` | `001af7f500` | clean |
| `experiment/riva-global-seeds` | `/workspace/riva-global-seeds` | `f9e2fabd20` | clean |
| `experiment/index-only` | `/workspace/riva-index` | `a2bac45024` | modified |
| `fix/internal-seed-overlap` | `/workspace/riva-internal-overlap` | `1993fda53f` | clean |
| `experiment/riva-late-cycle` | `/workspace/riva-late-cycle` | `6089e2ce10` | clean |
| `experiment/riva-long-cycle` | `/workspace/riva-long-cycle` | `a115fc7a90` | clean |
| `experiment/riva-one-indel` | `/workspace/riva-one-indel` | `66b0e9eb58` | clean |
| `fix/podman-seeded-comparison` | `/workspace/riva-podman-benchmark` | `85e78b1a9a` | clean |
| `experiment/podman-bowtie-threads` | `/workspace/riva-podman-bowtie` | `da03b03209` | clean |
| `benchmark/podman-g2p` | `/workspace/riva-podman-g2p` | `b6e2711d2c` | clean |
| `experiment/podman-parallel` | `/workspace/riva-podman-parallel` | `241c55e4dc` | clean |
| `fix/qualification-global-cap` | `/workspace/riva-qualification-global-cap` | `2bdc6b1561` | clean |
| `experiment/lower-consensus-ratio` | `/workspace/riva-ratio` | `a2bac45024` | modified |
| `experiment/low-dominance` | `/workspace/riva-ratio1` | `a2bac45024` | modified |
| `experiment/riva-seed-search` | `/workspace/riva-seed-search` | `9af720b10d` | modified |
| `experiment/riva-sensitive` | `/workspace/riva-sensitive` | `1684217e1d` | clean |
| `experiment/riva-short-k` | `/workspace/riva-short-k` | `167126b17b` | clean |

## Evidence and next decisions

- Original slow-seven stitcher-only diagnostics are NOT full-MiCall evidence; one experimental cycle-boundary change passed 3/7.
- Genuine fast-seven A/B outputs: `/workspace/riva-fast7-20261028-results`; all seven must be qualified by one 40-minute invocation.
- Old HIV HXB2 scoring is invalid for HCV and V3. PR #7 now evaluates those against their own final IVA MAX consensus.
- Investigate NS5a 2054-base IVA versus 639-base Riva result; the dominance2 and sequencing-error-tolerant read-overlap variants are under A/B testing.
- Retain all branch refs and experiment histories until comparative results establish a safe next step.

Additional isolated work in this preserved branch: commit 8b786bc adds bounded 10-base trim-and-retry, and 2e9ddcf adds a high-support, reference-free solid-kmer graph fallback. The graph variant has 14 passing Rust tests and was built as localhost/riva-micall-riva:solidgraph. These changes are NOT accepted into PR #7 without complete real MiCall evidence.

## Measured HCV-NS5a seed-selection bias (2026-10-28)

Only for diagnostics (not as input to Riva), compared HCV-NS5a S101
candidate k-mers with the genuine IVA raw 2169-base contig.
The original global-highest-500 seeds match only genomic bins 0-1199,
while a deterministic log2-read-abundance round-robin across 500 seeds
has matches throughout bins 0-2168. The second half is not missing
read coverage: its individual 31-mer counts are generally 50-200+ in
just the first 50k paired reads. This exposes a structural bias in the
original fixed-size seed search, not an HXB2 scoring artifact.

Experimental commit 66b0e9e on preserved branch
`experiment/riva-one-indel` implements that balanced seed search,
with 16 passing Rust tests; the immutable image
`localhost/riva-micall-riva:depthbalanced` is based on the same MiCall
IVA image and changes only the Riva executable. The full-MiCall
Riva-only 7-sample run was started as Lubko job
`76a1dec8-3016-4ec9-91bd-bb814d62970d` using the exact verified
IVA controls and dataset; no acceptance claim is made until results.
