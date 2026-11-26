# P1 PCR jackpot: bounded native reconstruction of disconnected fragments (source-only, 2026-11-26)

## Provenance / coordination

- Base (exact): `e97eebb9c6ffed655fad0e94196125e7acc9bb17`, branch
  `p1/pcr-jackpot-5966811-pr464-20261125` (the previously pushed P1 combined
  candidate: `5966811` + PR464 + PR468, parent `12d8c72f`).
- This branch: `p1/pcr-native-disconnected-fragments-20261126`, one commit on
  that exact base. No rewrite, no merge, no PR, no promotion.
- Sibling combined candidate `science/combined-pr506-pr516-20261126`
  (`950fe331`) is read-backed-ranking work; it is not duplicated or modified
  here. No frozen source, MiCall, image, controller, threshold or cohort file
  was written.

## Why high-copy disconnected fragments were missing (reference-blind)

Operator posthoc evidence (`ivanka-storage-recovery-20261126/`): on 14
relative-floor misses the unstitched candidate recovers a median 40.2% of the
truth canonical-31-mers observed in reads versus 99.87% for the best frozen
rival; the rival-only observed truth 31-mers number 720-2032, each seen in at
least three distinct read strings (not independent molecules).

Native path inspection of `pcr_jackpot-s001` (`12d8c72` evidence) shows a
caller-supplied seed, 50 seed candidates of which 33 produce no extension,
`IVANKA_QUALITY no_extension_support=33`, and six final contigs. The jackpot
generator draws reads from 13 fixed 270-base fragments of one haplotype; seed
extension cannot reach disjoint fragments. The existing native-fragment
retention adds one 150-base read per free contig slot. Two consequences:
one 270-base fragment consumes two slots, and a single-read candidate is
discarded wholly if even one of its 31-mers is already represented.

Read-only pair-support analysis of that case: 26 high-support read identities
(about 67-96 distinct observed pairs each), 11 already represented, 15 novel,
and only 10 free slots. The loss is a native contig-recovery gap, not a MiCall
stitcher artifact and not absolute-genome unidentifiability.

## Source-only fix

`src/assembler/run/native_fragments/`:
- `rank/fragments.rs`: merge a read with the mate of its own observed pair only
  when an exact suffix/prefix overlap of at least 16 bases exists (both strand
  orientations considered). The merged sequence contains only exact observed
  bases; no gaps are filled, no bases invented, no mates from different pairs
  joined. With no exact overlap the original read is unchanged.
- `rank/mates.rs`: one borrowed (read, mate) pair per canonical read identity,
  deduplicated by distinct observed pair so repeated copies cannot supply
  extra mates.
- `support.rs`: emit the merged fragment first and keep the original single
  read as a fallback candidate. The fallback prevents a longer fragment from
  being lost entirely when one represented 31-mer vetoes it.
- All prior bounds are unchanged: minimum 15 distinct observed pairs, at least
  1% of all distinct library pairs, canonical 31-mer eligibility, skip of
  represented regions, and the caller's `--max-contigs` cap. The default
  unseeded CLI path is untouched (`retain` remains gated on supplied seeds),
  so frozen default-output contract tests remain byte-identical. No
  reference, truth, family label or rival data reaches the assembler.

## Validation (exact branch)

- `cargo test --locked --all-targets`: 98 unit + 51 contract, 0 failed.
  Five new compact read-derived fixtures: exact mate overlap reconstruction,
  unrelated mate not merged, short overlap not merged, reverse-complement mate
  merged, retain uses the reconstructed fragment. Existing boundary,
  identity, share-guard, contig-budget and repeated-observation controls pass.
- `cargo fmt --all -- --check`: clean. Structural lint 0 violations.
- `python3 benchmarks/reference_isolation.py`: PASS.
- `cargo clippy --locked --bin ivanka` with CI correctness/suspicious/perf/
  complexity denials: rc=0; only style warnings, including two moved
  pre-existing `chunks_exact(4)` lines in `rank/` (same code as the base
  `pair_support.rs`). No correctness/suspicious/perf/complexity denial.
- Release build (`--locked`, `CARGO_INCREMENTAL=0`, `CARGO_PROFILE_DEV_DEBUG=0`):
  prefix SHA256 `28273c6f916dcbc8c92e82fcbac1b84d9708e2e66328b3265533059c5d8609bb`;
  fixed SHA256 `99722c06a20acdc9d27838f39babdd67710843da6a1a3144c3dbadbedf245c71`.

Targeted native comparison (seeded, reads only in the assembler; exact
canonical-31-mer truth recovery computed posthoc after both FASTAs were read):

| case | prefix | fixed | truth31 in reads |
|---|---|---|---|
| pcr_jackpot-s000 | 0.774 | 0.988 | 2650 |
| pcr_jackpot-s001 | 0.771 | 0.987 | 2781 |
| pcr_jackpot-s002 | 0.614 | 0.730 | 3106 |
| pcr_jackpot-s003 | 0.613 | 0.768 | 3098 |
| pcr_jackpot-s008 | 0.764 | 0.993 | 2623 |
| pcr_jackpot-s014 | 0.952 | 0.988 | 2498 |

Negative controls: `clonal-s000`, `minority_30pct-s000`,
`complex_mixture-s000`, `coverage_hole-s000`, `equal_strains-s000` native
FASTAs are byte-identical to the prefix binary under the same supplied seeds.

## Boundaries

No integrated MiCall pilot, full 464-cohort replay, OCI build, frozen write,
physical comparison, threshold change or qualification. `pcr_jackpot-s002`
remains at 0.730 of observed truth 31-mers because the seeded selection uses
11 of 16 slots before native retention; the cap is caller-controlled and not
changed here. These are source tests and bounded native diagnostics only; no
gate pass or clinical claim is supported.
