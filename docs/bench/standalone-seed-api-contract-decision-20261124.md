# Standalone `--seeds` API contract: decision (2026-11-24)

Workfront: board issue `39kEMeIL7UMhiR04ZbWIsy-nest`, parent
`Fz2R6jPtA0dzrkMgVuxD0f-solomon`. Source-only, isolated draft branch; no
MiCall source, frozen image, adapter byte, controller, 4,634 historical arm,
clinical run or PR412/434 source was changed. Host: marceline-dev.

## 1. Sources actually read

| Source | Commit | What it establishes |
| --- | --- | --- |
| `main` | `b6924ea0` | Authoritative CLI contract and intents; no exact-seed suppression. |
| PR402 | `e47f841f` | Adds opt-in `--exclude-supplied-seed-duplicates`; requires adapter overlay, therefore ineligible under the frozen-adapter policy. |
| PR412 | `7dbdbaef` | Makes suppression the **default** for `--seeds` when reads are admitted; this is the candidate under review. |
| PR434 | `d675fc80` | Test-only review; records the standalone empty-output observation but proposes no fix. |

Binding intent text read in full: `AGENTS.md`, `docs/intents/002-default-invocation-parity.md`,
`docs/intents/004-dominant-sequence.md`, `README.md` (`--seeds` sections),
`benchmarks/patch_micall_for_ivanka.py`, `benchmarks/test_verify_ivanka_binding.py`,
`benchmarks/test_reference_isolation.py`, and the candidate source
`src/assembler/run/{mod,finish,write_results,prepare,seeds}.rs` and
`src/assembler/run/seed_duplicates.rs`.

## 2. Reproduced observation (source-attested, no clinical input)

On PR412 head, with the ordinary `tests/fixtures/a` read pair, a seed FASTA
containing the dominant native contig (471 nt from `a_expected.fa`) and
`--max-contigs 1`:

```
IVANKA_NATIVE_SUPPLIED_SEED_DUPLICATES removed=1 remaining=0
Ivanka wrote 0 contigs in 0.1s
```

`--output` is a valid 0-byte FASTA and the process exits 0. With
`--max-pairs 0` the same seed is emitted unchanged. This matches PR434 §1 and
the issue statement. No reference, truth panel, score or sample name was used;
the decision input is only the caller's FASTA plus original read-support.

## 3. What the documented contract already requires

1. **Intent 002, acceptance #2:** "A direct invocation with the **same reads
   and seed file** must produce byte-identical FASTA; a valid zero-contig
   assembly still exits successfully." The MiCall boundary and a standalone
   boundary are required to be indistinguishable, byte for byte, at the
   assembler CLI.
2. **`README.md`:** `--seeds` supplies **read-derived contigs as assembly
   starting points**; Ivanka *extends* them with the sample reads and reserves
   part of the output budget for them. It does not define `--seeds` as an
   output-passthrough or echo channel. The caller owns seed provenance.
3. **Intent 004:** "The Rust component may emit empty or partial contigs. We
   introduce **no extra nonquantitative completeness, contig-count,
   redundancy, or all-haplotypes intent**." Empty output is explicitly legal;
   adding a non-empty / contig-count / anti-redundancy *requirement* is
   explicitly out of scope.
4. **Frozen adapter:** the reviewed adapter passes only `--reads1`,
   `--reads2`, `--output` and (when present) same-sample `--seeds`, with
   `env={}`. `test_verify_ivanka_binding.py` rejects extra flags and any
   argument mutation; `test_reference_isolation.py` rejects an unreviewed
   adapter that forwards seeds. MiCall injects the G2P contigs separately
   downstream, so the assembler's job is to avoid re-emitting exact copies.

## 4. Rigorous incompatibility (no automatic read-derived fix exists)

Let `I = (reads, seeds, argv, env={})` be everything Ivanka can observe when
it runs. The frozen-adapter invocation and any standalone seed-assisted
invocation that satisfies Intent 002 #2 have **the same `I`**. The difference
between them — whether G2P contigs are separately injected downstream — occurs
*after Ivanka exits* and is not an input to Ivanka. Therefore:

* Any function `f(I)` that Ivanka computes (read support, k-mer breadth,
  canonical sequence equality, quality diagnostics, seed length, read
  admission) returns the same value for both callers.
* The two desired outputs are `f(I) = emit exact seed` (standalone utility)
  and `f(I) = suppress exact seed` (no redundant native output under the
  adapter). No deterministic `f(I)` can satisfy both. Detecting the caller
  path/name, reference or downstream injection would require information
  outside `I`, which is forbidden and would also break byte-identical parity.

Consequences for the mechanism families named in the issue:

| Mechanism | Verdict |
| --- | --- |
| Caller path/name or reference detection, env tuning, adapter flag | Forbidden (issue constraints, Intents 002/010/011, binding guard rejects mutated argv). |
| "Non-empty fallback": keep the dominant contig if suppression would empty the FASTA | Adds a nonquantitative completeness/contig-count gate forbidden by Intent 004, and reintroduces redundant native output under the adapter in exactly the degenerate case it targets. |
| Always echo supplied seeds into `--output` | Reintroduces redundant native output under the frozen adapter (the defect PR402/412 exist to remove); also contradicts the "assembly starting point, not passthrough" meaning of `--seeds`. |
| Emit only a read-derived *extension* beyond the seed | When the native contig equals the seed exactly there is no extension to emit; the case is unaltered. |
| Automatic caller-discriminating rule | Information-theoretically impossible under Intent 002 byte parity, as proved above. |

## 5. Decision

**No source behavior change is warranted; the observed empty FASTA is a
documented, valid contract outcome, not a defect.** PR434's "standalone caller
must preserve its own seeds" is the correct consequence of the contract:
`--seeds` is an assembly *hint*, Ivanka emits only native assembly evidence,
and the caller — not Ivanka — retains the seeds it supplied. This is exactly
what Intent 002 #2 and Intent 004 permit, and what the frozen adapter already
does downstream. Suppressing exact/RC-native copies while reads are admitted
is a read-derived, reference-blind rule; it is not caller detection and does
not modify MiCall.

The genuine gap is **underspecification of a public API**, not incorrect
behavior. The honest resolution is explicit contract + versioning, not a
hidden heuristic:

1. **Clarify the documented contract** (this decision record, plus the contract
   tests added alongside it): a successful Ivanka run with `--seeds` is allowed
   to emit `0` contigs; supplied seeds are assembly starting points and are
   never echoed into `--output`; callers that require those contigs must retain
   them. A direct invocation with the same reads and seed file is byte-identical
   to the adapter invocation.
2. **Version, do not auto-detect.** If a future standalone API needs seed echo,
   it must be an *explicit, caller-selected, versioned* CLI mode (for example a
   `--seeds-output` / `seeds-v2` contract) that the frozen adapter never passes.
   It requires its own contract amendment and fresh physical/synthetic
   qualification; it is NOT a P0 patch to the benchmarked binary and is out of
   scope here.
3. **Keep PR412/PR434 unchanged** until the controller finishes the full
   198-sample all-r score/runtime Ψ gates and the 464-multitruth synthetic
   phase. This review changes no production behavior and claims no numerical
   qualification.

## 6. Artifact and validation

* `tests/contract/seeds/contract.rs` (new): locks byte-identical direct/adapter
  invocation, the valid-empty-FASTA outcome for the dominant exact seed with
  admitted reads, and the read-admission-only dependence (the same seed is
  emitted with `--max-pairs 0`). Registered in `tests/contract/seeds/mod.rs`.
* `cargo fmt --all -- --check`, `cargo test --all-targets`,
  `python3 benchmarks/reference_isolation.py` — results recorded in the
  terminal handoff. No source file changed, so the candidate binary is
  preserved byte-for-byte.
