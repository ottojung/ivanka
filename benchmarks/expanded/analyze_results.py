"""Diagnostic analysis of genuine MiCall results; never claims causal proof.

Consumes immutable physical JSONL, not assembler inputs. Output aggregates
outliers, project categories, contig counts and paired timing/score deltas.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from statistics import median, mean

from .gate import psi


def _pearson(a, b):
    if len(a) != len(b) or len(a) < 3:
        return None
    ma, mb = mean(a), mean(b)
    numerator = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    divisor = (sum((x-ma)**2 for x in a) * sum((y-mb)**2 for y in b)) ** 0.5
    return round(numerator/divisor, 5) if divisor else None


def _ranks(x):
    order = sorted(range(len(x)), key=x.__getitem__)
    result = [0.] * len(x)
    i = 0
    while i < len(x):
        j = i+1
        while j < len(x) and x[order[j]] == x[order[i]]:
            j += 1
        for k in range(i, j):
            result[order[k]] = (i+j+1)/2
        i = j
    return result


def analyze(records, expected=198):
    """A diagnostic report only; the immutable-hash verifier remains authority."""
    samples, malformed = [], []
    seen = set()
    for rec in records:
        if rec.get("status") != "finished":
            continue
        name = rec.get("sample")
        if name in seen:
            malformed.append("duplicate sample")
            continue
        seen.add(name)
        try:
            a, b = rec["iva"], rec["ivanka"]
            q = rec["best_contig_acceptance"]
            if (a["exit_code"] != 0 or b["exit_code"] != 0
                    or any(not math.isfinite(float(v)) for v in
                           (a["seconds"], b["seconds"], q["iva_score"],
                            q["ivanka_score"]))):
                raise ValueError("non-successful arm or nonfinite measurements")
            project = rec.get("provenance", {}).get("micall_project_code", "unknown")
            samples.append({
                "sample": name, "project": project or "unknown",
                "delta_time": a["seconds"] - b["seconds"],
                "delta_score": q["ivanka_score"] - q["iva_score"],
                "iva_time": a["seconds"], "ivanka_time": b["seconds"],
                "iva_contigs": q.get("iva_contig_count"),
                "ivanka_contigs": q.get("ivanka_contig_count"),
                "iva_best_length": q.get("iva_best_contig_length"),
                "ivanka_best_length": q.get("ivanka_best_contig_length"),
                "ratio": (q["ivanka_score"]/q["iva_score"]
                          if q["iva_score"] > 0 else None),
            })
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            malformed.append(str(exc))
    delta_times = [x["delta_time"] for x in samples]
    delta_scores = [x["delta_score"] for x in samples]
    def outcomes(x):
        return {"wins": sum(v>0 for v in x),
                "losses": sum(v<0 for v in x),
                "ties": sum(v==0 for v in x)}
    def breakdown(rows):
        if not rows:
            return None
        return {"n": len(rows),
                "runtime": outcomes([r["delta_time"] for r in rows]),
                "alignment": outcomes([r["delta_score"] for r in rows]),
                "mean_runtime_savings_seconds": mean(r["delta_time"] for r in rows)}
    report = {
        "schema": "ivanka.expanded.retrospective.v1",
        "interpretation": "read-only exploratory diagnostics, NOT source qualification or causality",
        "complete": len(samples) == expected and not malformed,
        "expected": expected, "valid_samples": len(samples),
        "malformed_or_incomplete": malformed,
        "runtime": outcomes(delta_times),
        "alignment": outcomes(delta_scores),
        "mean_runtime_savings_seconds": mean(delta_times) if samples else None,
        "median_runtime_savings_seconds": median(delta_times) if samples else None,
        "total_runtime_savings_seconds": sum(delta_times),
        "pearson_runtime_vs_alignment_delta": _pearson(delta_times, delta_scores),
        "spearman_runtime_vs_alignment_delta": _pearson(
            _ranks(delta_times), _ranks(delta_scores)) if len(samples)>2 else None,
    }
    groups = defaultdict(list)
    for row in samples:
        groups[row["project"]].append(row)
    report["project_groups"] = {name: breakdown(rows)
                                for name, rows in sorted(groups.items())}
    def anonymize(row):
        return {"sample_sha256_prefix": hashlib.sha256(
            str(row["sample"]).encode()).hexdigest()[:12],
            "project": row["project"], "delta_score": row["delta_score"],
            "delta_time": row["delta_time"],
            "iva_contigs": row["iva_contigs"],
            "ivanka_contigs": row["ivanka_contigs"],
            "iva_best_length": row["iva_best_length"],
            "ivanka_best_length": row["ivanka_best_length"]}
    report["largest_runtime_regressions"] = [
        anonymize(r) for r in sorted(samples, key=lambda x:x["delta_time"])[:12]]
    report["largest_alignment_regressions"] = [
        anonymize(r) for r in sorted(samples, key=lambda x:x["delta_score"])[:12]]
    report["runtime_wins_with_alignment_loss"] = sum(
        row["delta_time"]>0 and row["delta_score"]<0 for row in samples)
    report["runtime_losses_with_alignment_gain"] = sum(
        row["delta_time"]<0 and row["delta_score"]>0 for row in samples)
    for field in ("iva_contigs", "ivanka_contigs",
                  "iva_best_length", "ivanka_best_length"):
        pairs = [(r[field], r["delta_time"]) for r in samples
                 if isinstance(r[field], (int, float))]
        report["pearson_runtime_vs_"+field] = (_pearson(*map(list, zip(*pairs)))
                                                 if len(pairs)>2 else None)
    if report["complete"] and len(samples) == 198:
        report["alignment_psi"] = psi(delta_scores)
        report["runtime_psi"] = psi(delta_times)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_jsonl", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    records = [json.loads(line) for line in args.results_jsonl.read_text().splitlines()
               if line.strip()]
    report = analyze(records)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print("RETROSPECTIVE_COMPLETE" if report["complete"]
          else "RETROSPECTIVE_INCOMPLETE", report["valid_samples"])


if __name__ == "__main__":
    main()
