# Cap sensitivity 16/24/32 — source/aggregate-only diagnostic evidence

**Retrospective truth-based evaluation, NOT qualification.** No gate, merge,
promotion, deployment, integrated MiCall run, OCI build, live PX, frozen write,
adapter/default change or cap change. The user default remains `--max-contigs
16` and the CLI maximum 1000; 24/32 were invocation-only values on a preserved
binary. No FASTQ, hidden truth, rival output, private path or large file is in
this repository — only text scripts and aggregate hashes/counts.

## Provenance

- Candidate head this branch is based on:
  `19386765b40a4d57dce15c0984a731486b69121e` on
  `science/pcr-paired-fragments-on-950fe331-20261126` (reviewed by g8Kq at
  exact head, SOURCE CORRECTNESS ONLY). This branch changes **only** this
  `docs/diagnostics/` directory.
- Binary: source head `7a445488`, SHA256
  `ec5eb83546fb4fb212514a3ff54a8fea39e5b016e06ac70f46e2e22a1a931563`.
  It was preserved outside any build cache; no rebuild was needed.
- Exact binary SHA, source head, caps, predeclared case IDs, per-case R1/R2/
  seed SHA256s, per-case per-cap output SHA256s and the three script SHA256s
  are in `pinned_receipt.json`. `aggregate.json` contains all aggregate and
  per-case counts (contigs, sequence bases, FASTA bytes, runtime, peak RSS,
  read support, native fragments added and their pair support, truth31 counts
  and hashes). No private paths appear in either file.

## Reproduction (operator supplies roots; no truth in runner)

```
export IVANKA_BINARY=/path/to/preserved/binary        # SHA verified vs receipt
export IVANKA_CASES_ROOT=/path/to/case/root            # <case>/reads/R{1,2}.fastq.gz
export IVANKA_OUTPUT_DIR=/path/to/disposable/output
python3 run_cap_sensitivity.py
export IVANKA_TRUTH_ROOT=/path/to/hidden-truth/root    # <case>/hidden-truth/haplotypes.fasta
python3 posthoc_cap.py
python3 verify_independent.py
```

`run_cap_sensitivity.py` verifies each input hash against the receipt before
invocation, uses only the original sample-derived `<case>/assembly_*/seeds.fasta`,
sets `env PATH=/usr/bin:/bin`, applies a 30 s per-case deadline (SIGKILL) and a
4 GB MemAvailable stop guard, and verifies each output hash after invocation.
No per-case tuning and no cap changes. `posthoc_cap.py` reads and hash-verifies
all three cap FASTAs for a case **before** opening any truth FASTA; truth is
never given to the assembler. `verify_independent.py` re-checks the aggregate
without opening truth.

## Aggregate (72/72 invocations, all exit 0, no deadline/low-memory stop)

| family | cap | n | mean contigs | mean sequence B | mean s | max s | mean peak RSS KB | mean read support | mean truth31 |
|---|---|---|---|---|---|---|---|---|---|
| pcr_jackpot | 16 | 16 | 14.31 | 3,164 | 0.161 | 0.243 | 19,949 | 1.0000 | 0.9244 |
| pcr_jackpot | 24 | 16 | 15.69 | 3,484 | 0.166 | 0.243 | 19,891 | 1.0000 | 0.9854 |
| pcr_jackpot | 32 | 16 | 15.69 | 3,484 | 0.163 | 0.243 | 19,918 | 1.0000 | 0.9854 |
| equal_strains | 16/24/32 | 4 | 4.00 | 42,606 | 1.169/1.196/1.276 | – | ~25k | 1.0000 | – |
| clonal | 16/24/32 | 4 | 1.00 | 9,685 | 1.579/1.592/1.590 | – | ~25k | 1.0000 | – |

- cap 24 vs 16: **7 jackpot cases improved, 0 regressed** (mean +180
  truth31); cap 32 adds nothing further. All 8 predeclared control cases have
  **byte-identical output hashes across all three caps**.
- Independent verifier result: `verify_digest 49c019ff75ef4981…`; all ten
  checks PASS (`72_invocations`, `all_exit_zero`, `caps_16_24_32`,
  `default_and_max_unchanged`, `controls_identical_8/8`, `no_regressions`,
  `improved_at_24`, `improved_at_32`, `read_support_all_one`,
  `receipt_outputs_match_aggregate`).
- Remaining low cases at cap 16: s002 0.730, s003 0.768, s012 0.820; at cap 24
  the minimum jackpot truth31 fraction is 0.9517. These are caller-budget
  effects, not a reason to change the default here.

## Review coordination and boundary

g8Kq reviewed the candidate source at exact head `19386765` with a SOURCE
CORRECTNESS-ONLY GO; this artifact asks for independent review of the preserved
aggregate only, not a new source verdict. No integrated run until guarded
admission. No qualification, gate-pass or clinical claim is made; the
truth-based numbers are retrospective diagnostics computed after outputs were
sealed.
