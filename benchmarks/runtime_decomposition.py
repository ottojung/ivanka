"""Diagnostic-only decomposition of a frozen Ivanka/IVA MiCall result cohort.

This reads existing MiCall log files; it never runs or alters either assembler.
A counterfactual zero-assembler time holds every downstream stage fixed.
It cannot establish a formal single-invocation scientific qualification.
"""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
import statistics

STAMP = r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3})"
ASSEMBLY = re.compile(r"Ivanka wrote \d+ contigs in ([0-9]+(?:\.[0-9]+)?)s")
REMAP = re.compile(STAMP + r".*Running remap")
SAM2ALN = re.compile(STAMP + r".*Running sam2aln")


def _timestamp(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S,%f").timestamp()


def parse_stages(log):
    native = ASSEMBLY.findall(log)
    remap = REMAP.findall(log)
    sam2aln = SAM2ALN.findall(log)
    if not native or not remap or not sam2aln:
        raise ValueError("Missing assembler/remap/sam2aln stage markers")
    remap_seconds = _timestamp(sam2aln[0]) - _timestamp(remap[0])
    native_seconds = float(native[-1])
    if not math.isfinite(native_seconds) or native_seconds < 0 or remap_seconds < 0:
        raise ValueError("Invalid native/remap interval")
    return native_seconds, remap_seconds


def signed_psi(differences):
    if not differences:
        raise ValueError("Empty signed-power cohort")
    n = len(differences)
    if any(not math.isfinite(d) for d in differences):
        raise ValueError("Nonfinite signed-power difference")
    return {
        "faster": sum(d > 0 for d in differences),
        "slower": sum(d < 0 for d in differences),
        "ties": sum(d == 0 for d in differences),
        "psi0": sum((d > 0) - (d < 0) for d in differences) / n,
        "psi1": sum(differences) / n,
        "psi2": sum(d * abs(d) for d in differences) / n,
    }


def _group(sample):
    for tag in ("HCV-NS5a", "MidHCV", "V3LOOP", "HLA-B", "NFLHIVDNA"):
        if tag in sample:
            return tag
    return "other"


def cohort(records, expected_samples):
    if len(records) != expected_samples:
        raise ValueError(f"Expected {expected_samples} samples, got {len(records)}")
    names = [record.get("sample") for record in records]
    if any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names):
        raise ValueError("Missing or duplicated sample identity")
    rows = []
    for record in records:
        name = record["sample"]
        if record.get("status") != "finished" or record.get("failed") is not False:
            raise ValueError(f"Unfinished or failed sample: {name}")
        arms = (record["iva"], record["ivanka"])
        times = [float(a["seconds"]) for a in arms]
        if any(not math.isfinite(t) or t <= 0 for t in times):
            raise ValueError(f"Nonpositive/nonfinite arm time: {name}")
        logpath = Path(record["ivanka"]["artifact_dir"]) / "podman.stderr.log"
        native, remap = parse_stages(logpath.read_text(errors="replace"))
        iva, ivanka = times
        if native > ivanka:
            raise ValueError(f"Native time exceeds MiCall arm time: {name}")
        rows.append({"sample": name, "group": _group(name), "iva_seconds": iva,
                     "ivanka_seconds": ivanka, "assembler_seconds": native,
                     "remap_seconds": remap, "delta": iva-ivanka,
                     "zero_assembler_delta": iva-ivanka+native})
    return rows


def summarize(rows):
    groups = {"all": rows}
    for group in sorted(set(r["group"] for r in rows)):
        groups[group] = [r for r in rows if r["group"] == group]
    result = {}
    for group, group_rows in groups.items():
        remap_total = sum(r["remap_seconds"] for r in group_rows)
        ivanka_total = sum(r["ivanka_seconds"] for r in group_rows)
        result[group] = {
            "samples": len(group_rows),
            "native_median_seconds": statistics.median(r["assembler_seconds"] for r in group_rows),
            "native_mean_seconds": statistics.mean(r["assembler_seconds"] for r in group_rows),
            "remap_median_seconds": statistics.median(r["remap_seconds"] for r in group_rows),
            "remap_total_seconds": remap_total,
            "ivanka_total_seconds": ivanka_total,
            "remap_fraction": remap_total / ivanka_total,
            "observed_runtime": signed_psi([r["delta"] for r in group_rows]),
            "zero_assembly_counterfactual": signed_psi(
                [r["zero_assembler_delta"] for r in group_rows]),
        }
    return {"formal_qualification": False,
            "counterfactual_assumption": "zero native assembler seconds, downstream timings fixed",
            "groups": result}



def live_report(events, expected_samples):
    """Read-only diagnostic of one running invocation; never formal qualification."""
    if not events or len({e.get("invocation") for e in events}) != 1:
        raise ValueError("Live records must have one nonempty invocation")
    invocation = events[0].get("invocation")
    if not isinstance(invocation, str) or not invocation:
        raise ValueError("Missing invocation identity")
    if any(e.get("status") not in ("started", "finished") for e in events):
        raise ValueError("Unexpected live record status")
    started = [e for e in events if e["status"] == "started"]
    finished = [e for e in events if e["status"] == "finished"]
    names = [e.get("sample") for e in started]
    done = [e.get("sample") for e in finished]
    if len(started) != expected_samples or len(set(names)) != expected_samples:
        raise ValueError("Live invocation must start exactly the expected unique samples")
    if any(not isinstance(n, str) or not n for n in names):
        raise ValueError("Missing started sample identity")
    if len(set(done)) != len(done) or not set(done).issubset(names):
        raise ValueError("Duplicate or unknown finished sample")
    valid = [e for e in finished if e.get("failed") is False]
    failed = [e.get("sample") for e in finished if e.get("failed") is not False]
    if valid:
        for arm in ("iva", "ivanka"):
            if {e[arm].get("timing_origin") for e in valid} != {
                    "micall_in_container_monotonic_v1"}:
                raise ValueError("Mixed or non-authentic internal timing origins")
            image_ids = {e[arm].get("image_id") for e in valid}
            if len(image_ids) != 1 or not next(iter(image_ids)):
                raise ValueError("Missing or mixed image IDs in live diagnostic")
        rows = cohort(valid, len(valid))
        report = summarize(rows)
        report["worst_runtime_regressions"] = sorted(
            ({"sample": r["sample"], "runtime_delta_seconds": r["delta"],
              "assembler_seconds": r["assembler_seconds"],
              "remap_seconds": r["remap_seconds"]} for r in rows),
            key=lambda r: r["runtime_delta_seconds"])[:10]
    else:
        report = {"formal_qualification": False, "groups": {},
                  "worst_runtime_regressions": []}
    report.update(partial_diagnostic=True, invocation=invocation,
                  started=len(started), finished=len(finished),
                  valid=len(valid), failed_samples=sorted(failed),
                  remaining=expected_samples-len(finished),
                  alignment_floor_failures=sum(
                      e.get("best_contig_acceptance", {}).get("pass") is not True
                      for e in valid))
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--expected-samples", type=int, default=198)
    parser.add_argument("--live", action="store_true",
                        help="Analyze one in-progress invocation; never formal qualification")
    args = parser.parse_args()
    if args.expected_samples < 1:
        parser.error("--expected-samples must be positive")
    lines = [json.loads(s) for s in args.jsonl.read_text().splitlines() if s.strip()]
    report = (live_report(lines, args.expected_samples) if args.live else
              summarize(cohort(lines, args.expected_samples)))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
