# Native seed-novelty review: biological correctness and frozen-runtime risk (2026-11-24)

Independent source-only review for issue `LzYdEFCZGIyc0Ni1w9S0f3-municipal`.
Review base: candidate commit `7dbdbaefb1155f634a760034287cc9d480099bf9`
(PR412, parent `e47f841f799e9b6e46aad23d9e11f7bcbc8e0446`, image
`73f29f0233da2ecd1ab126178cba4deb9e246bff5a6f770ab021a8f36d71081b`).
The running candidate, its controller, MiCall source, frozen OCI images and
all 4,634 original arms were not changed. No new sample run, OCI build,
original-arm rerun or PX work was performed.

## 1. Actual Rust default `--seeds` semantics vs the frozen adapter

`src/assembler/run/mod.rs` computes `standard` false whenever `--seeds` is
present, so a seeded invocation takes the native multi-contig FASTA path in
`src/assembler/run/write_results.rs`. In the reviewed candidate the
`skip_matching_seeds` argument is `config.seeds.as_deref()`: whenever a seed
FASTA is supplied **and at least one read pair is admitted**, `keep_indices`
removes every assembled contig whose canonical (lexicographically smaller of
the sequence and its reverse complement) form equals a canonical supplied
seed. With zero admitted read pairs the original seed passthrough remains.

The frozen original adapter (SHA256
`966c6970939b867521a015f0b4d4e5312558dca366089d54df552afd2c500900`,
byte-identical in parent and candidate images) passes only `--reads1`,
`--reads2`, `--output` and, when same-sample G2P contigs exist in the CSV,
`--seeds` with an empty child environment. It never passes an adapter-side
dedup flag. MiCall's frozen downstream separately injects those same G2P
contigs from `merged_contigs.fasta`, so removing only the native exact copies
does not remove the physical sequence end-to-end.

**Demonstrated standalone-API semantic change (not a MiCall regression):** a
direct caller that supplies a seed FASTA containing the exact native dominant
contig and ordinary read pairs obtains an empty assembly FASTA; with
`--max-pairs 0` the same seed is emitted unchanged. The candidate's own design
note already records this contract. It is captured as a regression test so it
cannot become silent. A direct API caller must preserve its own seeds when it
needs them; the frozen MiCall integration does so downstream.

## 2. Biological-correctness properties of exact/RC suppression

Suppression compares whole canonical sequences, not k-mers, lengths or
references. New source-only unit tests (`seed_duplicates/tests_bio.rs`,
`tests_phase.rs`), a ranking test (`ranking_tests/minority_retention.rs`) and
a contract test (`contract/seeds/standalone.rs`) show:

- exact seed copies and their reverse complements are removed;
- a single-substitution minority contig (the 15%-abundance hazard) is retained;
- a two-seed recombinant/mosaic contig is retained;
- partially overlapping (strict substring) and fully disjoint contigs are retained;
- the reverse complement of a minority variant is retained (matching is exact, not approximate);
- an empty seed FASTA suppresses nothing.

No reference, truth panel, score or evaluator output enters `keep_indices`; it
reads only the caller's FASTA. `python benchmarks/reference_isolation.py`
passes. Reverse-complement canonicalisation is orientation-neutral double-
stranded DNA handling, not a reference-conditioned ranking.

Read-derived support is considered before suppression: the ordinary selection
already ranks by read-support density and protects the seed prefix, and the
suppression runs afterwards. Phase is not fabricated: unknown pair phase does
not make a distinct contig a duplicate, and an unphased near-variant is not
promoted to a known haplotype.

## 3. Previously proposed contig-density work (draft PR399)

Branch `p0/contig-density-short-contig-snv-20261123` HEAD
`b407be1575e8abd1d167cb8577d1ca5ff1ee3001` adds
`redundancy::single_substitution_apart(valid, shared) = shared * 2 >= valid &&
valid - shared <= K`, collapsing a one-substitution neighbour at **any**
length. Verified by `git merge-base --is-ancestor`: this commit is **not** in
the candidate. The candidate therefore does not carry the flagged hazard.

In the candidate's inherited selection rule a 310-base contig differing by one
substitution shares 249/280 = 88.9% of canonical windows (below the 95% rule)
and is retained, while a 900-base one shares 839/870 = 96.4% and is withheld
(with SNV evidence routed to the unphased audit). PR399 removes that length dependence and would also drop
the short, read-supported 15% minority haplotype from the ordinary FASTA. The
audit preserves unphased observations but does not restore a phased minority
contig or the original pair evidence. A new executable test
(`ranking_tests/minority_retention.rs`) proves the candidate retains a
310-base, one-substitution minority contig at about 85:15 read support.
**Recommendation: do not adopt PR399 as proposed.** Any density rule must
retain a contig with independent read-derived support and be validated on
HXB2-derived multitruth synthetic cases at 15% minority abundance before
consideration.

## 4. Downstream runtime risk from already completed frozen receipts

No new run was performed. Published candidate receipts are within
40 min / 4 GB: R042 12.3157 s / 369.6 MB, HLA-B control 219.9385 s / 501.4 MB,
HCV-unique control 125.4136 s / 515.1 MB, score gate >=90% of best available
rival. Earlier frozen read-only phase forensics (33 same-source pairs) found
native contig counts mean 6.367 (Ivanka) vs 1.567 (IVA) and that pairs with
more native contigs had downstream remap delta (IVA minus Ivanka) mean
-10.419 s, worst -44.052 s. Removing exact native copies reduces or leaves
unchanged the contig burden MiCall remaps, so the direction of runtime risk is
beneficial or neutral. It remains a hypothesis: strict all-r runtime Psi on
the full 198 and the 40 min/4 GB sampled maxima must be measured by the running
controller; old receipts do not prove kernel-enforced 4 GB isolation.

## 5. Validation of this review artifact

On branch `review/seed-novelty-bio-correctness-M7qXkbGD` at the review commit:

- `cargo fmt --all -- --check`: clean.
- `cargo test --all-targets`: 78 unit + 52 contract = 130 tests pass
  (candidate base was 71 + 51 = 122; eight new regression tests).
- `python3 benchmarks/reference_isolation.py`: PASS.
- Source-lint invariant: no Rust source file exceeds 50 nonblank noncomment
  lines; the new test directories stay below 10 direct entries.
- `cargo clippy --all-targets`: not completed; the host's Guix loader cannot
  load `libgcc_s.so.1` for the build script (exit 127). This is environmental,
  unrelated to these tests; no clippy claim is made.

## 6. Recommendation and unresolved risks

No demonstrated defect in the candidate's exact/RC suppression was found, so
no prospective patch or draft PR was opened and the running candidate is
recommended **unchanged**. Keep PR412 draft until the controller completes
full physical 198 >=90% floors and strict all-r score/runtime Psi, and until
the separate 464 multitruth phase-safety gate is run.

Unresolved: (a) standalone callers must independently preserve `--seeds`
contigs (contract change, now test-covered); (b) PR399-style near-dup pruning
must not be merged without a read-support guard; (c) numerical qualification
and full 40 min/4 GB maxima are not established by source-only work;
(d) P3 comparator failures still block any seven-way claim.
