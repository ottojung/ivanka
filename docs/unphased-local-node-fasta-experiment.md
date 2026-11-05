# Experimental authenticated local shared-node FASTA (unphased)

**Purpose:** Provide graph-oriented, short **local sequence nodes** backed by
authentic original MiCall Q15 read observations, while avoiding the unsafe
shortcut of filling the masked segment of an individual full-length haplotype.

The producer is opt-in and **never** changes the original MiCall MAX consensus,
remap file, IVA baseline, 198 numerical acceptance, reference panel, or raw
FASTQs. The output FASTA must **not** be substituted into MiCall's per-haplotype
MAX sequences or treated as proof of a full-length haplotype. Each accepted
fragment is explicitly labeled `IVANKA_UNPHASED_SHARED_LOCAL`.

## Original source authentication

The input is a saved export produced by
`export_shared_unphased_observations.py` (PR #169). Before inspecting any
sequence, the producer calls the authenticated verifier using the **caller's**
original MiCall artifact directory, correct sample identity, separately
source-attested direct-mask cohort screen and its **externally known SHA256**,
plus both original R1/R2 FASTQ mates. It authenticates the complete source
chain, reference group, exact zero-based masked interval, observed Q15
nucleotide and Phred evidence, and recomputes the original observation
spectrum. Reports without fully authenticated external provenance are
rejected.

It independently rereads the selected original remap rows and applies the
same `shared_block_consensus_candidate.audit_remap` that enforces one original
strict paired QNAME per site (never per remap hypothesis), correct mate
geometry, Q15 calls, consistent paired-read-sequence-signature diversity,
and no conflicting overlapping mate votes. The read-derived local consensus
must match the independently recomputed original per-site Q15 A/C/G/T count
spectrum exactly. No raw read identifiers or complete raw read sequences are
written to the manifest.

## Strict default eligibility (research, not clinical)

All of the following must hold:

- At every base: >=100 original Q15 read-pair IDs supporting the **same**
  shared allele, >=100 consistent distinct paired-read-sequence signatures,
  a strict majority, and no alternative allele reaching that threshold.
- The shared expected allele contributes >=95% of unambiguous Q15 original-pair
  observations at **every** masked base. This protects genuine minority alleles.
- At least 20 consistent distinct original pair-sequence signatures directly
  observe **the entire local block** without inserting unsequenced bases.
- A single, uniquely aligned, exactly shared 31bp-flanked locus in at least
  two selected remap references. The output sequence comes from **observed Q15
  read-derived majority bases**, not simply copied from a reference.
- All source hashes, selected refs and original R1/R2 mates authenticate.

Even these tests do not establish independent biological DNA molecules.
Distinct paired sequences may be correlated by PCR, and a complete local
block does not establish how it joins any distant phase marker.

## Usage

    python3 benchmarks/export_unphased_local_nodes.py PRIVATE/S48-shared-unphased.json \
      --artifact-dir FROZEN_RUN/73090AMIDI-MidHCV_S48/ivanka \
      --screen-ledger PRIVATE/frozen198-v2-direct-summary.json \
      --screen-sha256 5d6caefe76cfee3ec368223482e2e36e91dd82d5ce92d52dc54b93eccda4c716 \
      --sample 73090AMIDI-MidHCV_S48 \
      --original-fastq-r1 ORIGINAL_S48_R1.fastq.gz \
      --original-fastq-r2 ORIGINAL_S48_R2.fastq.gz \
      --fasta PRIVATE/S48-local.fasta \
      --report PRIVATE/S48-local.json

Both outputs must be **new** files outside every input MiCall directory,
original FASTQ directory and independent-ledger source directory. Files are
private (mode 0600), cannot overwrite originals or previously generated
artifacts. When an allele fails eligibility, the FASTA is intentionally
**empty**, with exact failure reasons and counts only in the manifest.
Neither a nonempty FASTA nor an empty FASTA modifies original consensus.

## Genuine frozen-sample S48/S12 A/B, November 5, 2026

This is an A/B of the **new isolated local-node output**, not a new full
MiCall run. Both original MiCall sources/FASTQs and the independent selected
mask ledger were authenticated as required, and MiCall MAX was left intact.

| | S48 2-HCV-1a | S12 4-HCV-1a |
|---|---:|---:|
| Local masked block | 31 bases | 38 bases |
| Minimum Q15 shared original-pair IDs per base | 119 | 104 |
| Minimum consistent distinct paired sequences per base | 119 | 104 |
| Minimum shared-allele fraction across sites | 96.75% | 81.40% |
| Direct original read-pair witnesses for complete block | 74 | 52 |
| Distinct complete-block paired-read sequence signatures | 74 | 52 |
| Decision | **Emit unphased 31-base node** | **Withhold** due competing allele |

The 95% competing-allele guard matters: although S12 passes the 100
per-site pooled-depth diagnostic, a site has **18.6% alternative support**;
it must not be flattened into a shared consensus or counted as an
unambiguous haplotype. S48 passes the local criteria but still has no
validated long-range molecule phase. This is the intended conservative
separation of local sequence identity and complete haplotype assignment.

Private original authenticated evidence and outputs are on marceline-dev:
`/workspace/ivanka-lab/unphased-local-node-20261105/`.

S48 FASTA SHA256 `2be5ca970ade7ffbb80cb1c1e484b40228028711345f812128328aaf49c27b55`
and manifest SHA256 `a851655b3e2e530b69549d470550d30489a92a7323814b3a1004dd899be70db3`.
S12 empty FASTA SHA256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
and veto manifest SHA256
`c92855ec4bae72254a628f07321db48b416b52317facb6d2464d037e238d841f`.

## Next step

To safely affect actual reconstruction quality, graph assembly needs a
typed shared-node/uncertain-edge representation, with original-pair
provenance and minority paths. A reference-free method must prove or
conservatively mark its linkage, while downstream MiCall must not
mistakenly replace the shared node with a phased full-length contig.
A future **derived-image** MiCall single-sample A/B, with marker retention
and final-MAX untouched as control, must precede any benchmark change.
