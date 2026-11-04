# Attesting original FASTQ provenance of MiCall remap rows

This independent, opt-in **read-only audit** connects an already completed
MiCall remap.csv to its original paired R1/R2 FASTQ files. It verifies
that all remap QNAMEs really occur in both paired FASTQs and that
**every remap nucleotide sequence and Phred quality string** appears
as a contiguous substring of the matching original mate
(**SAM first-in-pair must match original R1; second-in-pair must match R2**),
possibly reverse-complemented (with qualities reversed).

A successful attestation means the particular remap rows carry
observed original sequence and quality, even if MiCall trims bases
or reuses the same overlapping mate sequence in two SAM rows.
It does **not** verify per-haplotype read allocation, physical
molecule or PCR independence, correct assembly, insert sequence,
long-range phase, or biological validity of candidate contigs.

For an already completed MiCall run, use:

    python3 benchmarks/attest_remap_fastq_provenance.py RUN/ivanka/scratch/remap.csv ORIGINAL_R1.fastq.gz ORIGINAL_R2.fastq.gz --output PRIVATE_AUDIT_DIR/remap-raw-provenance.json

The output includes only counts, SHA256 hashes and explicit
non-inference declarations, never read IDs, nucleotide sequences
or quality strings. A remap record is checked against both
original mates but a read-pair ID is counted **once**. Quality
strings, not only bases, must match exact raw FASTQ substrings.

R1 and R2 must be separate source files; using the same FASTQ twice
cannot establish paired source provenance.

The audit fails closed for a missing or duplicated QNAME,
unaligned original mate order, malformed FASTQ record, a
remap row without original sequence-and-quality provenance,
repeated remap mappings under the same QNAME, or missing original
R1/R2 designator. It never changes remap records, assembly,
the pinned IVA cache or PSI scoring.

## Genuine source-pinned checks (November 4, 2026)

| Evidence | S48 | S98 |
| --- | ---: | ---: |
| Original paired FASTQs scanned | 86,144 | 26,496 |
| Original QNAMEs represented in remap.csv | 32,324 | 22,223 |
| Original remap SAM rows authenticated | 64,648 | 44,446 |
| Paired rows with identical sequences | 26,925 (83.3%) | 14,878 (66.9%) |
| Paired rows with identical quality strings | 0 | 0 |
| Original QNAMEs with strict primary proper-pair mappings | 32,088 | 22,079 |
| SAM rows without original bases/quality provenance | **0** | **0** |

This authenticates all original remap row sequences and quality
strings for these two saved experiments. It also explains why
**two SAM rows must not be interpreted as two independent
molecules**. Their nucleotide strings frequently coincide,
while their distinct quality strings still originate in the
raw read observations.

The reports with input SHA256s are kept privately at
/workspace/ivanka-lab/remap-original-fastq-provenance-20261104/.
These results cannot be generalized to different MiCall preprocessing
or library formats without rerunning the verifier.
