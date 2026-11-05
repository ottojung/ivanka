# Unphased single-SNV evidence without remapping competition

The standalone Ivanka Rust assembler can now report strongly supported local
single-nucleotide alternatives in an **optional, separate TSV** while emitting
its ordinary assembly FASTA **unchanged**. The experimental full-contig
preservation in draft PR #172 added extra competing MiCall hypotheses, and
genuine full MiCall cap-1000 A/B runs lost four Q15 minority allele calls in
S48 and one in S12 without improving the best 33-reference alignment score.
This audit-only alternative deliberately does **not** add those contigs.

## Usage

    ivanka --reads1 ORIGINAL_R1.fastq.gz --reads2 ORIGINAL_R2.fastq.gz \
      --max-contigs 1000 --output PRIVATE/ivanka-contigs.fasta \
      --unphased-snv-audit PRIVATE/extra-local-snv.tsv

The audit path must be new, distinct from the normal FASTA, and outside the
original paired-FASTQ and supplied seed-input directories. The file is created
exclusively with mode 0600; it refuses to overwrite an existing report.
Without the option, the original output selection remains unchanged.

The TSV records only a **local 61-nucleotide context** centered on each
alternative and its original FASTA parent index, zero-based offset, reference
base and alternative base, and approximate support statistics. It never
outputs another full-length remapping contig or alters read assignments.

The original contig selector first retains exactly the same baseline
ranked sequences. From the normally suppressed near-identical alternatives,
the optional evidence collector records at most 16 unique local SNVs when:

- The alternative is at least 128 bases and differs from one retained
  equal-length sequence at exactly one **internal** nucleotide.
- Extension-supporting read-record count is at least 50 and one-quarter
  of the corresponding retained contig's count.
- At least three distinct canonical 31-mers specific to the alternative,
  absent from the **entire** ordinary retained output, each have at least
  five occurrences in Ivanka's existing sampled original read 31-mer table.
- The same parent-index/offset/alternative-base combination is reported
  only once, even if assembly proposed identical candidates repeatedly.
- After any ordinary rescue replacement, its matching parent must still
  appear in the final output. Otherwise it is withheld.

**Scientific limitations:** The sampling is Ivanka's original
first-50,000-pair, every-third-31-mer heuristic. It does **not** inspect
base qualities (no Q15 claim); multiple overlapping k-mers may come from
the same read pair; repeated reads may be PCR duplicates. These counts are
neither independent physical molecules nor evidence of long-range
haplotype phase. The local context is not an authenticated complete
genome, and the parent FASTA index is meaningful only for that exact
FASTA output. Downstream use must separately bind original FASTQ SHA256s,
verify Q15 read-pair alleles against the saved evidence and prove any edge
assignment via direct reads, as in the source-bound shared/unphased tools
merged in PRs #169–#171.

## Genuine first-50,000-original-paired-FASTQ A/B (November 5, 2026)

All files are private on `marceline-dev`; no source FASTQ, MiCall MAX,
frozen 198-run output, IVA cache, original reference panel or PSI result was
modified.

| Original sample | Baseline contigs | Audit-arm contigs | Ordinary FASTA SHA256 | New local SNP records |
| --- | ---: | ---: | --- | ---: |
| S48, cap 1000 | 122 | 122 | `5689cc31acf8b8368af71a1c9970eac8662a6e02e7557093758097dd1ba5bbf6` | 3 |
| S12, cap 1000 | 35 | 35 | `d2d0ddec061ced04d4319abcec654531b7a090a2fc103360bf4296257d64d714` | 3 |
| S48, cap 16, with controlled research seed | 16 | 16 | `862ec1f31bde4a59c458864dc14cbafd8f4bbff1062af6a44cba9e70bee63caa` | 0 |

Every baseline and audit-arm FASTA above is **byte-identical**. The
controlled 180bp S48 seed was derived from a saved local contig; neither
genuine original frozen S48 nor S12 MiCall run had G2P seed records, so the
seeded comparison tests integration behavior, not a previously issued
MiCall G2P seed file.

Private audited output directory:
`/workspace/ivanka-lab/snv-unphased-audit-20261105/`.

S48 cap1000 SNV TSV SHA256
`7825f4d9df470f34e3481fdbbf736eaeee8b7ef18cc2fbce0a45fe97e2d25dbe`.
S12 cap1000 SNV TSV SHA256
`bfbc05162d8d9683da5b19f877d4bf6b65700e6b9ceaecb06f81123a99488f30`.

This is **not** a new MiCall alignment improvement or a new 198-sample
biological qualification. The purpose is to preserve useful local
variation evidence without activating the read-stealing regression seen
with supplementary full-length contigs in draft PR #172.
