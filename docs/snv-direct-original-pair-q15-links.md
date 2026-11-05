# Direct Q15 original-pair linkage among local unphased SNV observations

This optional read-only report complements the original FASTQ Q15 SNV verifier from PR #175. It **never changes** Ivanka's ordinary contigs, MiCall mapping/consensus, IVA control, frozen 198 sample results, or accepted Ψ metrics.

## Independent source and local-node guardrails

Inputs are the original v1 unphased SNV TSV, the ordinary MiCall-facing assembler FASTA, and original R1 and R2 FASTQ files. All **four source SHA256s must be supplied independently by the caller**; the exact original read-pair scan is source-hash checked before and after analysis. The original-Q15 local verifier first requires a valid parent base/offset, unique baseline 31-mer within that parent, absent alternative 31-mer from existing ordinary contigs, at least 10 original Q15 paired IDs and 10 distinct consistent paired-read sequences directly observing the alternative.

The direct-link verifier then reopens those first 50,000 original paired FASTQs and asks whether a **single original read-pair identifier** observes two allele-specific central 31-mers with Phred >=15 at every position. Reverse-complement orientation is supported, but no alignment-to-reference, stitching, gap imputation or distant phase assignment is inferred. A direct observed local allele combination is one of reference/alternative, alternative/reference, or alternative/alternative; reference/reference co-observation is recorded but **cannot activate a discovered-variant edge by itself**.

For each unordered candidate pair, the JSON reports all four original-pair allele-combination counts and all four counts of distinct consistent paired-read-sequence signatures. A signature contributes to a combination only if **every original R1+R2 pair with identical sequences** directly observed that same nonmissing, nonconflicting combination. Pair IDs count once regardless of overlapping mates, multiple exact matches, and candidate order. Contradictory or unqualified pair observations cannot manufacture an edge.

The default exploratory edge requires both local SNV candidates to have passed the separate independent Q15 positional screen, plus **>=10 original read pairs and >=10 distinct consistent paired-read sequences in the same alternative-containing allele combination**. A pair of SNVs connected through a third SNV never creates a synthetic transitive link. There is no summing counts across markers, no physical DNA-molecule identity, no haplotype-specific depth, and no full-length haplotype phase claim.

Use the same four independent-source SHA256 flags as the original verifier, with the new script:

    python3 benchmarks/snv_q15_direct_links.py \
      PRIVATE/unphased-snv.tsv PRIVATE/ordinary-contigs.fasta \
      ORIGINAL/sample_R1.fastq.gz ORIGINAL/sample_R2.fastq.gz \
      --sha256-audit-tsv TRUSTED_TSV_SHA256 \
      --sha256-ordinary-fasta TRUSTED_FASTA_SHA256 \
      --sha256-original-r1 TRUSTED_R1_SHA256 \
      --sha256-original-r2 TRUSTED_R2_SHA256 \
      --min-phred 15 --min-pairs 10 \
      --output SEPARATE_PRIVATE_DIR/unphased-local-links.json

All outputs are source-hash attested, aggregate-count-only and mode 0600. No raw read identifiers, read sequences, or source files are copied or uploaded.

## Frozen original S48/S12 FASTQ replay, November 5, 2026

The first 50,000 original read pairs per sample were analyzed. The original FASTA remains byte-identical to the baseline and is **not** rerun through MiCall.

Three S48 local SNV candidates passed the individual Q15/unique-parent-offset screen; the TSV lists their offsets in order **217, 677, 395**. Exactly **two** direct allele-combination links pass the exploratory 10-pair/10-distinct-sequence floor:

| Original direct allele combination | Q15 original read pairs | Distinct consistent paired sequences |
| --- | ---: | ---: |
| offset 217 alternative / offset 395 reference | 33 | 33 |
| offset 677 alternative / offset 395 reference | 17 | 17 |

The 217/677 link is withheld. Its strongest individual direct combination has just 6 original pairs; no allele combination has 10. Even though both SNPs have evidence with offset 395, **no transitive 217/677 link is manufactured**.

S12 has one individually Q15- and parent-position-qualified local SNV (offset 458) among three raw audit candidates, and therefore **zero eligible pairwise edges**. Raw reference/reference counts between unqualified candidates are retained as diagnostics only and never authorize edges.

Private immutable reports on marceline-dev (not uploaded to public GitHub):

- /workspace/ivanka-lab/snv-q15-direct-links-20261105/S48-conservative-direct-Q15.json — SHA256 1bedd0bae50be0602940303c9fac83213441d2c960d027087169d9c0932ecabb
- /workspace/ivanka-lab/snv-q15-direct-links-20261105/S12-conservative-direct-Q15.json — SHA256 5764c48dd686027c7d94d5315dcbd65b9b5a205473dab58e7d1b9ec3d20517fc

## Scientific qualification

These are conservative short-range **read-pair co-observations only**. An original paired FASTQ identifier is not necessarily an independently sampled physical DNA molecule (PCR duplicates remain possible). Exact Q15 31-mer matches can occur at homologous genomic loci, even when the reference 31-mer is unique within a specific parent contig. Thus a direct link does not establish full-length phase or correct graph placement. A future graph assembler must carry link provenance and uncertainty explicitly, never infer distant paths from transitivity, and prove safety through isolated genuine MiCall A/B experiments before changing benchmark outputs.
