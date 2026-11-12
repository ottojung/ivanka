# Pinned biological references — benchmark generator only

**NEVER distribute these FASTAs to Ivanka or any competing assembler.**
References are used only by the HXB2-anchored synthetic generator and
the independent evaluation/ancestry validator.

Three publicly deposited, accession-versioned HIV-1 genomes were retrieved
from NCBI's GenBank nucleotide service on 2026-11-12:

| Accession | Subtype | Description |
| --- | --- | --- |
| [K03455.1](https://www.ncbi.nlm.nih.gov/nuccore/K03455.1) | B | HIV-1 HXB2, reference genome |
| [MH705157.1](https://www.ncbi.nlm.nih.gov/nuccore/MH705157.1) | A | HIV-1 isolate P4039 |
| [U46016.1](https://www.ncbi.nlm.nih.gov/nuccore/U46016.1) | C | HIV-1 isolate C2220 |

The downloaded FASTA bytes and SHA-256s are pinned in `manifest.json`.
`build_alignment.py` uses deterministic global pairwise alignments
onto the full-length HXB2 coordinate sequence (match +2, mismatch −1,
gap-open −7, extension −1), merging insertion columns by coordinate
and retaining aligned parent bases and gaps. The complete aligned
`hxb2-subtypes-aligned.fasta` is also checked by SHA-256 against the
manifest and may be regenerated and compared.

Random recombinant breakpoints select **homologous aligned columns**;
each recombinant begins with an HXB2-derived block and may alternate
randomly chosen subtype A/C blocks. Unselected parent insertions,
reference gaps and deletion positions are handled by the alignment.
Mutations, when present, affect ≤5% of the resulting ungapped truth
sequence at **uniformly sampled positions without replacement**.
Every generating parent, breakpoint, seed, substitution and SHA-256 is
preserved in hidden case ancestry metadata.

The Rust binary has no reference-FASTA argument, the MiCall integration
invokes it with an empty environment, and container build rules install
only the compiled Rust executable, not this source directory.

The generator's frozen 400-case dataset is verifiable with:

```sh
python3 -m benchmarks.expanded.hxb2_cohort DATASET \
  --seeds 16 --verify-only --certificate ATTESTATION.json
```

A completed truth-validation attestation does **not** imply the
mandatory seven-tool MiCall benchmark has been executed or passed.


## Source-attested 400-case HXB2 cohort (November 12, 2026)

- Frozen 400-case source manifest: `hxb2-400-v2-cohort.json`
  (SHA-256 `314e9b67429b332a900ec98829144d3b065d6473733eefaf9337a89e17ce3ea6`)
- Replay-validated truth attestation: `hxb2-400-v2-validation.json`
  (verification SHA-256 `7d21ff441b2a0297baecb830ad6e67421e72d878e4398dc4a79acc3b932c2cb3`)
- Entire synthetic dataset at `/workspace/ivanka-hxb2-qualified400-v2-20261112`
  on `marceline-dev`; no patient/source-private data
- 25 read-level mechanism families × 16 deterministic seeds, 900 paired
  reads per ordinary case (modified for low/ultra-deep families)
- Every generating haplotype and contaminant is a real HXB2-derived
  reference or a random homologous recombinant of HXB2 with A/C
  parental subtype references, with up to 5% uniformly random
  independently replayable truth substitutions

**This proves source-eligibility, not superior assembly.** Full
MiCall-integrated seven-assembler 598-case evaluation and
independently positive all-exponent alignment/runtime Ψ remain mandatory.


## New v3 MiCall-compatible input format

The v2 source-correct synthetic truth used old single-token FASTQ
identifiers, which MiCall's `fastq_g2p` parser rejects before assembly.
For canonical integrated benchmarking, use the separately committed
`hxb2-400-v3-micall-cohort.json` manifest and
`hxb2-400-v3-micall-validation.json` attestation. The v3 data regenerate
the same real HXB2-derived genomes and read behaviors using
two-token Illumina CASAVA paired read identifiers
(`@... 1:N:0:1` / `@... 2:N:0:1`), with no alteration of
biological truth or mutation positions.

Pinned v3 `cohort.json` SHA-256:
`a390ba4ecec60e2dcf2af8d7a933d7c399e401e5a44a42ac7adf868f2b341113`.
Historical v2 results and identities remain intact and are not
rewritten or upgraded. Every canonical run verifies each FASTQ
descriptor, both mate IDs, full hidden HXB2 ancestry and output SHA256
before any assembler starts.
