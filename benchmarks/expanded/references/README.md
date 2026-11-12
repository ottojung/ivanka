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

## V4: HXB2 truth-identical, higher-coverage MiCall integration cohort

The November 12 v4 generated cohort provides **all 400 original
25 × 16 HXB2-derived biological truths** with additional original
paired-read observations per sample. The truth FASTAs, the complete
recombinant ancestry records and the mixture fractions are
**byte-identical to all 400 corresponding v3 cases**. There is no
truth tuning, mutation re-clustering, changed parental segment, or
different family selection.

- Pinned source-input manifest:
  `hxb2-400-v4-micall-high-depth-cohort.json`, SHA256
  `964fff8226beef4787226a5542dc2667fff0102bea0b4f4694686b11af1f7f5a`.
- Independent full HXB2 ancestry/CASAVA paired-read validation:
  `hxb2-400-v4-micall-high-depth-validation.json`, all **400/400**
  cases verified. Source template manifest is unchanged.
- Reproduction: `python3 -m benchmarks.expanded.hxb2_cohort
  /data/hxb2-v4 --seeds 16 --pairs 10000 --certificate /data/v4-proof.json`.
- Deterministic read sampling: **10,000 pairs per ordinary case**;
  the preexisting low-depth and ultra-deep read mechanism families
  yield **2,500** and **30,000** pairs respectively. The diverse
  read-level error mechanisms remain the same. HXB2 truth remains
  inaccessible to every assembler under Intents 003 and 008.
- Original generated FASTQ/hidden truth artifacts live on
  `marceline-dev` at
  `/workspace/ivanka-hxb2-depth10000-400-20261112/`.
  The repository pins full per-case SHA256 identities without
  committing hundreds of megabytes of reads.

**Rationale and fairness:** A preliminary seven-arm MiCall test on the
v3 **900-pair** clonal case revealed IVA completed without any
read-supported final remap (honest failed arm); the corresponding
**10,000-pair** clonal case allowed all seven MiCall integrations
to complete and produce read-supported dominant consensuses.
The change applies **identically to every assembler**, not through
Ivanka-only settings or a reference-conditioned source. Preserve the
v3 data and failures as historical diagnostics. This single-case
confirmation does **not** prove any seven-way dominance, all-r Ψ
acceptance, or guaranteed success on other v4 families. A completely
fresh, source-pinned v4 run and independent gate must establish that.
