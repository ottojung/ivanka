"""Emit optional, isolated SHARED/UNPHASED local FASTA nodes only.

A locally supported allele is NOT a full-length phased haplotype. The output
cannot be fed back into ordinary MiCall MAX or counted as independent DNA
molecules. Caller-supplied source hashes/FASTQs provide a trust anchor.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from export_shared_unphased_observations import (
    ObservationExportError, verify_observation_export,
)
from shared_block_consensus_candidate import audit_remap
from shared_locus_remap_coverage import group_loci


def decide_local_node(observation, audited, *, depth=100,
                      min_fraction=0.95, min_complete_signatures=20):
    """Require directly read-derived consensus and protect minority variants."""
    if (type(depth) is not int or depth < 1
            or not 0 < min_fraction <= 1
            or type(min_complete_signatures) is not int
            or min_complete_signatures < 1):
        raise ValueError("Invalid conservative local node thresholds")
    if (observation.get("unphased") is not True
            or observation.get("phase_status") != "unidentified"
            or observation.get("modifies_final_max_sequence") is not False):
        raise ValueError("Only authenticated unphased local evidence permitted")
    sites = audited["positions"]
    spectrum = observation["per_site_q15_observed_allele_spectrum"]
    if len(sites) != len(spectrum) or not sites:
        raise ValueError("Observed local evidence length mismatch")
    for item, original in zip(sites, spectrum):
        if (item["site"] != original["site_zero_based_in_mask"]
                or item["allele_qnames"] !=
                original["q15_original_pair_base_counts"]):
            raise ValueError("Independent Q15 site spectrum mismatch")
    complete = audited["complete_block_observations"]
    signature_counts = complete["distinct_pair_sequence_evidence"]
    complete_signatures = signature_counts["shared_allele_distinct_pair_sequences"]
    fractions = [
        item["shared_base_qnames"] / item["depth_qnames"]
        if item["depth_qnames"] else 0
        for item in sites
    ]
    reasons = []
    if not audited["eligible"] or any(
            item["shared_base_distinct_pair_sequences"] is None or
            item["shared_base_distinct_pair_sequences"] < depth
            for item in sites):
        reasons.append("Q15_original_pair_or_distinct_sequence_site_depth")
    if min(fractions) < min_fraction:
        reasons.append("competing_minority_allele_fraction")
    if complete_signatures < min_complete_signatures:
        reasons.append("insufficient_direct_complete_local_pair_signatures")
    allele = audited["read_derived_candidate"] if not reasons else None
    if allele is not None and (not allele or set(allele) - set("ACGT")):
        raise ValueError("Unresolved read-derived local sequence")
    return {
        "eligible": not reasons,
        "rejection_reasons": reasons,
        "read_derived_local_allele": allele,
        "mask_length": len(sites),
        "min_site_q15_original_pair_ids":
            min(item["shared_base_qnames"] for item in sites),
        "min_site_distinct_pair_sequence_signatures":
            min(item["shared_base_distinct_pair_sequences"] for item in sites),
        "min_shared_allele_fraction": min(fractions),
        "complete_shared_local_original_pair_ids":
            complete["shared_allele_complete_read_pair_ids"],
        "complete_shared_local_distinct_pair_signatures": complete_signatures,
        "full_length_haplotype_phase_proven": False,
        "independent_physical_molecules_proven": False,
        "per_haplotype_coverage_assigned": False,
        "safe_to_fill_existing_max_mask": False,
    }


def compute(observation, *, artifact_dir, screen_ledger,
            screen_sha256, sample, fastq_r1, fastq_r2,
            depth=100, min_fraction=0.95, min_complete_signatures=20):
    verification = verify_observation_export(
        observation, require_fastq=True, artifact_dir=artifact_dir,
        screen_ledger=screen_ledger, sample=sample,
        expected_screen_sha256=screen_sha256,
        original_fastq_r1=fastq_r1, original_fastq_r2=fastq_r2)
    if verification.get("empirical_use_permitted") is not True:
        raise ObservationExportError("External source and FASTQ proof required")
    original = observation["source_paths"]
    with Path(original["final_conseq_csv"]).open(newline="") as stream:
        original_rows = list(csv.DictReader(stream))
    target = [r for r in original_rows
              if r["region"] == observation["region"] and
              r["q-cutoff"] == "15" and
              r["consensus-percent-cutoff"] == "MAX"]
    if len(target) != 1:
        raise ObservationExportError("Ambiguous original MAX region")
    mask = observation["mask_interval_zero_based_half_open"]
    masked = SimpleNamespace(sequence=target[0]["sequence"],
                             start=mask["start"], end=mask["end"])
    with Path(original["remap_conseq_csv"]).open(newline="") as stream:
        available = {r["region"]: r["sequence"] for r in csv.DictReader(stream)}
    refs = {
        name: available[name] for name in
        observation["shared_reference_membership"]["selected_reference_names"]
    }
    # External source binding above ensures the exact original target/mask/ref
    # membership; the independent allele still comes from Q15 read votes.
    group_loci(masked, refs, anchor=observation["anchor_bp"])
    with Path(original["remap_sam_csv"]).open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    audited = audit_remap(masked, refs, rows,
                          minimum_quality=observation["minimum_phred_quality"],
                          required_depth=depth)
    decision = decide_local_node(
        observation, audited, depth=depth, min_fraction=min_fraction,
        min_complete_signatures=min_complete_signatures)
    sequence = decision.pop("read_derived_local_allele")
    identifier = (f"IVANKA_UNPHASED_SHARED_LOCAL__{sample}__"
                  f"{observation['region']}__{mask['start']}-{mask['end']}")
    fasta = f">{identifier} phase=unknown molecules=unknown\n{sequence}\n" if sequence else ""
    result = {
        "schema_version": "ivanka.unphased_shared_local_nodes.v1",
        "sample": sample,
        "region": observation["region"],
        "mask_interval_zero_based_half_open": mask,
        "selected_reference_names": list(refs),
        "source_binding_sha256": screen_sha256,
        "read_derived_local_node_sha256": (
            hashlib.sha256(sequence.encode()).hexdigest() if sequence else None),
        "node_identifier": identifier if sequence else None,
        "locally_supported_unphased_node_emitted": sequence is not None,
        "diagnostics": decision,
        "original_final_max_unchanged": True,
        "may_replace_micall_consensus": False,
        "may_be_assigned_to_competing_haplotypes": False,
        "independent_physical_molecules_inferred": False,
        "full_length_haplotype_phase_inferred": False,
        "affects_198_acceptance": False,
    }
    return fasta, result


def private_write(fasta, metadata, fasta_out, report_out, protected):
    """Never write into any original source tree or overwrite existing files."""
    files = [Path(fasta_out).resolve(), Path(report_out).resolve()]
    if files[0] == files[1]:
        raise ValueError("FASTA and report must be separate files")
    for path in files:
        for source in protected:
            directory = Path(source).resolve()
            if path == directory or directory in path.parents:
                raise ValueError("Refusing output inside original source tree")
        if path.exists():
            raise ValueError("Refusing existing output")
    encoded = [fasta, json.dumps(metadata, indent=2, sort_keys=True) + "\n"]
    for path, data in zip(files, encoded):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation_json", type=Path)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--screen-ledger", type=Path, required=True)
    parser.add_argument("--screen-sha256", required=True)
    parser.add_argument("--sample", required=True)
    parser.add_argument("--original-fastq-r1", type=Path, required=True)
    parser.add_argument("--original-fastq-r2", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=100)
    parser.add_argument("--minimum-fraction", type=float, default=0.95)
    parser.add_argument("--min-complete-signatures", type=int, default=20)
    parser.add_argument("--fasta", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        observation = json.loads(args.observation_json.read_text())
        fasta, report = compute(
            observation, artifact_dir=args.artifact_dir,
            screen_ledger=args.screen_ledger, screen_sha256=args.screen_sha256,
            sample=args.sample, fastq_r1=args.original_fastq_r1,
            fastq_r2=args.original_fastq_r2, depth=args.depth,
            min_fraction=args.minimum_fraction,
            min_complete_signatures=args.min_complete_signatures)
        protected = [args.artifact_dir, args.original_fastq_r1.parent,
                     args.original_fastq_r2.parent, args.observation_json.parent,
                     args.screen_ledger.parent]
        private_write(fasta, report, args.fasta, args.report, protected)
        print(json.dumps({
            "eligible": report["locally_supported_unphased_node_emitted"],
            "reasons": report["diagnostics"]["rejection_reasons"],
            "fasta": str(args.fasta), "report": str(args.report),
            "modifies_micall_consensus": False}, sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
