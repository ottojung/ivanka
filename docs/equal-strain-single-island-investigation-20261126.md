# Compact investigation: remaining equal-strain / PCR floor failures (source-only)

**Separate branch:** `science/equal-strains-balanced-island-20261126`, created
from the exact current candidate head
`19386765b40a4d57dce15c0984a731486b69121e` on
`science/pcr-paired-fragments-on-950fe331-20261126`. The previous branch and its
PR531-adjacent pin are untouched. No merge, PR, promotion, frozen write, OCI
build, live PX or full benchmark.

## Current exact candidate (for the record)

- Branch `science/pcr-paired-fragment-in-950fe331-20261126`, head `19386765…`.
- Native differential (old exact `950fe331` vs new candidate source `7a445488`),
  96/96 seeded invocations, all exit 0:
  - pcr_jackpot: contigs 6.94 → 14.31, bytes 24,025 → 51,742, mean 0.161 s →
    0.166 s, mean peak RSS 19,131 KB → 19,795 KB.
  - equal_strains: 3.50 → 3.50 contigs, 605,443 → 605,443 bytes, 16/16
    byte-identical, mean RSS 23,000 → 24,817 KB, mean 1.608 s → 1.603 s.
  - clonal: 1.06 → 1.06 contigs, 166,839 → 166,839 bytes, 16/16
    byte-identical, mean RSS 23,518 → 25,384 KB, mean 1.922 s → 2.053 s.
  - Posthoc truth31 (16 jackpot cases): mean 0.4263 → 0.9244, 16 improved,
    0 regressed. Candidate input identities and all per-case records:
    `/workspace/ivanka-pcr-integration-950fe331-20261126/native_report.json`,
    `posthoc_truth31.json`, `runs/`, `binaries/`.

## Equal-strain mechanism inspected

The read-backed balanced branch (`fda868a6`/`PR516`) admits a second
co-abundant haplotype only when it has at least **two** private supported runs
of >=150 canonical 31-mers, private fraction 10-60%, and depth 80-105% of the
primary. A legitimate co-abundant recombinant can differ in **one** internal
region, which the two-island rule rejects as if it were a whole-genome
duplicate. This is reference-blind: only read-derived depth and selected
contig 31-mers are consulted.

## Source idea implemented on this branch

- `balanced/evidence.rs` now also returns the window bounds of the longest
  supported private run.
- `balanced/mod.rs` accepts `islands >= 2` **or** one internal run of at least
  `2 * MIN_RUN` windows. "Internal" requires the run to start at least K bases
  into the contig and finish at least 2K bases before its end, so terminal
  extension tails are still rejected. Private-size, depth, pair-support and
  whole-duplicate guards are unchanged.
- Compact read-derived fixtures (`balanced/tests_single_island.rs`): one long
  internal island accepted; terminal tail, whole duplicate, minority depth and
  deeper superposition rejected. No truth/reference in the fixture logic.

## Validation (registered cache)

`CARGO_TARGET_DIR=$(antonina agent cache --id "$ANTONINA_AGENT_ID" --init)`,
`CARGO_INCREMENTAL=0`, `CARGO_PROFILE_DEV_DEBUG=0`.

- `cargo test --locked --all-targets`: **121 unit + 51 contract, 0 failed**
  (117+51 on the parent plus four new compact fixtures).
- Release binaries saved outside cache: parent candidate
  `ec5eb835…`, this idea `f65a8ce3…`.
- Compact native check (3 cases only, original sample-derived seed files):
  `equal_strains-s008`, `pcr_jackpot-s002`, `clonal-s000` — all exit 0 and
  **native FASTAs byte-identical** to the parent candidate. Note the equal-
  strain and clonal seed files in the P1 root are empty (SHA256 `e3b0c442…`),
  so those two controls are effectively unseeded; jackpot seeds are non-empty.
  No measured floor improvement on those cases; the fixture change is a
  generalized candidate only, not an accepted fix. RSS within ~100 KB,
  runtime not worse.

## PCR remaining-floor finding (blocker, no code change)

Posthoc fractions after the paired-fragment fix: s002 0.730, s003 0.768,
s012 0.820. These cases are **slot-limited**, not mechanism-limited: seeded
selection already occupies 11 of the caller-controlled 16 contig slots before
native retention, leaving 4-5 slots for 13 disjoint fragments. Freeing slots
would require dropping read-supported contigs or changing the caller's
`--max-contigs`; the latter is outside this source branch and the former risks
exactly the regressions the controls protect. No artificial duplication was
added. Owner/operator decision is required before touching that boundary.

## Boundaries

No MiCall arm, full cohort, OCI, frozen write, live PX, threshold change,
qualification or clinical claim. Disk stayed above the 32 GiB floor; the
registered build cache was used for both builds. This branch is for review of
the generalized single-island rule and the PCR slot-cap finding only.
