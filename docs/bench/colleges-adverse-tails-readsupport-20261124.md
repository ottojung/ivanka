# P0 read-only diagnosis of adverse frozen quality tails (2026-11-24)

Owner: agent `tzOshp2CY4r5DruSWV4iVn-colleges`.
Host: `marceline-dev` (founder 2026-11-24 01:28Z keeps Ivanka work here; PX is
founder-owned). No host misrouting.
Repository: `https://github.com/ottojung/ivanka.git`, verified from the board
and AGENTS.md, cloned into agent-owned
`/workspace/ivanka-p0-colleges-tails-20261124`.
Branch: `colleges/p0-quality-tails-research`, based on the live candidate
`7dbdbaefb1155f634a760034287cc9d480099bf9` (draft PR412). The candidate,
controller, adapter, MiCall source/images, original 4,634 arms and PX were
**not** modified or rerun. No new clinical run, OCI build or score/reference
input to an assembler.

## Question

Independent audit PR433 (`a3170a4`, issue `gtJKIc1ivMPq1dvObJRgdt-combining`)
reported, on 108–112 attested candidate cases, negative score tails against
ABySS and SPAdes, negative low-r score against Haploflow/MEGAHIT and positive
runtime Ψ on all axes. This work asks whether those tails are genuine loss of
read-supported biological sequence, or instead duplicate suppression,
read-span/phase selection and unchanged downstream MiCall context.

## Method (reference-blind)

`benchmarks/colleges_tails_read_support.py` is a read-only tool that, for each
case in the frozen plan:

1. reads the original Ivanka native contigs from the immutable frozen arm
   (`phase-real198/artifacts/ivanka-physical-*/…/unstitched_contigs.fasta`);
2. reads the candidate native contigs and caller-supplied read-derived G2P
   seeds from the SHA-attested candidate scratch archive;
3. records which native rows were removed and whether each is a whole
   strand-canonical duplicate of a supplied seed;
4. records original/candidate/rival MAX consensuses and posthoc scores;
5. computes per-base **exact source-read support** for every distinct contig
   and MAX consensus using the *pinned original* MiCall implementation
   `micall/utils/exact_coverage.py` at `bench-ci-venv` with `--overlap-size
   70` and the SHA-verified original R1/R2 FASTQs.

Only original paired reads and assembler/G2P contigs enter the support
computation. No reference panel, truth, sample identity or benchmark score is
an input to support. Output uses pseudonymous SHA-256 case keys; no private
sample name is published. Evidence:
`docs/bench/colleges-adverse-tails-evidence-20261124.json` (20 cases, SHA256
below). Reproduce:

```
python3 benchmarks/colleges_tails_read_support.py \
  --case 9da1b6c7b481 --case bea55de8b5b9 \
  --out <own-dir>/tails.json
```

## Cases inspected

20 independent cases: nine with candidate score below original Ivanka
(`-9,-6,-6,-3,-2,-2,-2,-2,-1`), four further cases below a rival but not
below original Ivanka (including the sharpest ABySS/Haploflow, MEGAHIT and
SPAdes tails), four fully unchanged cases, three score gains, and the R042
canary. Case keys and all numbers are in the evidence JSON.

## Findings

1. **No biological sequence loss in any inspected case.** All removed native
   rows in all 20 cases are exact strand-canonical duplicates of contigs that
   are also supplied as read-derived G2P `--seeds` (20/20 cases, 2–4 rows
   each). No distinct native sequence was dropped, and no native set contains
   internal canonical duplicates. The change is row provenance (native copy
   removed, seed copy retained), not sequence content.

2. **Score loss generally accompanies *more* source-read support, not less.**
   Of the nine score-loss cases, six have a candidate MAX consensus with
   strictly higher exact-read support than the original MAX (e.g.
   `-9` case: original MAX 306 nt with 0.0 mean exact coverage → candidate
   MAX 318 nt with 10,770.1 and 49.9% support share; `-6` case: 0.0 → 62.95;
   another `-6`: 0.0 → 74.82; `-3`: 0.0 → 11,850.0). Two are identical
   (one still 0.0 for both arms) and one changes negligibly (7.4066 → 7.3824,
   -0.3%). In the sharpest SPAdes tail case the candidate MAX support rises
   1,438.9 → 2,544.1 while the panel score falls 1 point. These are panel/
   stitcher-context tails, not loss of read-supported sequence.

3. **The unchanged-score adverse cases have unchanged support.** For the
   ABySS/Haploflow `-15`, MEGAHIT `-18` and SPAdes `-10/-6` cases whose MAX
   did not change, candidate and original MAX support are numerically
   identical. Where a rival's MAX has marginally higher support (e.g. 5,253
   vs 5,134 in one SPAdes tail), the difference is ~2% and the rival row is
   a downstream-stitched consensus, not an Ivanka native contig.

4. **R042 is preserved and diversity is retained.** The candidate removes
   the exact-seed-duplicate 324 nt (mean exact coverage 184.38, 91.9% support
   share) and a weakly supported 306 nt copy (0.82, 0.39%), then promotes the
   read-supported 324 nt MAX (score 179 vs original 102, best rival 179).
   Distinct native minority contigs remain: 306 nt at 3.47% and 251 nt at
   4.25% support share. Across the cohort, distinct contigs at 12.4% and
   20.1% support share are retained by the candidate. Nothing resembling
   15%-abundance haplotype loss was observed.

5. **Mechanism is frozen MiCall context, not the assembler's read choice.**
   Original adapter concatenates native contigs then G2P `merged_contigs`
   (`micall/drivers/sample.py::run_denovo`), after which the unchanged
   referenceless stitcher and fixed-panel scoring choose the MAX. Removing a
   native row changes that context and can flip which identical-sequence row
   wins, which is why identical support can produce different panel scores.
   Ivanka writes exactly one FASTA and receives no panel or score, so a
   Rust-only change cannot target the panel delta without smuggling in
   reference/score information (forbidden by Intent 003 and AGENTS.md).

## Recommendation / falsifiable conclusion

**Do not open a score-driven assembly patch.** The adverse tails observed here
are not measurable deficits in source-read support, and a patch that chased
panel points would either be reference-informed cheating or an unfounded
change to deterministic context. Keep candidate PR412 and its controller
running unchanged; this is consistent with the independent biological review
(issue `LzYdEFCZGIyc0Ni1w9S0f3-municipal`, commit `d675fc8`) that found no
exact/RC suppression defect. PR399-style near-duplicate/SNV pruning remains
unsafe without a read-support guard and 15% multitruth validation.

A future candidate change would constitute a *genuine* quality regression only
if, on a source-witnessed case, it (a) drops a distinct read-supported contig,
or (b) lowers the final MAX exact-read support relative to the original arm,
after the same pinned support computation. This audit provides zero such
examples in 20 cases; it should be re-run when the frozen cohort completes.

Adversarial Rust tests added on this branch lock in the two invariants that
any future remedy must respect: weak/strong **exact or RC seed duplicates**
may be removed, while distinct near-duplicate, minority and recombinant
contigs must be retained (`src/assembler/run/seed_duplicates/tests_tails.rs`).

## Validation

`python3 benchmarks/colleges_tails_read_support.py` ran to completion for 20
cases: 20/20 attested frozen paths and paired FASTQs resolved, pinned
`exact_coverage` returned finite per-base support for every input sequence.
`cargo fmt --all -- --check` clean; `cargo test --all-targets` pass count
recorded in the terminal handoff; `python3 benchmarks/reference_isolation.py`
PASS. No threshold, clinical code, candidate, controller, MiCall source,
image, original arm or PX artifact was changed.

Evidence JSON SHA256 is recorded in the board handoff; no clinical/phase/
release claim is made.
