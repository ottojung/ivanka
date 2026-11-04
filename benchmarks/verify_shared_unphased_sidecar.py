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


def verify(sidecar_path, artifact_dir):
    """Recompute producer evidence from hash-pinned original MiCall inputs."""
    sidecar_path = Path(sidecar_path)
    root = Path(artifact_dir).resolve(strict=True)
    if not root.is_dir():
        raise EvidenceContractError("Expected a MiCall artifact directory")
    report = json.loads(sidecar_path.read_text())
    if (report.get("schema_version") != "ivanka.shared_unphased_evidence.v1"
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
    return {
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sidecar_json", type=Path)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--status-output", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.sidecar_json, args.artifact_dir)
        if args.status_output:
            dest = args.status_output.resolve()
            source_root = args.artifact_dir.resolve()
            if (dest == source_root or source_root in dest.parents
                    or dest == args.sidecar_json.resolve()):
                raise EvidenceContractError("Cannot mutate source evidence or MiCall artifacts")
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
