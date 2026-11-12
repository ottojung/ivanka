# Expanded synthetic benchmark: initial 400-case retrospective

**Evidence status: exploratory only — the seven-way gate has NOT passed.**
This report preserves an initial full 400-case run and an independent
biologically correct rescoring of all retained outputs. The old runner
included hidden-truth evaluation in measured durations, so its times
are invalid as benchmark tool runtimes. Multiple competitor runs genuinely
failed. No result here establishes all-exponent Ψ acceptance, nor does it
replace the untouched original physical 198-sample gate.

## Reproducible source evidence

- Cohort: 25 synthetic mechanisms × 16 deterministically generated seeds,
  each with original paired FASTQ and separate withheld truth.
- Frozen cohort `cohort.json` SHA-256:
  `dbcd7a1328e3e84c1a82d1fed7677fcbcd5e02a9a4efe230be79bc9efb372491`.
- Original 400 × 7 per-tool output and execution records:
  `/workspace/ivanka-expanded-podman-full400-20261112/results.jsonl`
  on `marceline-dev`.
- Independent strand-corrected rescoring (without changing the original
  run records), SHA-256:
  `4cbd51cd9d7848ff6282f90418f854ec14f629a92fd1fe5fba1f8311a5100994`;
  file `orientation-corrected-diagnostics.jsonl` in the same directory.
- Each candidate received only the original paired reads and its output
  mount. Scoring truth remained outside the assembler containers.
- Evaluator: global dominant-haplotype alignment, matching +1,
  mismatch −1, gap-open −2, gap-extension −1, normalized by truth
  length and clipped to [0,1]; **either reverse-complement orientation**
  is equivalent. Re-evaluation used the same frozen source FASTAs.

## What the first experiment shows

| Assembler | Completed executable outputs | Mean global truth score |
| --- | ---: | ---: |
| Ivanka alpha.3 | 400/400 | 0.343 |
| IVA | 337/400 | 0.498 |
| Haploflow | 394/400 | 0.770 |
| MEGAHIT | 400/400 | 0.803 |
| ABySS | 313/400 | 0.570 |
| SPAdes | 400/400 | 0.842 |
| Velvet | 400/400 | 0.707 |

For these descriptive means, failed outputs contribute zero *only as an
explicit diagnostic convention*. **Those failures are not successes and
must never be used to satisfy Ψ or to claim that Ivanka beat a competitor.**
There were 63 failed IVA runs, 87 failed ABySS runs, and six failed
Haploflow runs. Failure modes include genuine nonzero execution,
and some tool profiles exiting without their expected contig file.
These outcomes require individually audited resolution or a documented
valid empty-assembly contract; no hidden substitutions.

The original Ivanka alpha.3 scored below 90% of the *best successful
competitor* in **349/400** cases after correction for DNA orientation.
Full qualification would additionally require **zero failed tool runs**
and strict per-competitor signed-power Ψ(r)>0 for all real r≥0, separately
on real and synthetic cohorts. The failure count is therefore not a
formal seven-way gate verdict; the run is already disqualified.

## Mechanism-stratified findings

| Synthetic mechanism | Ivanka mean | Best available mean | Below 90% floor (of 16) |
| --- | ---: | ---: | ---: |
| Clonal | 0.385 | 0.997 | 16 |
| IID base errors | 0.375 | 0.996 | 16 |
| Quality decay | 0.597 | 0.997 | 16 |
| Cycle-localized errors | 0.339 | 0.994 | 16 |
| Homopolymer slippage | 0.385 | 0.994 | 16 |
| Systematic recurring errors | 0.365 | 0.996 | 16 |
| GC-dependent dropout | 0.368 | 0.992 | 16 |
| Amplicon hotspots | 0.000 | 0.136 | 8 |
| Hard coverage gap | 0.000 | 0.000 | 0 |
| Low depth | 0.358 | 0.986 | 16 |
| Ultra-deep | 0.390 | 0.999 | 16 |
| PCR jackpot | 0.000 | 0.000 | 0 |
| Mate quality asymmetry | 0.379 | 0.997 | 16 |
| Strand-biased fragments | 0.385 | 0.996 | 16 |
| Adapter tails | 0.497 | 0.996 | 16 |
| Contamination | 0.385 | 0.996 | 16 |
| Minority 5% | 0.386 | 0.995 | 16 |
| Minority 30% | 0.384 | 0.997 | 16 |
| Equal-abundance strains | 0.383 | 0.995 | 16 |
| Tandem repeats | 0.367 | 0.996 | 16 |
| Inverted repeats | 0.306 | 0.315 | 5 |
| Overlapping mates | 0.384 | 0.997 | 16 |
| Long inserts | 0.386 | 0.997 | 16 |
| Discordant pairs | 0.386 | 0.996 | 16 |
| Complex mixtures | 0.382 | 0.997 | 16 |

The key practical issue is not simply sequencing-error tolerance:
the default passing real-data pipeline deliberately **tiles** long
contigs for MiCall, but global full-genome scoring necessarily penalizes
those fragments. On a clonal 2,600-base input, the tagged alpha.3 emitted
two tiles and scored **0.386**, while their overlap recovers a 2,581-base
source contig with a global score of **0.985**. Losing a fully supported
source contig is scientifically avoidable.

The proposed strictly read-supported retention rule (draft PR #240)
preserves a whole contig only when at least 95% of its 31-mer sites have
original-pair depth ≥3 and there is no unsupported tract of 100 sites.
Its *exploratory* first-seed sweep improved the score in 15 evaluated
families without observed decreases; no full 400-case or physical
198-sample acceptance is inferred. It changed output on 18/198 real
paired-FASTQ samples, which is why fresh original-gate requalification
remains necessary before merging it.

The end of a read-supported assembly may also be truncated by conservative
extension depth thresholds. Even a well-supported 2,581-base contig can
lack terminal bases that original reads contain, limiting its global score
against a fully supported competitor. An explicit, non-reference-based,
original-pair-supported terminal extension merits independent study.
Coverage holes and severe library amplification effects may be
**unidentifiable** from available reads; never fill them by consulting
the hidden benchmark genome.

## Gate integrity and next steps

The corrected scorer and separately timed seven-image runner were
merged in PR #241 and do not touch the native assembly algorithm. They score both
DNA orientations identically, do not mount hidden truth in containers,
run the default Rust ELF with an empty environment and only necessary
CLI parameters, and do not count tool failure as an Ivanka win.

1. Complete the genuine fresh original physical-198 MiCall A/B comparison
   for the read-supported whole-contig candidate; re-prove both all-r Ψ
   criteria before adopting it.
2. Re-execute all **400 × 7** synthetic assemblies under the corrected,
   source-pinned, container-isolated timing and scoring procedure.
3. Audit competitor failures by tool and family without silently
   changing acceptance definitions or treating failures as wins.
4. Run all **198 real × 7** MiCall comparisons on the identical updated
   MiCall base, with fresh controls and independently checked provenance.
5. Investigate original-read-pair-supported terminal extension,
   disconnected coverage, minority mixtures, and repeat ambiguity
   without reference-conditioned selection or benchmark-specific knobs.
6. Report the exact sample and family outcomes, nonnegative-all-r Ψ
   evidence and independently checked immutable result hashes; only
   then can the mandatory combined acceptance gate be claimed.

The synthetic cohort was consulted during development. A passing result
on it would still not constitute untouched held-out biological or
clinical validation.
