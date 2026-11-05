# Direct same-read-pair shared-block/marker evidence (v2)

**Experimental read-only artifact.** Does not change Ivanka, MiCall, IVA, remapping, stitcher, the 198-sample numerical milestone, or reference panel.

The v1 sidecar records full local-block and nearby-marker allele counts separately. Separate counts must not be treated as phase linkage.

The optional **--direct-links** switch emits the new version **ivanka.shared_unphased_evidence_direct.v2**; without it, the original v1 JSON remains unchanged. For each marker it reports only original strict read pairs that directly observe **every shared-block base and that marker** at Q15 or higher. It does not impute unsequenced insert bases or use transitive graph connections.

Usage after a completed MiCall run (supply the exact original region, remap references and zero-based masked interval):

    python3 benchmarks/shared_unphased_evidence.py RUN/ivanka/conseq.csv RUN/ivanka/remap_conseq.csv RUN/ivanka/scratch/remap.csv --region TARGET_REGION --reference REF_1 --reference REF_2 --mask-start START --mask-end END --direct-links --output PRIVATE_AUDIT_DIR/direct-v2.json

Each marker's counts include original paired QNAME IDs and separately distinct consistent paired-sequence signatures. Identical signatures with conflicting or incomplete observations are excluded from distinct-signature support. Both mates share the original pair identifier; an individual qname counts at most once per marker. Exact observed block allele, marker allele and marker reference positions are recorded in the private sidecar. Read IDs are redacted by default.

A single pair can observe more than one marker; **do not sum counts across markers**. Distinct pair sequences do not establish independent DNA molecules or absence of PCR duplication. Local block-marker co-observation does not establish a full-length haplotype. A zero is explicit absence of direct local linkage, not proof that the true haplotype is absent.

## Independent verification

    python3 benchmarks/verify_shared_unphased_sidecar.py PRIVATE_AUDIT_DIR/direct-v2.json --artifact-dir RUN/ivanka --original-fastq-r1 ORIGINAL_R1.fastq.gz --original-fastq-r2 ORIGINAL_R2.fastq.gz --status-output PRIVATE_AUDIT_DIR/direct-v2-verified.json

The verifier recomputes all direct links from the original three SHA256-matched MiCall CSVs and, with original FASTQs supplied, validates every original remap record's nucleotide and Phred strings against its correct mate. It rejects changed node counts, invented links, relocated sources and read ID disclosure. Verified status includes only per-marker counts, never read IDs/alleles, and always says full-length phase and independent physical molecule inference are false. The v1 consumer output remains unchanged.

## Authentic frozen HCV controls — November 4, 2026

| | S48 | S98 |
| --- | ---: | ---: |
| Original lowercase-x target [start,end) | [1057,1102) | [1058,1086) |
| Shared block length | 45 | 28 |
| Nearby marker loci | 1 | 3 |
| Strict original QNAME pairs eligible for local evidence | 14,867 | 19,014 |
| Direct full-block-to-marker QNAME pairs | 39 | 0, 0, 0 |
| Consistent distinct paired-read signatures | 39 | 0, 0, 0 |

Both reports pass read-only replay against the exact original remap sources and original paired FASTQs. Private artifacts are on marceline-dev at /workspace/ivanka-lab/unphased-shared-evidence-direct-v2-20261104/ and must not be committed to the repository. The 198-sample qualification remains historical and does not constitute biological phase safety.
