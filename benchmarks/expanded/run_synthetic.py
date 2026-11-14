"""Run all seven pinned assemblers on hidden-truth synthetic inputs.

Preflight requires all binaries and verifies their SHA256 against the fixed
tool manifest before any work. No partial cohort can qualify.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random

from .adapters import ASSEMBLERS, execute, require_programs
from .hxb2_cohort import attestation
from .score import dominant_truth_score
from .synthetic import fingerprint


def cohort_rows(cohort_root):
    root = Path(cohort_root).resolve()
    cohort = json.loads((root / "cohort.json").read_text())
    if cohort.get("schema") not in (
            "ivanka.expanded.cohort.hxb2.v1",
            "ivanka.expanded.cohort.hxb2.v2"):
        raise ValueError("legacy random or invalid HXB2 synthetic cohort")
    if cohort["schema"].endswith(".v2"):
        from .hxb2_lowdepth_v2 import verify_metadata
        verify_metadata(root, cohort)
    from .hxb2_truth import validate
    if cohort["samples"] != len(cohort["cases"]):
        raise ValueError("cohort manifest is incomplete")
    for entry in cohort["cases"]:
        directory = root / entry["id"]
        if not directory.is_dir() or directory.parent != root:
            raise ValueError("unsafe or missing synthetic case directory")
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest.get("schema") != "ivanka.expanded.synthetic.hxb2.v1":
            raise ValueError("non-HXB2 synthetic sample manifest")
        if not validate(directory):
            raise ValueError("unverified HXB2 source ancestry")
        if manifest["sha256"] != entry["sha256"]:
            raise ValueError("cohort and per-case hashes disagree")
        for file_name, digest in manifest["sha256"].items():
            path = (directory / file_name).resolve()
            if not path.is_relative_to(directory) or fingerprint(path) != digest:
                raise ValueError("synthetic source or truth hash mismatch")
        yield entry["id"], directory, manifest


def run(cohort_root, results_root, binary_spec, *, threads=2, timeout=1800):
    truth_proof = attestation(cohort_root, expected=400)
    binaries = require_programs(paths=binary_spec["paths"])
    if binaries != binary_spec["binary_provenance"]:
        raise ValueError("binary sha256 mismatch; repin the complete tool suite")
    output = Path(results_root)
    output.mkdir(parents=True, exist_ok=False)
    path = output / "results.jsonl"
    attempted = 0
    with path.open("x", buffering=1) as log:
        for case_id, directory, manifest in cohort_rows(cohort_root):
            row = {"id": case_id, "cohort": "synthetic",
                   "family": manifest["family"],
                   "truth_validation": truth_proof,
                   "input_sha256": hashlib.sha256(
                       (manifest["sha256"]["reads/R1.fastq.gz"] +
                        manifest["sha256"]["reads/R2.fastq.gz"]).encode()
                   ).hexdigest(),
                   "results": {}}
            r1 = directory / manifest["read_files"][0]
            r2 = directory / manifest["read_files"][1]
            order = list(ASSEMBLERS)
            random.Random(int.from_bytes(hashlib.sha256(
                case_id.encode()).digest()[:8], "big")).shuffle(order)
            row["execution_order"] = order
            for name in order:
                execution = execute(name, r1, r2, output / case_id / name,
                                    binaries, threads=threads, timeout=timeout)
                score = 0.0
                if execution["status"] == "success":
                    try:
                        metric = dominant_truth_score(
                            manifest, directory / manifest["hidden_truth_file"],
                            execution["fasta"])
                        score = metric["score"]
                        execution["truth_diagnostics"] = metric
                    except (OSError, ValueError, RuntimeError) as exc:
                        execution["status"] = "failed"
                        execution["error"] = f"independent truth scoring: {exc}"
                sha = binaries[name]
                provenance = "".join(v["sha256"] for _, v in sorted(sha.items()))
                row["results"][name] = {
                    "status": execution["status"], "score": score,
                    "score_origin": "assembler_fasta_diagnostic_v1",
                    "timing_origin": "standalone_assembler_wall_v1",
                    "seconds": execution["elapsed_wall_seconds"],
                    "sha256": hashlib.sha256(provenance.encode()).hexdigest(),
                }
            log.write(json.dumps(row, sort_keys=True)+"\n")
            attempted += 1
    return attempted


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--binaries", required=True, type=Path,
                        help="Pre-pinned JSON containing paths and binary_provenance")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args(argv)
    manifest = json.loads(args.binaries.read_text())
    print("ATTEMPTED_SYNTHETIC_CASES",
          run(args.cohort, args.out, manifest,
              threads=args.threads, timeout=args.timeout))
    print("DIAGNOSTIC ONLY: these scores evaluate raw assembler FASTA. "
          "They cannot satisfy pipeline-level Intent 004/006. "
          "Use HXB2-derived truth and full MiCall output for qualification.")


if __name__ == "__main__":
    main()
