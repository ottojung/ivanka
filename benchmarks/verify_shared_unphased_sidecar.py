"""Fail-closed downstream contract for original-pair, unphased MiCall evidence.

This is an opt-in POSTPROCESSING consumer. It never mutates MiCall, claims
haplotype-specific coverage, or feeds this evidence into 198 acceptance.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


class EvidenceContractError(ValueError):
    """The artifact could not be authenticated as unphased evidence."""


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify(sidecar_path, artifact_dir, original_r1=None, original_r2=None):
    """Recompute producer evidence from hash-pinned original MiCall inputs."""
    sidecar_path = Path(sidecar_path)
    root = Path(artifact_dir).resolve(strict=True)
    if not root.is_dir():
        raise EvidenceContractError("Expected a MiCall artifact directory")
    report = json.loads(sidecar_path.read_text())
    is_direct_v2 = report.get("schema_version") == (
        "ivanka.shared_unphased_evidence_direct.v2")
    if (report.get("schema_version") not in (
            "ivanka.shared_unphased_evidence.v1",
            "ivanka.shared_unphased_evidence_direct.v2")
            or ("marker_direct_links" in report) != is_direct_v2
            or report.get("artifact_type") != "shared_unphased_evidence_sidecar"
            or report.get("phase_status") != "unidentified"
            or report.get("phase_inferred") is not False
            or report.get("full_length_haplotype_phase_inferred") is not False
            or report.get("independent_molecules_inferred") is not False
            or report.get("insert_bases_imputed") is not False
            or report.get("original_read_pair_qnames_counted_once") is not True
            or report.get("raw_qnames_included") is not False
            or "original_qname_provenance" in report
            or any("original_qnames" in node or node.get("is_phased") is not False
                   for node in report.get("nodes", []))):
        raise EvidenceContractError("Not a redacted, explicitly unphased v1 sidecar")
    expected = {"final_conseq_csv": root / "conseq.csv",
                "remap_conseq_csv": root / "remap_conseq.csv",
                "remap_sam_csv": root / "scratch" / "remap.csv"}
    for name, path in expected.items():
        entry = report.get("input_provenance", {}).get(name)
        if (not isinstance(entry, dict) or not path.is_file()
                or Path(entry.get("path", "")).resolve() != path.resolve()
                or entry.get("sha256") != digest(path)):
            raise EvidenceContractError(f"Missing, relocated or modified source: {name}")
    if type(report.get("minimum_quality")) is not int or report["minimum_quality"] < 15:
        raise EvidenceContractError("Cannot accept evidence below Q15")
    references = report.get("selected_reference_names")
    if (not isinstance(references, list) or len(references) < 2
            or any(not isinstance(r, str) or not r for r in references)
            or len(set(references)) != len(references)):
        raise EvidenceContractError("Invalid selected original remap references")
    producer = Path(__file__).with_name("shared_unphased_evidence.py")
    command = [sys.executable, str(producer),
               *(str(expected[k]) for k in expected),
               "--region", report["region"]]
    for ref in references:
        command.extend(["--reference", ref])
    if is_direct_v2:
        command.append("--direct-links")
    for flag, key in (("--mask-start", "mask_start"),
                      ("--mask-end", "mask_end"),
                      ("--anchor", "anchor"),
                      ("--radius", "radius"),
                      ("--min-phred", "minimum_quality")):
        value = report.get(key)
        if type(value) is not int:
            raise EvidenceContractError(f"Invalid original {key}")
        command.extend([flag, str(value)])
    try:
        verified = json.loads(subprocess.run(
            command, check=True, capture_output=True, text=True,
            timeout=120).stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError) as exc:
        raise EvidenceContractError("Cannot independently reproduce sidecar") from exc
    if verified != report:
        raise EvidenceContractError("Sidecar disagrees with original read-pair evidence")
    if (original_r1 is None) != (original_r2 is None):
        raise EvidenceContractError("Both original FASTQ mates are required")
    raw = None
    if original_r1 is not None:
        from attest_remap_fastq_provenance import attest
        try:
            raw = attest(expected["remap_sam_csv"], original_r1, original_r2)
        except (ValueError, OSError, KeyError) as exc:
            raise EvidenceContractError("Original FASTQ mate provenance failed") from exc
        if raw["source_sha256"]["original_remap_csv"] != report["input_provenance"]["remap_sam_csv"]["sha256"]:
            raise EvidenceContractError("FASTQ authenticity does not match remap source")
        if raw["strict_proper_pair_ids_in_remap"] < report["strict_original_read_pair_ids_evaluated"]:
            raise EvidenceContractError("More evidence pairs than authentic strict remap pairs")
    result = {
        "schema_version": "ivanka.unphased_sidecar_verification.v1",
        "verification": "passed_source_sha256_and_exact_recomputation",
        "sidecar_sha256": digest(sidecar_path),
        "region": report["region"],
        "mask_start": report["mask_start"],
        "mask_end": report["mask_end"],
        "selected_reference_names": references,
        "strict_original_read_pair_ids_evaluated":
            report["strict_original_read_pair_ids_evaluated"],
        "local_allele_nodes": sum(n["feature_kind"] == "block" for n in report["nodes"]),
        "marker_context_nodes": sum(n["feature_kind"] == "marker" for n in report["nodes"]),
        "haplotype_phase": "unidentified",
        "independent_physical_molecules_assigned": False,
        "haplotype_specific_depth_assigned": False,
        "modifies_micall_consensus": False,
        "affects_198_acceptance": False,
    }
    if is_direct_v2:
        # These per-marker same-original-pair link counts MUST NOT be added
        # across markers or treated as independent physical molecules.
        marker_links = report["marker_direct_links"]
        if (not isinstance(marker_links, list)
                or len(marker_links) != report["marker_count"]):
            raise EvidenceContractError("Invalid direct marker linkage shape")
        result.update({
            "schema_version": "ivanka.unphased_sidecar_verification_direct.v2",
            "local_direct_marker_linkage_only": True,
            "per_marker_direct_original_pair_observations": [
                link["direct_joint_observation_count"] for link in marker_links],
            "per_marker_distinct_consistent_pair_sequence_signatures": [
                link["direct_joint_distinct_pair_sequence_signatures"]
                for link in marker_links],
            "transitive_graph_links_assigned": False,
            "long_range_haplotype_phase_inferred": False,
            "cross_marker_pair_counts_summable": False,
        })
    if raw is not None:
        result.update({
            "schema_version": (
                "ivanka.unphased_sidecar_verification_direct_raw_fastq.v2"
                if is_direct_v2 else
                "ivanka.unphased_sidecar_verification_raw_fastq.v1"),
            "verification": "passed_source_sha256_exact_recomputation_and_per_mate_raw_fastq",
            "original_fastq_provenance": "sequence_and_phred_authenticated_per_original_mate",
            "raw_original_read_pairs_scanned": raw["raw_pair_ids_scanned"],
            "original_remap_pair_ids_authenticated": raw["remap_pair_ids_verified"],
            "raw_fastq_sha256": {
                "r1": raw["source_sha256"]["original_fastq_r1"],
                "r2": raw["source_sha256"]["original_fastq_r2"],
            },
        })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sidecar_json", type=Path)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--status-output", type=Path)
    parser.add_argument("--original-fastq-r1", type=Path)
    parser.add_argument("--original-fastq-r2", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.sidecar_json, args.artifact_dir,
                        args.original_fastq_r1, args.original_fastq_r2)
        if args.status_output:
            dest = args.status_output.resolve()
            source_root = args.artifact_dir.resolve()
            raw_roots = [path.resolve().parent for path in
                         (args.original_fastq_r1, args.original_fastq_r2)
                         if path is not None]
            if (dest == args.sidecar_json.resolve()
                    or any(dest == folder or folder in dest.parents
                           for folder in [source_root, *raw_roots])):
                raise EvidenceContractError("Cannot write within original source directories")
            encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
            if dest.exists():
                if not dest.is_file() or dest.read_text() != encoded:
                    raise EvidenceContractError("Cannot overwrite a different verified status")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as file:
                    file.write(encoded)
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
    except (EvidenceContractError, KeyError, TypeError, OSError,
            json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
