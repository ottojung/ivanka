"""Authenticate preserved direct-v2 shared-mask sidecars with remap+FASTQ.

Read-only audit: verifies each selected sidecar by exact recomputation from
hash-pinned MiCall CSVs and, when original paired FASTQs are provided, by
per-mate raw sequence+quality attestation. Never mutates MiCall or FASTQ,
never assigns haplotype phase, never treats counts as independent molecules,
and never permits cross-marker summation as haplotype depth.
"""
import argparse
import glob
import json
import os
from pathlib import Path

from verify_shared_unphased_sidecar import EvidenceContractError, digest, verify


SCHEMA = "ivanka.direct_mask_sidecar_authentication.v1"


def _fastqs(sample_dir):
    """Return sorted R1,R2 FASTQ(.gz) paths from an original sample dir."""
    root = Path(sample_dir)
    pairs = {}
    for path in sorted(glob.glob(str(root / "*.fastq*"))):
        name = Path(path).name
        mate = None
        for marker, value in (("_R1_", 1), ("_R2_", 2), ("_1.fastq", 1),
                              ("_2.fastq", 2)):
            if marker in name:
                mate = value
                break
        if mate:
            pairs.setdefault(mate, path)
    if 1 not in pairs or 2 not in pairs:
        raise EvidenceContractError(f"Cannot find original R1/R2 FASTQs in {root}")
    return pairs[1], pairs[2]


def authenticate(targets, *, fastq_roots=(), output=None):
    """Verify selected sidecars; targets are dicts or resolved paths."""
    records = []
    roots = [Path(r).resolve(strict=True) for r in fastq_roots]
    for target in targets:
        spec = target if isinstance(target, dict) else {}
        sidecar = Path(spec.get("sidecar", target)).resolve(strict=True)
        report = json.loads(sidecar.read_text())
        artifact_dir = Path(spec.get("artifact_dir")
                            or report["input_provenance"]["remap_sam_csv"]["path"]).resolve().parent.parent
        sample = (spec.get("sample") or report.get("sample")
                  or artifact_dir.parent.name)
        r1 = spec.get("fastq_r1")
        r2 = spec.get("fastq_r2")
        if r1 and r2:
            r1, r2 = str(Path(r1).resolve()), str(Path(r2).resolve())
        else:
            r1 = r2 = None
            names = [sample, artifact_dir.parent.name, artifact_dir.name]
            for root in roots:
                for name in names:
                    if not name:
                        continue
                    candidate = root / name
                    if candidate.is_dir():
                        try:
                            r1, r2 = _fastqs(candidate)
                        except EvidenceContractError:
                            continue
                        break
                if r1:
                    break
        status = verify(sidecar, artifact_dir, r1, r2)
        records.append({
            "sample": sample,
            "region": report["region"],
            "mask_start": report["mask_start"],
            "mask_end": report["mask_end"],
            "mask_length": report["mask_end"] - report["mask_start"],
            "sidecar_path": str(sidecar),
            "sidecar_sha256": digest(sidecar),
            "artifact_dir": str(artifact_dir),
            "raw_fastq_authenticated": r1 is not None,
            "per_marker_direct_original_pair_observations":
                status.get("per_marker_direct_original_pair_observations", []),
            "per_marker_distinct_consistent_pair_sequence_signatures":
                status.get("per_marker_distinct_consistent_pair_sequence_signatures", []),
            "strict_original_read_pair_ids_evaluated":
                status["strict_original_read_pair_ids_evaluated"],
            "verification_schema": status["schema_version"],
            "cross_marker_pair_counts_summable": False,
            "haplotype_phase": "unidentified",
            "independent_physical_molecules_assigned": False,
            "haplotype_specific_depth_assigned": False,
            "modifies_micall_consensus": False,
            "affects_198_acceptance": False,
        })
    result = {
        "schema_version": SCHEMA,
        "record_count": len(records),
        "records": records,
        "interpretation": (
            "Per-marker direct local linkage only, independently recomputed "
            "from hash-pinned remap CSVs and optionally authenticated against "
            "original paired FASTQ sequence+quality. Counts are not additive "
            "across markers, not independent physical molecules, not per-"
            "haplotype depth, and not full-length phase. No MiCall consensus, "
            "198 acceptance, IVA cache, or original source files were modified."),
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output is not None:
        destination = Path(output).resolve()
        protected = [Path(t if isinstance(t, (str, Path)) else t["sidecar"]).resolve().parent
                     for t in targets]
        protected += [Path(r["input_provenance"]["remap_sam_csv"]["path"]).resolve().parent.parent
                      for r in (json.loads(Path(t if isinstance(t,(str,Path)) else t["sidecar"]).read_text())
                                for t in targets)]
        for root in roots:
            protected.append(root)
        if any(destination == folder or folder in destination.parents for folder in protected):
            raise EvidenceContractError("Cannot write inside original source directories")
        if destination.exists():
            if not destination.is_file() or destination.read_text() != encoded:
                raise EvidenceContractError("Refusing to overwrite a different report")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(encoded)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sidecars", nargs="+", type=Path)
    parser.add_argument("--fastq-root", action="append", default=[], type=Path,
                        help="Directory containing per-sample original FASTQ folders")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = authenticate(args.sidecars, fastq_roots=args.fastq_root,
                              output=args.output)
        if args.output is None:
            print(json.dumps(result, indent=2, sort_keys=True))
    except (EvidenceContractError, KeyError, TypeError, OSError,
            json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
