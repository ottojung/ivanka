# Verified shared/unphased evidence: downstream consumer contract

This **opt-in read-only postprocessing tool** verifies a previously
generated local evidence JSON against the three *original, preserved*
MiCall output CSVs and emits a small status object. It neither edits
the MiCall files nor assigns original pairs to competing haplotypes.

The producer is benchmarks/shared_unphased_evidence.py and the
consumer is benchmarks/verify_shared_unphased_sidecar.py.

## Use

For a previously completed MiCall analysis with these source paths:

- RUN/ivanka/conseq.csv (Q15/MAX final calls)
- RUN/ivanka/remap_conseq.csv (original remap references)
- RUN/ivanka/scratch/remap.csv (original paired remap rows)

Produce an opt-in unphased evidence JSON **outside** the original
analysis directory, selecting exact original target region, reference
names and lowercase-x mask interval. See
docs/shared-unphased-evidence.md for the producer invocation.

Then validate before using the artifact downstream:

    python3 benchmarks/verify_shared_unphased_sidecar.py PRIVATE_SIDE_CAR.json --artifact-dir RUN/ivanka --status-output PRIVATE_AUDIT_DIR/unphased-status.json

The consumer rejects a sidecar if input paths are moved, content hashes
change, any reported feature/allele/count differs from independently
recomputing the v1 producer on the original CSVs, a disclosed original
QNAME appears, quality falls below Q15, or any assertion of full-length
haplotype phase/independent molecules appears. It also forbids writing
the status into the original MiCall artifact directory, overwriting the
sidecar or overwriting a different existing status.

The resulting versioned status has no read IDs or observed nucleotide
alleles. It says phase unidentified and records counts of
**local evidence features only**. It always sets
haplotype_specific_depth_assigned,
independent_physical_molecules_assigned,
modifies_micall_consensus, and affects_198_acceptance to false.

Neither the sidecar nor the verified status is a final MAX consensus,
a biological haplotype assembly, a count of independent molecules,
evidence that all required alleles are phased, or proof that MiCall
preserves ambiguity annotations. Nothing here permits relaxed
per-haplotype Q15 depth thresholds.

## Exact frozen target controls (November 4, 2026)

The original authenticated S48 45-base and S98 28-base HCV target
sidecars were recomputed with the merged producer. Both originally
contained a now-removed, overclaiming boolean named
molecules_not_doubled; **all source hashes, allele nodes and
read-pair counts stayed exactly unchanged**. The old read-only copies
are archived privately with an independent hash ledger.

The refreshed local S48 and S98 reports are both accepted by the
consumer, returning passed_source_sha256_and_exact_recomputation and
haplotype_phase unidentified. Private outputs are under
/workspace/ivanka-lab/unphased-shared-evidence-sidecar-20261104/,
not included in the repository.

Source SHA256 and independent recomputation detect changes, not
biological correctness. A separate, independently validated MiCall
consumer that preserves ambiguity and molecule provenance is still
required before treating the shared evidence as actionable.
