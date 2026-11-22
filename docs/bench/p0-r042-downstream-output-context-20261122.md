# R042 physical gate: native-contig context and downstream selection

**Read-only finding — November 22, 2026.** This note supplements the preserved [R042 X-mask experiment](https://github.com/ottojung/ivanka/blob/leash/p0-r042-xmask-refutation/docs/bench/p0-r042-xmask-lead-refutation-20261122.md). It does **not** constitute an Ivanka fix or a change to the frozen benchmark.

## Established facts

The frozen R042 physical MiCall run has **Ivanka score 102**, while the best original competitors, SPAdes and Velvet, score **179**; the physical per-sample 90%-of-best floor is **161.1**. Every arm receives the same two MiCall-generated G2P contigs: a 324-base sequence (SHA256 `2ae22268ac7e2e68fc09be45f524e8f3eab1d41accce7219f5891eeb9896bc3a`) and a 306-base sequence (SHA256 `edf384f99973ae80a6d3f30c2026218a68edcea5df6f822c36f26e70d82d2f05`).

The following counts were independently re-derived from preserved `combined_contigs.fasta`, `stitched_contigs.fasta` and `contigs.csv` under the original physical case checkpoint. *Native* means a contig emitted by the candidate assembler, excluding the two identical G2P contigs appended by MiCall.

| Assembler | Native contigs in `combined_contigs.fasta` | Injected G2P contigs | Retained combined total | Final `contigs.csv` winner |
| --- | ---: | ---: | ---: | --- |
| **Ivanka** | 4 | 2 | 6 | 306-base, 102-point final result |
| **SPAdes** | **0** | 2 | 2 | **324-base, 179-point** final result |
| **Velvet** | 68 | 2 | 70 | **324-base, 179-point** final result |
| **IVA** | 2 | 2 | 4 | 306-base final result |

The downstream `stitched_blast.csv` and `contigs.csv` are different across assembler inputs despite the identical G2P-injected contigs. For Ivanka, the final CSV selects a B-KR region and the 306-base consensus; SPAdes selects a C-CN region and the 324-base consensus.

The prior **emit-only-324** Ivanka experiment was properly performed in an isolated prospective run. It still produced score 102 and the 306-base final winner. This is decisive **against that one output-selection remedy**, and the failed Rust variants must not be merged.

## Scientific correction

It does **not** follow that *no* Ivanka-only change can affect the shared downstream result. SPAdes feeds **zero native contigs** and obtains a different outcome; Velvet feeds **68** and also obtains that outcome. MiCall's outcome depends on the *context of upstream native contigs*, not simply on whether a 324-base sequence appears at all. The exact causal features remain unproven.

Equally, the SPAdes observation is **not** a license to make Ivanka omit a strongly supported candidate merely because an evaluator would prefer that outcome. The 324-base candidate has substantial independent read support (approximately 184.4 exact placements per base and no uncovered positions on the source-read diagnostic). Any withholding, deduplication, abundance weighting, or candidate-order rule must be **prospective, based on original reads only, independently justified**, and tested against minority sequences, read-pair support and diverse physical controls. Do not use benchmark scores, evaluator references, genotyping seeds, sample IDs or post hoc truth to make assembly decisions.

## Next P0 bounded investigation

1. With the frozen inputs in **read-only mode**, compare the four native FASTA sets and each subsequent MiCall `stitched_blast.csv`/`stitched_contigs.csv`/`contigs.csv` stage. Separate **number of contigs**, exact-duplicate representations, order/naming, grouping, and sequence content; avoid assuming which factor causes the region choice.
2. When permitted by the active **40-minute/4 GB** and shared disk safeguards, use **isolated prospective scratch**, separate from all 4,634 terminal execution artifacts, for minimal *diagnostic counterfactuals*: no native contigs, 324 alone, additional independently read-supported contigs, and control of duplicate native+G2P representation. This is diagnosis, not a candidate production rule. Never overwrite or count a diagnostic run as a replacement for the source-frozen trial.
3. Only introduce a Rust source change if a **general reference-blind, read-justified and phase-safe** rule emerges. Demonstrate its effect on independent non-cherry-picked physical controls, then R042 and the original 198-case IVA floor; maintain strict signed-power Ψ(r)>0 for all r≥0 for physical score and runtime, sampled RAM/time limits, and synthetic nonregression before a broad prospective run.
4. The other six assemblers' failures and the official seven-way gate remain **P3 last**, per the [founder-ordered workplan](ordered-work-20261121.md). Investigating shared downstream *causation* for P0 is allowed; it is not permission to patch the frozen MiCall checkout or initiate comparator repairs early.

**Status:** physical original IVA comparison remains **PASS**; R042 best-of-six floor remains **FAIL**, all-seven physical remains **NOT PASSED**, synthetic remains **NOT PASSED**. The frozen `v0.1.0-alpha.4` benchmark remains unchanged.

**Provenance:** frozen source image-manifest SHA256 `9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f`; original result artifacts `/workspace/micall-frozen-seven-20261117/phase-real198`; [annotated release](https://github.com/ottojung/ivanka/releases/tag/v0.1.0-alpha.4). The failed diagnostic code remains on the unmerged `leash/p0-r042-xmask-refutation` branch.
