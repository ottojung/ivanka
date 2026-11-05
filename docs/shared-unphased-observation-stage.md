# Shared unphased observation export/consume stage (opt-in, read-only)

Implements a provenance-correct, explicitly **SHARED/UNPHASED** local block
observation stage for MiCall remap evidence. It is an opt-in postprocess over
existing original MiCall outputs; it does **not** change MiCall consensus logic,
final MAX sequences, 198 acceptance, the 90%/1800s/PSI gates, IVA caches,
reference panels, or original FASTQ files.

## Safety invariants

- No original fragment is assigned to competing haplotypes.
- No full-length haplotype phase is inferred or imputed; missing inserts are not
  filled.
- Per-site Q15 spectra are pooled across selected remap hypotheses and count
  original strict read-pair IDs once; counts are **not** independent DNA
  molecules and **not** haplotype-specific depth.
- Minority/alternative alleles are preserved as observed counts.
- `modifies_micall_consensus=false`, `modifies_final_max_sequence=false`,
  `safe_for_final_max_overwrite=false`, `affects_198_acceptance=false`.
- Raw QNAMEs are never included.

## Artifacts and consumers

`benchmarks/export_shared_unphased_observations.py`:

- `export ... --output OUTSIDE_SOURCE.json` computes a versioned observation
  artifact from hash-pinned `conseq.csv`, `remap_conseq.csv`, and
  `scratch/remap.csv`, plus optional strict original R1/R2 FASTQ mate
  provenance (`--original-fastq-r1/--original-fastq-r2`, requiring per-mate
  sequence+quality attestation via `attest_remap_fastq_provenance`).
- `verify ARTIFACT.json --require-fastq` is fail-closed: it re-checks all
  source SHA256 hashes and deterministically recomputes observations from the
  original sources; when FASTQ provenance is claimed/required it reattests raw
  FASTQ mate sequence+quality. Tampered site counts or checksums are rejected.
- `consume_observations(..., authenticated=True)` (library) performs the same
  authenticated recomputation. `authenticated=False` returns
  `consumer_mode=untrusted_parse_diagnostic_only` and
  `empirical_use_permitted=false`; it must not be used for empirical claims.

## Genuine isolated replay (read-only, private paths)

Validated against preserved, original artifacts (no source mutation):
- `S48 73090AMIDI-MidHCV_S48, 2-HCV-1a [1095,1126)` 31bp, refs
  2/3/4/5-HCV-1a: 14,867 strict pairs evaluated; min shared Q15 119, max alt 6;
  74 shared complete-block pairs / 78 any complete block; 32,324 remap pairs
  reauthenticated to original FASTQs.
- `S12 73111AMIDI-MidHCV_S12, 4-HCV-1a [1027,1065)` 38bp, refs
  2/3/4/7-HCV-1a: 29,151 strict pairs evaluated; min shared Q15 104, max alt 69;
  52 shared / 63 any complete block; 51,869 remap pairs reauthenticated.

These show pooled per-base Q15 support with limited complete-block/direct phase;
they are not full-length haplotypes or independent molecules.

## MiCall integration / A/B blocker

An executable tested opt-in *postprocess* integration is provided (artifact
export+authenticated consume against existing MiCall outputs). A safe derived
candidate MiCall image for genuine isolated S48/S12 end-to-end MiCall A/B was
**not** built or executed in this run: no candidate image build was started and
no 198/IVA/frozen benchmark was touched. Any future A/B must use an isolated
derived image/workdir, keep final MAX/acceptance/gates unchanged, and require
explicit approval before expensive cohort runs.
