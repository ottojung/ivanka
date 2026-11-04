# Reference-free Q15 phase-audit read-cache performance experiment

This document is for an **opt-in research guard only**, based on draft
PR #157. Ordinary Ivanka, MiCall consensus, IVA reference images, the
private frozen 198 benchmark and acceptance PSI are not modified.

## Algorithm

Before: each selected contig performed its own pass over every original
R1, reverse R1, R2 and reverse R2 sequence, rebuilding exact 25-mer codes
and per-base quality-failure prefix counts. After: prepare 25-mer codes
and Q15 51-base-window flags only once per oriented original read, then
reuse them across all selected contigs. No pair/quality arrays are cloned
inside the per-contig scan. The compact flags occupy **one byte per
observation window**, not a platform-size integer per read base.

The resulting evidence is unchanged: exact 25+25 flanks at Q15,
an original pair remains a single vote, aligned mate placements must
be unique and inward-facing with plausible span, and unchanged
per-pair sequence-signature deduplication guards against treating
duplicated read records as independent molecules.

## Independently measured full-input native release A/B

Executed on marceline-dev, November 4, 2026, with the *same original
FASTQs*, a 16-contig cap, explicit experimental AUDIT=1 and **both
binaries built with cargo build --release --locked**. No sample
prefix/limiting max-pairs flag was set. Times below are full native
process elapsed, not only the phase-audit portion.

| Sample | Version | Elapsed seconds | Peak resident KB |
| --- | --- | ---: | ---: |
| S48: 86,144 original pairs | Original Q15 guard | 39.25 | 843,148 |
| S48 | First shared-preprocessing cache | 31.41 | 2,156,384 |
| S48 | Compact 51-base quality-window cache | **31.14** | **1,548,524** |
| S98: 26,496 original pairs | Original Q15 guard | 34.18 | 212,844 |
| S98 | First shared-preprocessing cache | 31.84 | 616,676 |
| S98 | Compact cache | **30.93** | **429,840** |

Compact vs baseline: S48 wall-time reduction approximately 20.7%
and S98 approximately 9.5%; memory remains higher than original:
1.84x for S48 and 2.02x for S98. Compact quality windows recovered
approximately 28% of the first cache's peak memory on S48 and 30%
on S98. Faster is not automatically better: at 10 concurrent
analyses, memory must be checked against the actual host and MiCall
co-resident memory use.

Both samples emitted **byte-identical FASTA** versus baseline at all
16 contigs. The exact file SHA256s are:

- S48: d1109143748774b95f6ad42fcd59a26a845a36343ba619954b91014614df5c97
- S98: 580e363225c26cf6bde47db201d71323645d2929cb853e9568164e82297ce4e3

Detailed private elapsed/RSS/FASTA logs and exact comparison outputs:
 /workspace/ivanka-lab/phase-guard-release-matched-20261104/

## Synthetic negative/positive equivalence

The actual compiled release executable produced FASTA exactly equal to
the previous Q15 guard for all three optional modes (audit-only,
ambiguous-N mask and destructive split), for all four fixtures:
seed-17 directly linked synthetic, seed-17 unlinked synthetic,
seed-23 1%-substitution linked synthetic and seed-23 1%-substitution
unlinked synthetic. Twelve output files were compared byte-for-byte.

The linked controls still flag the unsupported recombinant with 35
and 9 distinct original paired-sequence signatures respectively;
unlinked controls abstain. There is no new haplotype reconstruction,
physical molecule model or final MiCall phase contract.

**Do not merge the Q15 guard into production** on the strength of
these performance measurements. The phase screening model's insert
geometry, PCR duplicates, rare true haplotypes, false-positive costs,
downstream N-mask erasure by MiCall and full cohort acceptance remain
unresolved. This stacked experiment may be merged into the existing
draft guard only after independent review, not into main.
