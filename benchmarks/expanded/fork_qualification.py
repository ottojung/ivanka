"""Independently assemble and check the two source-attested seven-way cohorts."""
import argparse
import json
from pathlib import Path

from benchmarks.assembler_bench.fork_progress import checked
from benchmarks.assembler_bench.hxb2_preview import sha
from benchmarks.assembler_bench.real_progress import snapshot
from benchmarks.assembler_bench.real_public import sample_aliases
from .adapters import ASSEMBLERS
from .gate import summarize_gate
from .real_matrix import join_real_runs
from benchmarks.assembler_bench.dedicated_image_attestation import SCHEMA

NAME = "ivanka.expanded.dedicated-qualification.v1"


def evaluate(synthetic, real, physical_data, runner, attestation,
             source_roots, base):
    """Full qualification is impossible before six complete physical arms."""
    att = json.loads(Path(attestation).read_text())
    if att.get("schema") != SCHEMA:
        raise ValueError("qualification requires seven dedicated MiCall branches")
    frozen, synthetic_rows, _, verified = checked(
        synthetic, runner, attestation, source_roots, base)
    if verified != att:
        raise ValueError("synthetic attestation drift")
    images = frozen["images"]
    physical = snapshot(real, physical_data, runner, attestation, base, images)
    counters = physical["candidates"]
    progress = {
        "synthetic": len(synthetic_rows),
        "real_candidates": counters,
        "expected": {"synthetic": 400, "real": 198},
    }
    result = {
        "schema": NAME, "pass": False, "status": "incomplete",
        "provenance": {
            "synthetic_manifest_sha256": sha(Path(synthetic) / "run_manifest.json"),
            "real_manifest_sha256": physical["run_manifest_sha256"],
            "dedicated_attestation_sha256": sha(attestation),
            "qualification_source_sha256": sha(Path(__file__)),
            "unique_fork_commits": len({item["source_commit"]
                                        for item in att["images"].values()}),
        },
        "progress": progress, "gate": None,
    }
    if result["provenance"]["unique_fork_commits"] != 7:
        raise ValueError("dedicated qualification requires seven distinct commits")
    if (len(synthetic_rows) != 400 or
            any(item["finished"] != 198 for item in counters.values())):
        return result
    specification = {name: {
        "image_id": images[name],
        "results_jsonl": str(Path(real) / name / "results.jsonl"),
    } for name in ASSEMBLERS if name != "iva"}
    try:
        physical_rows = join_real_runs(specification)
    except (ValueError, KeyError, TypeError, OSError):
        result["status"] = "invalid-physical-evidence"
        return result
    alias = sample_aliases(physical_data)
    for row in physical_rows:
        if row["id"] not in alias:
            raise ValueError("physical result outside frozen 198 manifest")
        row["id"] = alias[row["id"]]
    evidence = summarize_gate([*synthetic_rows, *physical_rows])
    result["gate"] = evidence
    result["pass"] = bool(evidence["pass"])
    result["status"] = "passed" if evidence["pass"] else "failed"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("synthetic", "real", "physical-data", "runner",
                 "attestation", "source-roots", "base"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.synthetic, args.real, args.physical_data,
                      args.runner, args.attestation, args.source_roots,
                      args.base)
    with args.output.open("x") as destination:
        json.dump(report, destination, sort_keys=True, indent=2)
        destination.write("\n")
    print("EXPANDED_DEDICATED_QUALIFICATION", report["status"],
          "synthetic", report["progress"]["synthetic"],
          "real", {tool: item["finished"] for tool, item in
                  report["progress"]["real_candidates"].items()}, flush=True)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
