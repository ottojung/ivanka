"""Fail-closed public publisher for the ten NONQUALIFYING PX assemblers.

The private registry is the authority for source pins and receipt evidence.
Only measurements bound to a content-hashed image/pilot/benchmark receipt are
exported. An unbuilt or unrun candidate keeps an empty sample list and no
quality, runtime or dominance numbers; the public site states that explicitly.
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import tempfile
from pathlib import Path

from . import exploratory_policy

SCHEMA = "ivanka.assembler-bench.exploratory-candidates.v1"
DATA_FILE = "data/exploratory-candidates.json"
RESULT_SCHEMA = "ivanka.exploratory.per-sample.v1"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / "benchmarks/assembler_bench/exploratory_candidates.json"
DEFAULT_SITE = ROOT / "site/bench"
COHORTS = ("physical", "synthetic")
ALIAS = re.compile(r"^PX-([RH])([0-9]{3})\Z")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")
PRIVATE = re.compile(r"/workspace/|/home/|\.fastq|patient[-_]?id", re.IGNORECASE)
FAILURES = frozenset(("error", "timeout", "no_contigs", "no_final_max"))
STATUSES = ("source-pinned", "image-pinned", "pilot", "benchmarked")
RESULT_STATUSES = ("no-image", "image-only", "no-per-sample-results",
                   "verified-pilot", "verified-benchmark")


def _verified_label(status):
    return "verified-pilot" if status == "pilot" else "verified-benchmark"
MAX_SAMPLES = 662
CANDIDATE_FIELDS = {"id", "name", "source_repo", "source_commit",
                   "adapter_commit", "status", "qualifying", "image_sha256",
                   "source_license", "license_path", "replaces_blocked",
                   "rationale", "evidence", "results_status", "samples",
                   "results"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _text(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _receipt_evidence(item):
    """A digest is never promoted without a source-bound local receipt."""
    return {
        "image_receipt_verified": exploratory_policy.verified_receipt(
            item, item.get("image_evidence"), "image"),
        "pilot_receipt_verified": exploratory_policy.verified_receipt(
            item, item.get("pilot_evidence"), "pilot"),
        "benchmark_receipt_verified": exploratory_policy.verified_receipt(
            item, item.get("benchmark_evidence"), "benchmark"),
    }


def _check_evidence(item, evidence):
    """Promotion without the matching authenticated receipt is rejected."""
    status = item["status"]
    if status == "source-pinned":
        if (item["image_sha256"] is not None
                or any(evidence.values())
                or any(key in item for key in ("image_evidence",
                                               "pilot_evidence",
                                               "benchmark_evidence"))):
            raise ValueError("source-pinned explorer claims runtime evidence")
        return
    if not SHA64.fullmatch(item["image_sha256"] or ""):
        raise ValueError("promoted explorer has no immutable image digest")
    if not evidence["image_receipt_verified"]:
        raise ValueError("promoted explorer lacks a source-bound image receipt")
    if status in ("pilot", "benchmarked") and not evidence["pilot_receipt_verified"]:
        raise ValueError("pilot status without a genuine paired-FASTQ receipt")
    if status == "benchmarked" and not evidence["benchmark_receipt_verified"]:
        raise ValueError("benchmark status without a completed cohort receipt")


def _validate_samples(samples, expected, cohort):
    """Per-case rows carry only public aliases and finite numeric readings."""
    if (not isinstance(samples, list) or not 1 <= len(samples) <= expected
            or expected > MAX_SAMPLES):
        raise ValueError("invalid per-sample count")
    prefix = "R" if cohort == "physical" else "H"
    seen = set()
    rows = []
    for sample in samples:
        if not isinstance(sample, dict):
            raise TypeError("invalid per-sample row")
        alias = sample.get("alias")
        if (not isinstance(alias, str) or not ALIAS.fullmatch(alias)
                or alias[3] != prefix or alias in seen):
            raise ValueError("invalid or duplicated public case alias")
        seen.add(alias)
        outcome = sample.get("outcome")
        row = {"alias": alias, "outcome": outcome}
        if outcome == "success":
            score, seconds = sample.get("score"), sample.get("seconds")
            if (type(score) not in (int, float) or not math.isfinite(score)
                    or score < 0 or type(seconds) not in (int, float)
                    or not math.isfinite(seconds) or seconds <= 0):
                raise ValueError("unverified success measurement")
            row.update(score=score, seconds=seconds)
        elif outcome == "failure":
            if (sample.get("score") is not None
                    or sample.get("seconds") is not None
                    or sample.get("failure_reason") not in FAILURES):
                raise ValueError("failed arm cannot claim a measurement")
            row["failure_reason"] = sample["failure_reason"]
        else:
            raise ValueError("unknown per-sample outcome")
        if PRIVATE.search(_text(row)):
            raise ValueError("private identifier in per-sample row")
        rows.append(row)
    return rows


def _verified_results(path, item, status):
    """Bind a results file to the exact receipt that attests the run."""
    source = Path(path)
    data = json.loads(source.read_text())
    if (data.get("schema") != RESULT_SCHEMA
            or data.get("tool_id") != item["id"]
            or data.get("status") != status
            or data.get("source_commit") != item["source_commit"]
            or data.get("adapter_commit") != item["adapter_commit"]
            or data.get("image_sha256") != item["image_sha256"]
            or data.get("cohort") not in COHORTS):
        raise ValueError("per-sample file does not match the pinned explorer")
    expected = data.get("expected_sample_count")
    if type(expected) is not int or not 1 <= expected <= MAX_SAMPLES:
        raise ValueError("invalid expected per-sample count")
    evidence = (item.get("pilot_evidence") if status == "pilot"
                else item.get("benchmark_evidence"))
    if not isinstance(evidence, dict):
        raise TypeError("per-sample results have no run receipt")
    receipt = Path(evidence["path"]).resolve(strict=True)
    proof = json.loads(receipt.read_bytes())
    attested = proof.get("per_sample_results_sha256")
    if (not isinstance(attested, dict)
            or attested.get(data["cohort"]) != digest(source)):
        raise ValueError("per-sample results differ from attested receipt")
    if PRIVATE.search(source.read_text()):
        raise ValueError("private identifier in per-sample results")
    return {"cohort": data["cohort"], "expected": expected,
            "results_sha256": digest(source), "evidence_sha256": digest(receipt),
            "samples": _validate_samples(data.get("samples"), expected,
                                         data["cohort"])}


def _blocked(registry):
    rows = []
    for item in registry.get("blocked_original_candidates", []):
        reasons = item.get("blocked_reasons")
        if not isinstance(reasons, list) or not reasons:
            raise ValueError("lost source-only blocker evidence")
        row = {"id": item["id"], "name": item["name"],
               "source_commit": item["source_commit"],
               "status": item["status"], "blocked_reasons": reasons,
               "replacement": item["replacement"]}
        if PRIVATE.search(_text(row)):
            raise ValueError("private identifier in blocker evidence")
        rows.append(row)
    return rows


def build(registry_path=DEFAULT_REGISTRY, results=None):
    """Publish the registry's honest state, never an assumed future result."""
    registry = exploratory_policy.checked(registry_path)
    results = results or {}
    if set(results) - exploratory_policy.EXPERIMENTAL:
        raise ValueError("per-sample results for an unknown explorer")
    candidates = []
    for raw in registry["candidates"]:
        item = dict(raw, adapter_commit=registry["adapter_branch_commits"][raw["id"]])
        evidence = _receipt_evidence(item)
        _check_evidence(item, evidence)
        entry = {
            "id": item["id"], "name": item["name"],
            "source_repo": item["source_repo"],
            "source_commit": item["source_commit"],
            "adapter_commit": item["adapter_commit"],
            "status": item["status"], "qualifying": False,
            "image_sha256": item["image_sha256"],
            "source_license": item.get("source_license"),
            "license_path": item.get("license_path"),
            "replaces_blocked": item.get("replaces_blocked"),
            "rationale": item.get("rationale"),
            "evidence": evidence,
            "results_status": {
                "source-pinned": "no-image",
                "image-pinned": "image-only",
                "pilot": "no-per-sample-results",
                "benchmarked": "no-per-sample-results"}[item["status"]],
            "samples": [],
        }
        for path in results.get(item["id"], []):
            verified = _verified_results(path, item, item["status"])
            if "results" not in entry:
                entry["results"] = {"evidence_sha256": verified["evidence_sha256"],
                                    "results_sha256": {}, "cohorts": [],
                                    "expected_sample_count": {}}
                entry["results_status"] = _verified_label(item["status"])
            result = entry["results"]
            cohort = verified["cohort"]
            if cohort in result["cohorts"]:
                raise ValueError("duplicate per-sample cohort for one explorer")
            result["cohorts"].append(cohort)
            result["results_sha256"][cohort] = verified["results_sha256"]
            result["expected_sample_count"][cohort] = verified["expected"]
            entry["samples"].extend(verified["samples"])
        candidates.append(entry)
    policy = registry["policy"]
    return {
        "schema": SCHEMA,
        "title": "Experimental PX assemblers · not qualifying",
        "qualifying": False,
        "status": ("source-pinned-no-results"
                   if all(c["status"] == "source-pinned" for c in candidates)
                   else "receipted-nonqualifying-evidence"),
        "note": ("Ten experimental MiCall assemblers. Source pins and receipts "
                 "are shown as they are; unbuilt images and unrun benchmarks "
                 "have no scores, runtimes or Ψ comparisons."),
        "registry_sha256": digest(registry_path),
        "frozen_seven_manifest_sha256": policy["frozen_seven_manifest_sha256"],
        "baseline_assemblers": list(registry["baseline_assemblers"]),
        "resource_policy": {
            "max_container_wall_seconds": policy["max_container_wall_seconds"],
            "max_sampled_process_tree_rss_bytes":
                policy["max_sampled_process_tree_rss_bytes"],
            "max_concurrent_exploratory_workers":
                policy["max_concurrent_exploratory_workers"],
            "qualification_admission": policy["qualification_admission"],
        },
        "dominance": {"status": "not-applicable",
                      "reason": ("Nonqualifying explorers never enter the "
                                 "seven-way qualification Ψ matrices.")},
        "candidates": candidates,
        "blocked_original_candidates": _blocked(registry),
    }


def validate(snapshot):
    """Recheck the exported snapshot without needing private receipt files."""
    if (snapshot.get("schema") != SCHEMA
            or snapshot.get("qualifying") is not False
            or snapshot.get("status") not in ("source-pinned-no-results",
                                              "receipted-nonqualifying-evidence")
            or set(snapshot.get("baseline_assemblers", []))
            != exploratory_policy.ORIGINAL
            or not SHA64.fullmatch(snapshot.get("registry_sha256", ""))
            or not SHA64.fullmatch(
                snapshot.get("frozen_seven_manifest_sha256", ""))
            or snapshot.get("dominance", {}).get("status") != "not-applicable"
            or "psi" in snapshot):
        raise ValueError("invalid nonqualifying public snapshot")
    candidates = snapshot.get("candidates")
    if (not isinstance(candidates, list)
            or {c.get("id") for c in candidates}
            != exploratory_policy.EXPERIMENTAL
            or len(candidates) != 10):
        raise ValueError("exploratory public roster drift")
    for item in candidates:
        if (not CANDIDATE_FIELDS.issuperset(item)
                or item.get("qualifying") is not False
                or item.get("status") not in STATUSES
                or item.get("results_status") not in RESULT_STATUSES
                or not isinstance(item.get("evidence"), dict)
                or set(item["evidence"]) != {
                    "image_receipt_verified", "pilot_receipt_verified",
                    "benchmark_receipt_verified"}):
            raise ValueError("invalid public explorer identity")
        if not re.fullmatch("[a-f0-9]{40}", item.get("source_commit", "")):
            raise ValueError("invalid pinned source hash")
        if not re.fullmatch("[a-f0-9]{40}", item.get("adapter_commit", "")):
            raise ValueError("invalid pinned adapter hash")
        evidence = item["evidence"]
        if item["status"] == "source-pinned":
            if (item["image_sha256"] is not None
                    or item["results_status"] != "no-image"
                    or any(evidence.values()) or "results" in item):
                raise ValueError("unbuilt explorer shown with metrics")
        else:
            if (not SHA64.fullmatch(item["image_sha256"] or "")
                    or not evidence["image_receipt_verified"]
                    or item["results_status"] == "no-image"):
                raise ValueError("promoted explorer is missing image evidence")
            if item["status"] in ("pilot", "benchmarked") and not (
                    evidence["pilot_receipt_verified"]):
                raise ValueError("pilot status lacks authenticated proof")
            if item["status"] == "benchmarked" and not (
                    evidence["benchmark_receipt_verified"]):
                raise ValueError("benchmark status lacks authenticated proof")
        samples = item.get("samples")
        if not isinstance(samples, list):
            raise TypeError("invalid public sample list")
        verified = item["results_status"].startswith("verified-")
        if not verified:
            if samples or "results" in item:
                raise ValueError("unrun explorer has fabricated per-case data")
            if item["results_status"] == "image-only" and (
                    item["status"] != "image-pinned"):
                raise ValueError("image-only status on another promotion stage")
            if item["results_status"] == "no-per-sample-results" and (
                    item["status"] == "image-pinned"):
                raise ValueError("image-pinned explorer claims a later stage")
            continue
        if (item["results_status"] != _verified_label(item["status"])
                or not samples):
            raise ValueError("verified results inconsistent with explorer stage")
        result = item.get("results")
        if (not isinstance(result, dict)
                or not SHA64.fullmatch(result.get("evidence_sha256", ""))
                or set(result) != {"evidence_sha256", "results_sha256",
                                   "cohorts", "expected_sample_count"}
                or not result["cohorts"]
                or set(result["cohorts"]) - set(COHORTS)
                or set(result["results_sha256"]) != set(result["cohorts"])
                or set(result["expected_sample_count"]) != set(result["cohorts"])):
            raise ValueError("unverifiable per-sample result provenance")
        counted = 0
        for cohort in result["cohorts"]:
            if (not SHA64.fullmatch(result["results_sha256"][cohort])
                    or type(result["expected_sample_count"][cohort]) is not int
                    or not 1 <= result["expected_sample_count"][cohort] <= MAX_SAMPLES):
                raise ValueError("invalid attested per-sample cohort")
            prefix = "R" if cohort == "physical" else "H"
            rows = [sample for sample in samples
                    if sample["alias"][3] == prefix]
            counted += len(_validate_samples(
                rows, result["expected_sample_count"][cohort], cohort))
        if counted != len(samples):
            raise ValueError("per-case rows outside attested cohorts")
    blocked = snapshot.get("blocked_original_candidates")
    if (not isinstance(blocked, list)
            or {row.get("id") for row in blocked} != {"vicuna", "pehaplo"}):
        raise ValueError("historical source blockers were erased")
    if PRIVATE.search(_text(snapshot)):
        raise ValueError("private identifier in public explorer snapshot")
    return len(candidates)


def publish(site=DEFAULT_SITE, registry_path=DEFAULT_REGISTRY, results=None):
    """Atomically replace only the explorer snapshot, after full-site checks."""
    target = Path(site) / DATA_FILE
    snapshot = build(registry_path, results)
    validate(snapshot)
    with tempfile.TemporaryDirectory(prefix="px-bench-site-") as scratch:
        staged = Path(scratch) / "bench"
        shutil.copytree(site, staged)
        output = staged / DATA_FILE
        output.write_text(_text(snapshot) + "\n")
        from .site_build import validate_public_site
        validate_public_site(staged)
        pending = target.with_name(target.name + ".pending")
        pending.write_bytes(output.read_bytes())
        pending.replace(target)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--results", action="append", default=[],
                        metavar="TOOL=FILE",
                        help="content-hashed per-sample file; repeat per cohort")
    parser.add_argument("--check", action="store_true",
                        help="only validate the committed public snapshot")
    args = parser.parse_args()
    if args.check:
        snapshot = json.loads((args.site / DATA_FILE).read_text())
        print("PX_EXPLORATORY_PUBLIC_VALIDATED", validate(snapshot))
        return
    mapping = {}
    for spec in args.results:
        tool, _, path = spec.partition("=")
        if not tool or not path:
            raise ValueError("expected TOOL=FILE for --results")
        mapping.setdefault(tool, []).append(path)
    snapshot = publish(args.site, args.registry, mapping)
    verified = sum(item["results_status"].startswith("verified-")
                   for item in snapshot["candidates"])
    print("PX_EXPLORATORY_PUBLISHED candidates=10 verified_results=" + str(verified))


if __name__ == "__main__":
    main()
