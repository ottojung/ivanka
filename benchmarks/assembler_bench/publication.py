"""Export only independently verified aggregate/per-case measurements to Pages.

Input may contain private sample names and paths. No source strings or paths
are copied to sample rows: only public numeric fields and fresh aliases.
"""
import argparse
import hashlib
import json
from pathlib import Path

from .public_dominance import enrich

SCHEMA = "ivanka.assembler-bench.public.v1"
RUN_ID = "alpha3-original-real198-20261112"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def real_report(results_path, certificate_path):
    source = Path(results_path)
    certificate = json.loads(Path(certificate_path).read_text())
    if digest(source) != certificate.get("results_jsonl_sha256"):
        raise ValueError("private result digest differs from independent certificate")
    rows = [json.loads(text) for text in source.read_text().splitlines() if text.strip()]
    finished = [row for row in rows if row.get("status") == "finished"]
    if len(finished) != 198 or len(rows) != 396:
        raise ValueError("expected exactly 198 started and 198 finished rows")
    if not (certificate.get("real_data_numeric_gate_pass")
            and certificate.get("valid_pairs") == 198
            and certificate.get("samples_found") == 198
            and not certificate.get("errors")):
        raise ValueError("independent qualification did not pass")
    score_psi = certificate["score_psi"]
    time_psi = certificate["time_psi"]
    if not (score_psi.get("positive_all_nonnegative")
            and time_psi.get("positive_all_nonnegative")):
        raise ValueError("independent all-exponent PSI failed")
    samples = []
    for index, record in enumerate(finished, 1):
        alignment = record["best_contig_acceptance"]
        iva, ivanka = record["iva"], record["ivanka"]
        if (record.get("failed") is not False or
                alignment.get("pass") is not True or
                iva.get("exit_code") != 0 or ivanka.get("exit_code") != 0):
            raise ValueError("unaccounted original benchmark failure")
        for item in (iva["seconds"], ivanka["seconds"],
                     alignment["iva_score"], alignment["ivanka_score"]):
            if not isinstance(item, (int, float)) or item < 0:
                raise ValueError("bad numeric result")
        samples.append({
            "alias": f"R{index:03d}",
            "score": {"IVA": alignment["iva_score"],
                      "Ivanka": alignment["ivanka_score"]},
            "seconds": {"IVA": iva["seconds"], "Ivanka": ivanka["seconds"]},
            "floor_ok": True, "outcome": "success",
        })
    return {
        "schema": SCHEMA, "id": RUN_ID, "date": "2026-11-12",
        "title": "Native Rust Ivanka · original 198 real MiCall samples",
        "cohort": "real", "status": "passed-original-only",
        "expanded_status": "incomplete", "eligible_for_expanded": False,
        "status_reason": "Original IVA-only numeric gate passes; expanded six-rival gate unrun.",
        "tools": ["IVA", "Ivanka"], "sample_count": 198,
        "source_commit": "03a3287fbfde005b2803356f4c764ffdadc4c6ac",
        "certificate_sha256": digest(certificate_path),
        "results_sha256": digest(source),
        "manifest_sha256": certificate["manifest_sha256"],
        "images": {"IVA": certificate["iva_image"],
                   "Ivanka": certificate["ivanka_image"]},
        "psi": {"alignment": score_psi, "runtime": time_psi},
        "samples": samples,
    }


def legacy_synthetic_report(result_path):
    """Historical diagnostics only: no synthetic v1 can qualify Intent 008."""
    rows = [json.loads(text) for text in Path(result_path).read_text().splitlines()
            if text.strip()]
    tools = ["iva", "ivanka", "haploflow", "megahit", "abyss", "spades", "velvet"]
    if len(rows) != 400 or len({row["id"] for row in rows}) != 400:
        raise ValueError("incomplete synthetic diagnostic")
    families = {}
    for row in rows:
        family = row["family"]
        stats = families.setdefault(family, {
            "family": family, "sample_count": 0,
            "scores": {tool: 0.0 for tool in tools},
            "failures": {tool: 0 for tool in tools},
        })
        stats["sample_count"] += 1
        for tool in tools:
            result = row["results"][tool]
            stats["scores"][tool] += float(result["score"])
            stats["failures"][tool] += result["status"] != "success"
    for stats in families.values():
        for tool in tools:
            stats["scores"][tool] = round(
                stats["scores"][tool] / stats["sample_count"], 4)
    if len(families) != 25 or any(x["sample_count"] != 16
                                  for x in families.values()):
        raise ValueError("incomplete synthetic families")
    return {
        "schema": SCHEMA, "id": "legacy-synthetic-v1-20261112",
        "date": "2026-11-12", "title": "Legacy arbitrary-genome cohort · diagnostic only",
        "cohort": "synthetic", "status": "ineligible",
        "expanded_status": "incomplete", "eligible_for_expanded": False,
        "status_reason": "Generic-random truth violates Intent 008; failed tools and invalid original timing.",
        "tools": tools, "sample_count": 400,
        "source_commit": "af111e0664142372c9eb70898efe51a3e4f32ec8",
        "diagnostic_sha256": digest(result_path),
        "families": sorted(families.values(), key=lambda x: x["family"]),
        "samples": [], "psi": {},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-jsonl", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--synthetic-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = [real_report(args.real_jsonl, args.certificate),
               legacy_synthetic_report(args.synthetic_jsonl)]
    # This is a public-data export: never serialize source records themselves.
    output = {"schema": SCHEMA, "title": "Ivanka Assembler Bench",
              "expanded_qualification": "incomplete", "runs": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(enrich(output), sort_keys=True, indent=2) + "\n")
    print("PUBLIC_BENCH_REPORT_WRITTEN", args.output)


if __name__ == "__main__":
    main()
