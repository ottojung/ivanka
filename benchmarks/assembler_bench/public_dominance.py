"""Publish only complete-cohort, independently validated pairwise Ψ proofs."""
import json
import math
from pathlib import Path

from .psi_matrix import matrix
from .public_metrics import CATALOG


def rows_for(run):
    if run.get("cohort") == "synthetic" and not run.get("hxb2_truth_verified"):
        return []
    result = []
    for number, sample in enumerate(run.get("samples", [])):
        tools = {}
        for name in run["tools"]:
            score = sample.get("score", {}).get(name)
            runtime = sample.get("seconds", {}).get(name)
            failed = name in sample.get("failures", [])
            valid = (type(score) in (int, float)
                     and type(runtime) in (int, float)
                     and math.isfinite(score) and math.isfinite(runtime))
            tools[name] = {
                "status": "success" if valid and not failed
                          and sample.get("outcome") == "success" else "failed",
                "score": score, "seconds": runtime,
                "diagnostics": sample.get("diagnostics", {}).get(name, {})}
        result.append({"id": sample.get("alias", str(number)),
                       "results": tools})
    return result


def enrich(public):
    """No generated verdict for incomplete or ineligible historical data."""
    if public.get("schema") != "ivanka.assembler-bench.public.v1":
        raise ValueError("unsupported public results schema")
    for run in public["runs"]:
        is_real_pass = (run["cohort"] == "real"
                        and run["status"] == "passed-original-only"
                        and run.get("psi", {}).get("alignment", {}).get(
                            "positive_all_nonnegative") is True
                        and run.get("psi", {}).get("runtime", {}).get(
                            "positive_all_nonnegative") is True)
        count = run.get("expected_sample_count", run["sample_count"])
        psi = matrix(rows_for(run), run["tools"], expected=count,
                     eligible=is_real_pass, diagnostic_keys=CATALOG)
        if is_real_pass:
            original = run["psi"]
            alignment = psi["metrics"]["alignment"]["Ivanka"]["IVA"]
            runtime = psi["metrics"]["runtime"]["Ivanka"]["IVA"]
            for result, expected in ((alignment, original["alignment"]),
                                     (runtime, original["runtime"])):
                if (result["status"] != "dominates"
                        or abs(result["proof"]["psi1"]
                               - expected["psi1"]) > 1e-7):
                    raise ValueError("public PSI conflicts with certificate")
        run["dominance_matrix"] = psi
        run["micall_fork_provenance"] = {
            "status": "historical-unverified",
            "message": ("Old images are not proven to originate from "
                        "exact ottojung/MiCall fork commits; neither this "
                        "report nor its visualizations constitute "
                        "Intent 011-compliant image qualification."),
        }
    return public


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = enrich(json.loads(args.source.read_text()))
    with args.output.open("x") as output:
        json.dump(report, output, sort_keys=True, indent=2)
        output.write("\n")
    print("PAIRWISE_PUBLIC_MATRICES", len(report["runs"]))


if __name__ == "__main__":
    main()
