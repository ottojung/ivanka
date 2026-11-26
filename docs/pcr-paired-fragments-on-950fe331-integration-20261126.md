# Prospective integration: PCR paired-fragment fix on exact 950fe331 combined candidate

**Scope: separate candidate branch only.** No replacement of the existing
PR531 pilot pin (`science/p1-bounded-pilot-950fe331-on-pr527-20261126`), no
change to `science/combined-pr506-pr516-20261126`, no merge, PR, deployment,
OCI build, live PX, frozen write, threshold or qualification claim.

## Exact provenance

- Integration base: `950fe331dfcd857011bfd63f9eeca92462708545`, the exact
  combined P1 candidate (`PR506` + `PR516` on `PR490`/`PR498`).
- Ported onto that base, in order:
  - `28dd24e4` / `05cf7bd8` / `2ca630fb` — exact cherry-picks of PR468 native
    fragment retention (`ea3e1335`, `7b872123`, `9c024806`).
  - `7a445488` — exact cherry-pick of reviewed paired-fragment fix `01692977`
    (exact mate-overlap reconstruction plus single-read fallback, compact
    read-derived fixtures and native-path evidence doc).
- **PR464 (`d8dee798`, read-backed distinct-pair scoring) was deliberately not
  ported**: `950fe331` has its own diverged `read_backed/ranking` chain
  (`fda868a6`, `81c824cd`, `15785f5b`, balanced/junction/spans). Porting the
  `raw_pairs` tie-break there would mix two independent ranking changes and is
  not required by the paired-fragment mechanism. This candidate adds only the
  native-fragment path; no read-backed ranking code was modified.

## Mechanism and guardrails (unchanged from reviewed fix)

High-copy jackpot reads come from 13 disjoint 270-base fragments; seed
extension cannot reach them. The native retention path now merges a read with
the mate of its **own observed pair** on an exact >=16-base suffix/prefix
overlap, emitting only exact observed bases (no invented bases, no cross-pair
joins), and keeps the single read as fallback. Bounds unchanged: >=15 distinct
observed pairs, >=1% of distinct library pairs, canonical 31-mer eligibility,
represented-region skip and the caller's `--max-contigs` cap. No truth,
reference, family label or rival data reaches the assembler; diagnostics are
posthoc only. The default unseeded CLI path is untouched.

## Validation

- `cargo test --locked --all-targets`: **117 unit + 51 contract, 0 failed**
  (includes the five new paired-fragment fixtures and the 950fe331
  coverage-hole/balanced tests). `cargo fmt --check` clean; structural lint 0;
  reference isolation PASS.
- Release binaries built from the exact heads with
  `CARGO_TARGET_DIR=$(antonina agent cache --id "$ANTONINA_AGENT_ID" --init)`,
  `CARGO_INCREMENTAL=0`, `CARGO_PROFILE_DEV_DEBUG=0`; saved outside cache:
  - old combined `950fe331`: SHA256 `8569290db7aada4b915feda4648cfd3bcb92a48288cea7918ce36cc9439c3786`
  - new candidate source `7a445488`: SHA256 `ec5eb83546fb4fb212514a3ff54a8fea39e5b016e06ac70f46e2e22a1a931563`
- Bounded seeded native differential: **16/16 pcr_jackpot + 16/16
  equal_strains + 16/16 clonal = 96/96 invocations, all exit 0**, using only
  the original sample-derived `seeds.fasta` from the P1 root and the FASTQ
  pairs. Records, per-case wall time, per-child peak RSS and FASTAs are in
  `ivanka-pcr-integration-950fe331-20261126/native_report.json` and `runs/`.

| family / arm | mean seconds | max seconds | mean peak RSS (KB) | mean contigs | total FASTA bytes |
|---|---|---|---|---|---|
| jackpot old | 0.161 | 0.222 | 19,131 | 6.94 | 24,025 |
| jackpot new | 0.166 | 0.205 | 19,795 | 14.31 | 51,742 |
| equal_strains old | 1.608 | 2.236 | 23,000 | 3.50 | 605,443 |
| equal_strains new | 1.603 | 2.473 | 24,817 | 3.50 | 605,443 |
| clonal old | 1.922 | 2.582 | 23,518 | 1.06 | 166,839 |
| clonal new | 2.053 | 2.699 | 25,384 | 1.06 | 166,839 |

Control byte-identity: **16/16 equal_strains and 16/16 clonal native FASTAs
byte-identical** — no extra contig burden in those families. RSS rises about
1.8 MB in controls and 0.7 MB in jackpot, attributable to the loaded mate
index; no per-case deadline was approached. Jackpot contigs/bases rise because
that is the target family; the cap remains 16.

Posthoc exact canonical-31-mer truth recovery (truth opened only after both
FASTAs for a case were read; mean over 16 jackpot cases): **0.4263 old →
0.9244 new; 16 improved, 0 regressed**. Per-case values and the diagnostic
script are in `ivanka-pcr-integration-950fe331-20261126/posthoc_truth31.json`
and `posthoc_truth31.py`. Cases s002 (0.730), s003 (0.768) and s012 (0.820)
remain below the others because the seeded selection already consumes slots
before retention; the caller-controlled cap was not changed.

## Review boundary

This is source integration plus bounded native diagnostics only. No MiCall
arm, full cohort replay, physical parity, OCI/image, live PX, frozen write,
gate pass or clinical/qualification claim. Disk stayed above the 32 GiB floor
for the bounded runs (35.1 GiB free at build; rechecked after). A credentialed
reviewer should verify the exact head, the PR464 exclusion, control identity
and the posthoc-only truth boundary before any further coordination.
