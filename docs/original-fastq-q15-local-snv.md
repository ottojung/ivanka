# Original-pair Q15 verification for Ivanka's unphased SNV audit

This optional, **read-only** verifier checks the standalone Ivanka assembler's local SNV audit against its **original paired FASTQs**. The assembler's reported k-mer support is not quality-filtered. This verifier separately tests whether the 31-base context centered on each proposed alternative is directly observed at Q15 quality.

## Authentication and input contract

The command requires four source inputs and four independently known SHA256 values: Ivanka's unphased SNV audit TSV, its exact ordinary FASTA, and the original R1/R2 FASTQs. Expected hashes must come from a trusted external ledger, not be derived from possibly modified input files. The verifier checks all four hashes before analysis.

The audit must carry the expected unphased, quality-unchecked, molecule-nonindependent v1 metadata. A candidate must match the exact FASTA parent index and length, original base at the zero-based offset, and 61-base context differing from that FASTA at exactly the center position. It refuses duplicate candidate reports, malformed reads, mismatched original paired IDs, duplicated read-pair identifiers, inconsistent mate designators, and incomplete FASTQ pairs.

For each proposed SNV, scan **at most the first 50,000 original read pairs**, matching the assembler's sampled-read horizon. Count a pair once if either mate contains the exact allele-specific central 31-mer or its reverse complement and every one of the 31 observed base qualities is **at least Phred 15**. Observe baseline and alternative separately. A pair containing both is labeled conflicting and excluded from either allele support. A pair with neither high-quality observation is missing.

Identical paired-read sequences are grouped as a signature. One distinct sequence signature counts only when **all** original pairs sharing that exact R1+R2 sequence signature agree on one nonmissing allele. This is not physical DNA-molecule deduplication: neither QNAMEs nor distinct read sequences prove independent original molecules.

## Experimental local-Q15 screening rule

A candidate passes the exploratory local-Q15 screen only if:

- At least **10 original read-pair IDs** directly observe its alternative 31-mer at Q15 or better.
- At least **10 distinct consistently observed paired-read sequence signatures** support that alternative.
- The matching baseline 31-mer occurs at **exactly one position within the designated parent contig**, considering both orientations and overlapping matches.
- The alternative central 31-mer does **not** already occur anywhere in the ordinary baseline contig FASTA.

Reference-context occurrences across the entire contig set are also reported. Several homologous contigs may contain the same baseline 31-mer, so even a positive screen does **not** establish a uniquely placed full-length haplotype or identify a biological molecule. Repetitive baseline contexts within the same parent are withheld because a central 31-mer cannot locate the reported position.

These thresholds are **research diagnostics only** and are not clinical, per-haplotype, full-block, or 198-benchmark acceptance criteria. The command does not modify MiCall, original FASTQs, the assembler FASTA, IVA, or any original benchmark output. It writes count-only, source-hashed JSON into a separate private file, never raw QNAMEs or read sequences.

## Invocation

    python3 benchmarks/snv_original_fastq_q15.py \
      PRIVATE/snv-audit.tsv PRIVATE/original-contigs.fasta \
      ORIGINAL/sample_R1.fastq.gz ORIGINAL/sample_R2.fastq.gz \
      --sha256-audit-tsv TRUSTED_TSV_SHA256 \
      --sha256-ordinary-fasta TRUSTED_FASTA_SHA256 \
      --sha256-original-r1 TRUSTED_R1_SHA256 \
      --sha256-original-r2 TRUSTED_R2_SHA256 \
      --min-phred 15 --min-pairs 10 \
      --output SEPARATE_PRIVATE_DIR/verified-Q15-SNV.json

## Genuine S48/S12 original-FASTQ study, November 5, 2026

50,000 original read pairs per sample; exact source SHA256 and strict mate identity checks; no MiCall rerun. The underlying optional Rust TSV retains three local variants per sample, while its ordinary FASTA is byte-identical to baseline.

| Sample | Parent / offset | Q15 alternate pairs | Consistent paired sequences | Baseline 31-mer occurrences in parent | Conservative local screen |
| --- | --- | ---: | ---: | ---: | --- |
| S48 | 8 / 217 | 129 | 129 | 1 | Pass |
| S48 | 8 / 677 | 425 | 425 | 1 | Pass |
| S48 | 8 / 395 | 28 | 28 | 1 | Pass |
| S12 | 6 / 344 | 9 | 9 | 1 | Fail: fewer than 10 pairs |
| S12 | 6 / 394 | 45 | 45 | **2** | Fail: ambiguous parent position |
| S12 | 2 / 458 | 189 | 188 | 1 | Pass |

Thus **four of six** local variants pass all current diagnostic guards. S12 offset 394 has 45 genuine Q15 alternative-pair observations, but its baseline 31-mer occurs twice in its parent and 19 times across the full ordinary contig collection. The evidence supports a local sequence observation, not assignment to one particular reported parent offset.

Two separately preserved private reports on marceline-dev:

- /workspace/ivanka-lab/snv-q15-original-verification-20261105/S48-unique-parent-q15.json, SHA256 efdea90fc16a4be9f1f9678ca09bc14e544e16b98930e5c07a26f1e1f372d4a3
- /workspace/ivanka-lab/snv-q15-original-verification-20261105/S12-unique-parent-q15.json, SHA256 f4d0d32504ffbdbd77355330e1579ba2eb94978cefac8d860859aca2b124f03d

Do not upload private reads or private source-attested reports to public GitHub. Future graph consumers must separately verify direct original read-pair links to any distant marker, avoid transitive inference, and leave all shared support explicitly unphased.
