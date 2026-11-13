"""Verified, privacy-safe HXB2 MiCall benchmark *incomplete* run previews."""
from collections import defaultdict
import argparse
import hashlib
import json
import math
from pathlib import Path

from benchmarks.expanded.adapters import ASSEMBLERS
from benchmarks.expanded.micall_checkpoint import existing_case, identity
from benchmarks.expanded.micall_dominant import SCORE_ORIGIN
from benchmarks.expanded.micall_synthetic_constants import TIMING_ORIGIN
from .publication import SCHEMA
from .public_dominance import enrich

COHORT_SHA = "964fff8226beef4787226a5542dc2667fff0102bea0b4f4694686b11af1f7f5a"
COHORT_FILE = (Path(__file__).resolve().parents[1] / "expanded/references"
               / "hxb2-400-v4-micall-high-depth-cohort.json")
PROOF_FILE = (Path(__file__).resolve().parents[1] / "expanded/references"
              / "hxb2-400-v4-micall-high-depth-validation.json")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned_truth():
    if sha(COHORT_FILE) != COHORT_SHA:
        raise ValueError("HXB2 v4 cohort differs from committed proof")
    cohort = json.loads(COHORT_FILE.read_text())
    proof = json.loads(PROOF_FILE.read_text())
    if (cohort.get("samples") != 400 or len(cohort["cases"]) != 400
            or proof.get("valid") is not True
            or proof.get("samples_validated") != 400
            or proof.get("cohort_sha256") != COHORT_SHA):
        raise ValueError("missing independently verified HXB2 truth ancestry")
    return cohort, proof


def checked_run(directory, source_root=None):
    """All records must be actual completed MiCall cases, never partial arms."""
    root = Path(directory)
    manifest_file = root / "run_manifest.json"
    manifest = json.loads(manifest_file.read_text())
    cohort, proof = pinned_truth()
    if (manifest.get("schema") != "ivanka.expanded.micall_synthetic.v2"
            or manifest.get("expected") != 400 or manifest.get("limit") is not None
            or manifest.get("source_truth") != proof
            or manifest.get("status") != "INCOMPLETE"
            or manifest.get("qualified") is not False
            or manifest.get("score") != SCORE_ORIGIN
            or manifest.get("timer") != TIMING_ORIGIN):
        raise ValueError("not an authentic full-cohort HXB2 MiCall run")
    sources = manifest.get("benchmark_sources_sha256", {})
    base = (Path(source_root) if source_root else Path(__file__).resolve().parents[2]) / "benchmarks/expanded"
    required_sources = ("micall_synthetic.py", "micall_checkpoint.py",
                        "micall_synthetic_constants.py", "micall_lock.py",
                        "micall_dominant.py", "score.py", "adapters.py",
                        "hxb2_cohort.py")
    if (set(sources) != set(required_sources)
            or any(sha(base / name) != sources[name]
                   for name in required_sources)):
        raise ValueError("benchmark source SHA attestation mismatch")
    # New instrumented manifests bind optional diagnostic source to its
    # archived metrics; old historical snapshots lack this instrument.
    extra = manifest.get("diagnostic_sources_sha256")
    if extra is not None:
        instrument_root = (Path(source_root) if source_root else Path(__file__).resolve().parents[2]) / "benchmarks"
        expected = {"sam_metrics.py": instrument_root / "assembler_bench/sam_metrics.py",
                    "diagnostic_metrics.py": instrument_root / "diagnostic_metrics.py"}
        if (set(extra) != set(expected)
                or any(sha(path) != extra[name]
                       for name, path in expected.items())):
            raise ValueError("MiCall diagnostic source attestation mismatch")
    images = manifest.get("images")
    if (not isinstance(images, dict) or set(images) != set(ASSEMBLERS)
            or any(type(x) is not str or len(x) != 64
                   or any(c not in "0123456789abcdef" for c in x)
                   for x in images.values())):
        raise ValueError("missing immutable seven-tool image identities")
    identities = {row["id"]: row for row in cohort["cases"]}
    results = root / "results.jsonl"
    entries = [json.loads(line) for line in results.read_text().splitlines()
               if line.strip()]
    if len(entries) > 400 or len({r.get("id") for r in entries}) != len(entries):
        raise ValueError("duplicate or surplus benchmark rows")
    checked = []
    for row in entries:
        identifier = row.get("id")
        if identifier not in identities:
            raise ValueError("case not in pinned HXB2 cohort")
        source = identities[identifier]
        fields = identity(identifier, {
            "family": identifier.rsplit("-s", 1)[0],
            "sha256": source["sha256"],
        }, proof)
        verified = existing_case(root / identifier, fields, images)
        if verified != row:
            raise ValueError("unverified checkpoint row")
        checked.append(row)
    return manifest, checked, sha(results)


def preview(directory, source_root=None):
    manifest, records, result_hash = checked_run(directory, source_root)
    return format_preview(manifest, records, result_hash,
                          sha(Path(directory) / "run_manifest.json"))


def format_preview(manifest, records, result_hash, source_manifest_sha256):
    """Convert independently verified completed cases to anonymous public rows."""
    tools = list(ASSEMBLERS)
    families = defaultdict(list)
    samples = []
    failed_arms = 0
    for index, row in enumerate(sorted(records, key=lambda r: r["id"]), 1):
        values = row["results"]
        failed = [name for name in tools if values[name]["status"] != "success"]
        failed_arms += len(failed)
        sample = {
            "alias": f"H{index:03d}", "family": row["family"],
            "score": {}, "seconds": {}, "failures": failed,
            "outcome": "failure" if failed else "success",
            "floor_ok": None,
        }
        for name in tools:
            part = values[name]
            if part["status"] == "success":
                number = part.get("score")
                seconds = part.get("seconds")
                if (type(number) not in (int, float) or not 0 <= number <= 1
                        or type(seconds) not in (int, float)
                        or not math.isfinite(seconds)
                        or not 0 < seconds <= 1800):
                    raise ValueError("invalid scientific score or MiCall duration")
                sample["score"][name] = number
                sample["seconds"][name] = seconds
            else:
                sample["score"][name] = None
                sample["seconds"][name] = None
        if not failed:
            highest = max(sample["score"][tool] for tool in tools
                          if tool != "ivanka")
            sample["floor_ok"] = sample["score"]["ivanka"] >= 0.9 * highest
        samples.append(sample)
        families[row["family"]].append(sample)
    summaries = []
    for name, rows in sorted(families.items()):
        mean = {}
        mean_times = {}
        failures = {}
        for tool in tools:
            selected = [x["score"][tool] for x in rows
                        if x["score"][tool] is not None]
            times = [x["seconds"][tool] for x in rows
                     if x["seconds"][tool] is not None]
            mean[tool] = sum(selected)/len(selected) if selected else None
            mean_times[tool] = sum(times)/len(times) if times else None
            failures[tool] = len(rows)-len(selected)
        summaries.append({
            "family": name, "sample_count": len(rows),
            "scores": mean, "seconds": mean_times, "failures": failures,
        })
    source = manifest["benchmark_sources_sha256"]
    return {
        "schema": SCHEMA, "id": f"hxb2-v4-micall-cases-{len(samples):03d}",
        "title": "HXB2 v4 · seven-way integrated MiCall (in progress)",
        "date": "2026-11-12", "cohort": "synthetic",
        "status": "incomplete", "expanded_status": "incomplete",
        "eligible_for_expanded": False, "hxb2_truth_verified": True,
        "status_reason": (f"{len(samples)}/400 completed HXB2-derived cases; "
                          f"{failed_arms} failed arms. This partial run does "
                          "NOT meet the mandatory 598-case seven-way gate."),
        "source_commit": "5510121fbf322ca496a3a89af3e3be7c8546452b",
        "sample_count": len(samples), "expected_sample_count": 400,
        "tools": tools, "samples": samples, "families": summaries,
        "images": manifest["images"], "psi": {},
        "cohort_manifest_sha256": COHORT_SHA,
        "reference_manifest_sha256": manifest["source_truth"][
            "reference_manifest_sha256"],
        "source_manifest_sha256": source_manifest_sha256,
        "diagnostic_sha256": result_hash, "runner_source_sha256": source,
        "timing_origin": TIMING_ORIGIN, "score_origin": SCORE_ORIGIN,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--public-json", type=Path, required=True)
    args = parser.parse_args()
    report = preview(args.source)
    target = args.public_json
    if not target.is_file():
        raise ValueError("public run index must already exist")
    public = json.loads(target.read_text())
    if public.get("schema") != SCHEMA or any(
            run["id"] == report["id"] for run in public["runs"]):
        raise ValueError("duplicate/unsupported public benchmark snapshot")
    public["runs"].append(report)
    public = enrich(public)
    temporary = target.with_suffix(".json.pending")
    with temporary.open("x") as stream:
        json.dump(public, stream, sort_keys=True, indent=2)
        stream.write("\n")
    temporary.replace(target)
    print("PUBLIC_HXB2_INCOMPLETE_PREVIEW", len(report["samples"]),
          report["status"], sha(target))


if __name__ == "__main__":
    main()
