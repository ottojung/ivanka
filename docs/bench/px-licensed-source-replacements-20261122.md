# PX: replacing two source-infeasible exploratory assemblers

**Decision recorded November 22, 2026.** The ten-assembler PX programme remains **experimental and NONQUALIFYING**. These substitutions change only the *prospective source-pinned roster*, not any frozen MiCall image or result, and do not assert a successful build or benchmark.

## Why two proposed tools cannot be honestly shipped

- **VICUNA / mvicuna** at `437843110f5e6b63087f57ded9b9c93654391451` has no auditable redistribution grant for its application code and its current CLI emits assembled/merged **FASTQ reads**, not an implemented final contig FASTA output. Its repository's third-party licensed components do not license the main program. A MiCall-ready assembler adapter cannot be inferred from the README's aspirational consensus description.
- **PEHaplo** at `eeb564329ed7f5b5b99d1b79a81d7962fc13eeca` has a plausible paired-end de novo path and `Contigs.fa` output, but no complete source license grant at that pinned revision. The bare `__license__ = "GPL"` metadata does not identify terms/version or provide adequate distribution permission.

These original records, their exact source commits, and the source-based reasons remain in the registry's `blocked_original_candidates`. **No binary or benchmark was produced for either.** If distribution permission or a real FASTA contract is independently resolved, reconsider them separately; never rewrite history.

## Prospective licensed replacements

| Candidate | Pinned upstream revision | License evidence | Source-only feasibility | Remaining hard gate |
| --- | --- | --- | --- | --- |
| [SOAPdenovo2](https://github.com/aquaskyline/SOAPdenovo2) | `7560c0b9d59e253cb0c819eca40d60f8636b4a11` | Pinned repository [`LICENSE`](https://github.com/aquaskyline/SOAPdenovo2/blob/7560c0b9d59e253cb0c819eca40d60f8636b4a11/LICENSE), GPL-3.0 | `README.md` documents paired short-read libraries and `all -s <config> -K <k> -o <prefix>`; contig-generating command | README states a generic **minimum 5 GB RAM**, above this programme's strict **4,000,000,000-byte** cap. **Do not build, tune or run** unless a small-virus, bounded memory feasibility method is demonstrated and then observed under the independent resource guard. If not, mark infeasible, choose another tool. |
| [Fermi-lite](https://github.com/lh3/fermi-lite) | `85f159e5a2e15a4c4fb41cdfce91ba0c9b68d2e1` | Pinned [`LICENSE.txt`](https://github.com/lh3/fermi-lite/blob/85f159e5a2e15a4c4fb41cdfce91ba0c9b68d2e1/LICENSE.txt), explicit MIT license | `fml-asm` is a short-read overlap/FM-index assembler; `example.c` calls `fml_assemble`, then `fml_utg_print` | Source `misc.c:fml_utg_print` prints *assembled unitigs as FASTQ*, not input reads or arbitrary graph fragments. An audited adapter must combine both paired FASTQ input streams into supported input and convert **unitig FASTQ** to MiCall valid unitig FASTA without changing sequences; valid zero-unitig output is empty FASTA. Test pair handling, lengths, phase retention, failure codes, and 4 GB/40-minute bounds. |

Upstream source pins, license paths, and evidence are independently checked. Exact source commits are cataloguing information, **not OCI image IDs**. No execution results or MiCall adapter branches are claimed by this document.

## Next implementation rules

1. Build adapter branches **only** from `ottojung/MiCall` pinned shared baseline, with individual assembler commands and no modification of the frozen seven-assembler clinical code. Before committing, compare changes to the established eight adapter-only branches.
2. Produce a real source-built native binary hash, then isolated tool-only reproducible container SHA. Retain license notices and any upstream code distribution obligations. A wrapper must faithfully emit FASTA unitigs; zero valid unitigs is allowed, but failures cannot be reclassified as success.
3. All expensive PX builds, images, and sample pilots remain **blocked** unless shared `/workspace` has at least **32 GiB available**, the separate PX store and **all** incremental data including temporary build/cache fit within **8 GiB**, and only **one** exploration worker exists. Reserve pessimistic future disk growth, continuously monitor, stop before either bound, and never duplicate historical FASTQ assets.
4. When admitted, each tool gets at least one genuinely measured source-attested physical paired-FASTQ pilot and one synthetic paired-FASTQ pilot with MiCall final MAX, true outcome/failures, in-container timing, and 4 GB/40-minute resource checks. Never use posthoc evaluator truth/references to guide assembly. Only subsequent explicit founder approval can promote any new assembler to qualifying.
5. Keep the founder's priority order: **P0 physical then P1 synthetic**, PX may progress independently under capacity safeguards; **P2** physical metrics follows core qualification, **P3** other original assembler failure repairs is last. The original frozen **4,634** terminal arms and `v0.1.0-alpha.4` remain untouched.

**Status at decision:** 8/10 previous candidate adapter branches exist; 2/10 replacement candidates are now **source-pinned in the registry only**; **0 new** candidate OCI images and **0 new** candidate pilots. This does not make all ten experimentally benchmarked.

## Updated milestone — November 22, 09:55 UTC

Both replacements now have separate, **source-only** `ottojung/MiCall` fork integration branches: SOAPdenovo2 `bench/assembler-soapdenovo2` at `a02075c1549160e61abd435b6bf75ee88aa4988e`, **12/12** focused source tests; Fermi-lite `bench/assembler-fermi-lite` at `b8e6959b4943be32ee3b7698530d84690018ac1e`, **24/24** focused source tests. Exact fork SHAs are separately pinned in the experimental candidate registry. The earlier eight-branch counts above describe the decision-time state and do not represent current source integration completeness.

**Ten of ten source branches exist; zero new validated native binary hashes, OCI images, authentic physical pilots, synthetic pilots or qualifying additions exist.** The originally blocked VICUNA and PEHaplo source/license records remain preserved. SOAPdenovo2's full physical-4GB feasibility remains unproven despite its dynamically allocated k-mer data structures; fail closed if actual pilots cannot satisfy the immutable 4,000,000,000-byte cap. The native `SOAPdenovo-63mer` target is present in the pinned upstream Makefile, with vendored BAM linker archives under `sparsePregraph/inc` and `standardPregraph/inc`. This is **source feasibility**, not a compiled artifact attestation.

No image build or sample execution is permitted while `/workspace` free space is below 32 GiB or the independent 8 GiB incremental PX budget cannot be guaranteed. P0 physical qualification and its continuously supervised resource-bounded runs have priority; P1 synthetic, P2 physical diagnostics and P3 comparator repairs remain in the founder's order.
