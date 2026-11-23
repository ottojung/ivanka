# Original-pair phase conflict experiment

**Read-only research diagnostic; never a MiCall contig filter.** The prototype does not change assembler FASTA, MiCall remapping, stitching or MAX, IVA, or the frozen 198 results.

For each local SNV, it requires an exact Q15 context with seven flanking bases on each side. Read pairs count once per original QNAME; identical paired sequences must agree to count as distinct sequence evidence. It tests only direct original paired-read co-observation, never transitive paths, imputed insert bases, independent physical DNA molecules or full-length phase.

Critically, every candidate context is checked against **all ordinary input contigs** (not just the reported contig), including possible alternate bases and reverse complements. Ambiguous placements are withheld. All original contigs must be supplied as the ambiguity scope, even when only the first eight or sixteen are screened.

A local conflict is reported only if the candidate combination has *zero* direct original Q15 pairs and another combination has at least five direct pairs and three consistent distinct paired sequences. No observed bridge means **UNKNOWN**, not correct. Even a conflict flag does not authorize removing the contig.

## Known-truth synthetic experiment (November 5, 2026)

The deterministic seed-17 dataset contains 1,000 original read pairs, 100-base reads, 300-base fragments and a 0.2% base-error rate. With variants at positions 280 and 400, 21 source pairs overlap both variants. Requiring full 31-base contexts (15 flanks) detects zero of those direct links, a false negative caused by mate geometry. With 7-base flanks, nine pairs directly co-observe both unique Q15 contexts: the deliberately recombinant sequence is flagged, while the true generating haplotype is not. Variants 280 and 900 have zero bridged read pairs; both long-range phases remain unresolved.

## Real original-pair scope check

From the preserved, hash-pinned 50,000-pair S48/S12 assembler A/B, screen 1,000 original pairs and evaluate the first eight original contigs against the **entire** output FASTA (122 contigs in S48; 35 in S12). Under cross-contig context checks, both samples have zero uniquely attributable candidate SNV sites and zero actionable phase-veto flags. A within-contig-only check produced misleading apparent conflicts for S12. These are NOT biological evidence that any contig is invalid.

The command requires externally trusted SHA256 values for FASTA and both R1/R2 FASTQs, verified before and after the scan. Output is a separate private, create-new JSON artifact (not a replacement for any source). Source QNAMEs and raw read sequences are not emitted. This remains an experimental known-truth sensitivity check, not a genuine assembly or MiCall improvement.

Next: represent equivalent local loci across homologous contigs as unphased graph nodes, then attach only direct same-original-pair evidence, without assigning observations to competing full-length haplotypes.

## Private source-bound real diagnostics

Authentic original MiCall-facing FASTA and both original FASTQ mates were independently checked against trusted SHA256s before and after scanning. These reports are private on marceline-dev (not public GitHub):

- S48: `/workspace/ivanka-lab/phase-veto-source-pinned-20261105/S48-full-scope-source-bound.json`, SHA256 `758e05b259f356208d7eb64907e38b92b32005b17984269f37c513a944dab4dd`.
- S12: `/workspace/ivanka-lab/phase-veto-source-pinned-20261105/S12-full-scope-source-bound.json`, SHA256 `4b5b4ba8cb6dc27c91756e115ef415469920bf5aa759bb709a74908e808ae998`.

Negative results are specific to the first 1000 original pairs and first eight evaluated contigs. They do NOT prove absence of all phase information elsewhere, and cannot be used to infer the full 198-sample status.
