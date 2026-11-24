# Default `--seeds` behavior in the candidate (2026-11-24)

Consolidates the source-only contract decision from board issue
`39kEMeIL7UMhiR04ZbWIsy-nest`, branch
`seedcontract/standalone-seed-api-YJmFkQS99DmTsqd8341Zq3-20261124`, commit
`6eee7029f02fb1b1d6e994b54f7ccc3e5ec94076`, with the binding CLI contract in
Intents 002/004 and the current candidate source. This is documentation only:
no source behavior, CLI mode, MiCall code or frozen artifact changes here.

## Sources actually read

| Source | Commit | What it establishes |
| --- | --- | --- |
| `main` | `b6924ea0` | Authoritative CLI contract and intents; no exact-seed suppression. |
| PR402 | `e47f841f` | Adds opt-in `--exclude-supplied-seed-duplicates`; requires an adapter overlay, ineligible under the frozen-adapter policy. |
| PR412 | `7dbdbaefb1155f634a760034287cc9d480099bf9` | Makes exact/RC seed-copy suppression the default when reads are admitted; this is the candidate. |
| PR434 | `d675fc80712eb622178b41d2aae1de5444160912` | Test-only review recording the standalone observation; proposes no fix. |

Binding text: `AGENTS.md`, `docs/intents/002-default-invocation-parity.md`,
`docs/intents/004-dominant-sequence.md`, `README.md` (`--seeds` sections), the
frozen adapter and its binding guards, `benchmarks/reference_isolation.py`, and
candidate source `src/assembler/run/{mod,prepare,write_results,seed_duplicates}.rs`.

## Precise default behavior of the candidate

- When `--seeds` is supplied **and reads are admitted**, the assembler's native
  output may omit contigs that are **whole exact or reverse-complement copies**
  of a supplied seed. This is a read-derived, reference-blind duplicate rule in
  `src/assembler/run/write_results.rs` and `src/assembler/run/seed_duplicates.rs`;
  it is not a caller, path or reference check.
- With **zero read pairs loaded** (for example `--max-pairs 0`), supplied seeds
  **can be preserved** in the emitted FASTA. The suppression branch is skipped
  when no reads are available.
- The **caller retains its own seed input** in every case: Ivanka does not write
  to or delete the supplied FASTA. Under the frozen adapter the caller injects
  its read-derived G2P contigs separately downstream; that injection is not
  visible to Ivanka.
- A run that emits a **valid empty FASTA exits 0**. Suppressed output is not an
  error, and this review adds no completeness, non-empty-output, contig-count
  or redundancy gate (Intent 004).
- A direct invocation with the same reads and seed file is byte-identical to the
  adapter invocation (Intent 002 acceptance #2); the empty child environment and
  argument contract are unchanged.

## Reproduced observation

On the candidate with an ordinary read pair and a seed FASTA holding the
dominant native contig, the duplicate diagnostic reported
`IVANKA_NATIVE_SUPPLIED_SEED_DUPLICATES removed=1 remaining=0`, the FASTA was
empty and the process exited 0. With `--max-pairs 0` the same seed was emitted.
No reference, truth panel, score or sample identity entered this observation.

## Why no automatic fix is in scope

The frozen adapter and any byte-identical standalone invocation are
indistinguishable at the CLI: reads, seed file, argv and the empty environment
are all Ivanka can observe. Whether the caller re-injects seeds downstream
happens after Ivanka exits and is not an input. Any deterministic function of
those inputs must therefore return the same output for both callers, so
"always echo seeds" and "always suppress exact copies" cannot both hold.
Caller detection, environment tuning and extra adapter flags are forbidden by
Intents 002/010/011 and the binding guards; a non-empty fallback would add a
completeness/contig-count gate forbidden by Intent 004.

## Decision

No source behavior change, no new CLI mode and no caller detection are
introduced. The underspecified public contract is the gap, and it is clarified
above rather than hidden in a heuristic. A future standalone API that needs
seed echo would require an explicit, versioned, caller-selected contract with
fresh P0 qualification; it is not part of this review. PR412 and its controller
remain unchanged pending the full 198-sample all-r score/runtime Ψ and 464-case
gates. PR434 stays a draft test/documentation stack. No numerical or clinical
qualification is claimed.

## Tests

`tests/contract/seeds/default_behavior.rs` locks repeated direct-invocation
byte parity and caller seed-input retention together with a valid empty FASTA.
`tests/contract/seeds/standalone.rs` (already in PR434) locks suppression with
admitted reads and preservation with zero read pairs.
