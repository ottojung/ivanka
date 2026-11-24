"""Neutral ingestion of immutable PX cohort case receipts into /bench/.

Only terminal, source-bound receipts are admitted. Genuine scores, diagnostic
metrics, failures and observed peak RAM are merged into the cohort-owned
evidence; original seven measurements are never rewritten. Launcher wall time
is never presented as the in-container runtime metric.
"""
import argparse
import hashlib
import json
import math
import re
import tempfile
import shutil
from pathlib import Path

from .current_inputs import PANEL, PHYSICAL_MANIFEST
from .public_metrics import CATALOG
from .public_view import (EVIDENCE_SCHEMA, assert_clean_object,
                          merge_evidence, scrub)

CASE_SCHEMA = "ivanka.px.case.receipt.v1"
INDEX_SCHEMA = "ivanka.px.case.receipt-index.v1"
RESULT_SCHEMA = "ivanka.exploratory.per-sample.v1"
RESOURCE_SCHEMA = "ivanka.px.arm-resource.v1"
DIAGNOSTIC_SCHEMA = "ivanka.px.diagnostics.v3"
SCORE_METHOD = "best_final_max_contig_local_alignment_over_reference_panel"
ALIAS = re.compile(r"^PX-([RH])([0-9]{3})$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")


def _load(path):
    return json.loads(Path(path).read_bytes())


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_index(root):
    index = _load(root / "receipts" / "index.json")
    if (index.get("schema") != INDEX_SCHEMA
            or not isinstance(index.get("entries"), dict)
            or not index["entries"]):
        raise ValueError("invalid PX case receipt index")
    for name, digest in index["entries"].items():
        if not SHA64.fullmatch(digest):
            raise ValueError("invalid PX receipt digest")
        path = root / "receipts" / (name + ".json")
        if not path.is_file() or _digest(path) != digest:
            raise ValueError("PX case receipt differs from index: " + name)
    return index


def _canonical_alias(receipt, real_data):
    """Bind a public alias to the original read-pair bytes of a cohort case."""
    match = ALIAS.fullmatch(receipt.get("alias", ""))
    if not match or receipt.get("cohort") != "physical":
        return None
    alias = match.group(1) + match.group(2)
    from .real_public import sample_aliases
    samples = sample_aliases(Path(real_data))
    sample = next((name for name, public in samples.items()
                   if public == alias), None)
    if sample is None:
        raise ValueError("PX alias is not a canonical cohort case")
    folder = Path(real_data) / "samples" / sample
    inputs = receipt.get("input_sha256", {})
    for mate in ("R1", "R2"):
        path = next(folder.glob("*_" + mate + "_001.fastq.gz"), None)
        if (path is None or not SHA64.fullmatch(inputs.get(mate, ""))
                or _digest(path) != inputs[mate]):
            raise ValueError("PX input hash differs from original source pair")
    return ("real", alias)


def _metrics(diagnostics):
    values = scrub(diagnostics.get("metrics", {}).get(
        "canonical_micall", {}).get("values", {}))
    result = {}
    for key, value in values.items():
        name = "nuc_soft_clips_count" if key == "soft_clips_count" else key
        if name in CATALOG and type(value) in (int, float) and math.isfinite(
                value) and value >= 0:
            result[name] = value
    return result


def _case(root, name, receipt, assembler, real_data):
    """Validate one receipt and its post-hoc result/resource/diagnostic files."""
    tool = receipt.get("tool_id")
    if tool != assembler["id"]:
        raise ValueError("PX case receipt tool mismatch")
    provenance = assembler.get("provenance", assembler)
    for key in ("source_commit", "adapter_commit", "image_sha256"):
        if receipt.get(key) != provenance.get(key):
            raise ValueError("PX case provenance differs from registry")
    if receipt.get("schema") != CASE_SCHEMA or receipt.get("terminal") is not True:
        raise ValueError("PX case is not a terminal receipt")
    bound = _canonical_alias(receipt, real_data)
    if bound is None:
        return None
    cohort, alias = bound
    stem = name
    files = (root / "results" / (stem + "-results.json"),
             root / "results" / (stem + "-resource.json"),
             root / "diagnostics" / (stem + ".json"))
    if not all(path.is_file() for path in files):
        return None  # no receipt-bound post-hoc evidence to publish
    result, resource, diagnostics = (_load(path) for path in files)
    if (result.get("schema") != RESULT_SCHEMA
            or result.get("tool_id") != tool
            or result.get("cohort") != receipt["cohort"]
            or resource.get("schema") != RESOURCE_SCHEMA
            or resource.get("tool_id") != tool
            or diagnostics.get("schema") != DIAGNOSTIC_SCHEMA
            or diagnostics.get("tool_id") != tool):
        raise ValueError("PX post-hoc files do not match terminal receipt")
    if (diagnostics.get("output_sha256") != receipt.get("output_sha256")
            or diagnostics.get("runner_receipt_sha256") != receipt[
                "runner_receipt_sha256"]):
        raise ValueError("PX diagnostic evidence is not receipt-bound")
    row = result["samples"][0]
    if (row.get("alias") != receipt["alias"] or row.get("outcome") != receipt["outcome"]
            or row.get("method") != SCORE_METHOD
            or row.get("reference_panel_sha256") != PANEL):
        raise ValueError("PX score method or alias mismatched")
    failure = receipt.get("failure_reason")
    if receipt["outcome"] == "success":
        score = row.get("score")
        if type(score) not in (int, float) or not math.isfinite(score) or score < 0:
            raise ValueError("PX success has no genuine score")
    else:
        score = None
    ram = row.get("peak_ram_observed_mib")
    if (type(ram) not in (int, float) or not math.isfinite(ram)
            or ram <= 0 or resource.get("peak_ram_observed_mib") != ram
            or resource.get("peak_rss_bytes") != receipt.get("peak_rss_bytes")):
        raise ValueError("PX observed peak RAM is not reconciled")
    coverage = diagnostics["metrics"].get("exact_coverage", {})
    metrics = _metrics(diagnostics)
    # Observed peak RAM is a genuine published diagnostic as well as receipt
    # evidence; keep both representations in agreement.
    metrics["peak_ram_observed_mib"] = ram
    return {
        "cohort": cohort, "canonical_alias": alias, "outcome": receipt["outcome"],
        "canonical_manifest_sha256": PHYSICAL_MANIFEST,
        "failure_reason": failure, "score": score,
        "score_origin": "micall_final_max_reference_panel_v1",
        "reference_panel_sha256": PANEL, "method": SCORE_METHOD,
        "scorer_source_sha256": result.get("scorer_source_sha256"),
        "launcher_seconds": receipt.get("seconds"),
        "timing_origin": "guarded_launcher_total_wall_with_podman_cleanup_v1",
        "peak_ram_observed_mib": ram, "peak_rss_bytes": receipt["peak_rss_bytes"],
        "input_sha256": receipt["input_sha256"],
        "output_sha256": receipt["output_sha256"],
        "source_commit": provenance.get("source_commit"),
        "adapter_commit": provenance.get("adapter_commit"),
        "image_sha256": provenance.get("image_sha256"),
        "diagnostics": metrics,
        "exact_coverage": {
            "status": coverage.get("status", "unavailable"),
            "unavailable_reason": coverage.get("unavailable_reason"),
        },
        "binding_receipts": 5,
    }


def refresh_registry_provenance(evidence, registry_path, handoff_path):
    """Adopt a verified registry activation without inventing measurements."""
    from . import exploratory_policy
    registry = _load(registry_path)
    handoff = _load(handoff_path)
    if (registry.get("schema") != "ivanka.exploratory.assemblers.v1"
            or handoff.get("schema") != "ivanka.px.supervisor.handoff.v1"
            or not SHA64.fullmatch(handoff.get("image_receipt_sha256", ""))
            or not SHA64.fullmatch(handoff.get("pilot_receipt_sha256", ""))):
        raise ValueError("registry activation or supervisor handoff unverified")
    branches = registry.get("adapter_branch_commits", {})
    assemblers = {item["id"]: item for item in evidence["assemblers"]}
    adopted = []
    for raw in registry["candidates"]:
        item = dict(raw, adapter_commit=branches.get(raw["id"]))
        target = assemblers.get(item["id"])
        if target is None or item["id"] != handoff["tool_id"]:
            continue
        pilot = _load(item["pilot_evidence"]["path"])
        adapter = branches.get(item["id"])
        if (not adapter or adapter != pilot.get("adapter_commit")
                or item.get("image_sha256") != handoff["image_sha256"]
                or item.get("pilot_evidence", {}).get("sha256")
                != handoff["pilot_receipt_sha256"]):
            raise ValueError("handoff does not bind this assembler activation")
        if not exploratory_policy.verified_receipt(
                item, item.get("image_evidence"), "image"):
            raise ValueError("activated image lacks a source-bound receipt")
        if not exploratory_policy.verified_receipt(
                item, item.get("pilot_evidence"), "pilot"):
            raise ValueError("activated pilot lacks a paired-FASTQ receipt")
        from .adapter_branch_refs import adapter_provenance
        target["adapter_commit"] = adapter
        target["image_sha256"] = item["image_sha256"]
        target.update(adapter_provenance(item["id"], adapter))
        target["pilot"] = {
            "image_receipt_sha256": handoff["image_receipt_sha256"],
            "pilot_receipt_sha256": handoff["pilot_receipt_sha256"],
            "outcomes": {cohort: pilot.get(cohort, {}).get("status")
                         for cohort in ("physical", "synthetic")},
        }
        adopted.append(item["id"])
    return adopted


def ingest(report, evidence, root, real_data, registry_path=None,
           handoff_path=None):
    """Return updated evidence and report with genuine cohort receipts joined."""
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("unsupported assembler evidence schema")
    root = Path(root)
    index = _read_index(root)
    result = scrub(json.loads(json.dumps(evidence)))
    added = []
    if registry_path and handoff_path:
        for tool in refresh_registry_provenance(
                result, registry_path, handoff_path):
            added.append(("registry", tool, "activation"))
    assemblers = {item["id"]: item for item in result["assemblers"]}
    # Older evidence rows carried observed peak RAM only as receipt metadata.
    # Normalize them into the per-arm diagnostic map before publication so
    # published diagnostics and their attested case evidence agree.
    for item in assemblers.values():
        for case in item.get("cases", []):
            ram = case.get("peak_ram_observed_mib")
            if isinstance(ram, (int, float)):
                case.setdefault("diagnostics", {})["peak_ram_observed_mib"] = ram
    for name in sorted(index["entries"]):
        receipt = _load(root / "receipts" / (name + ".json"))
        tool = receipt.get("tool_id")
        if tool not in assemblers:
            continue
        case = _case(root, name, receipt, assemblers[tool], real_data)
        if case is None:
            continue
        cases = assemblers[tool].setdefault("cases", [])
        if any(item.get("cohort") == case["cohort"] and
               item.get("canonical_alias") == case["canonical_alias"]
               for item in cases):
            continue
        cases.append(case)
        added.append((tool, case["cohort"], case["canonical_alias"]))
    assert_clean_object(result)
    merged, joined = merge_evidence(report, result)
    return result, merged, added, joined


def publish(site, root, real_data, registry_path=None, handoff_path=None):
    """Atomically update evidence and runs.json after full-site validation."""
    from .site_build import validate_public_site
    site = Path(site)
    evidence = _load(site / "data/assembler-evidence.json")
    report = _load(site / "data/runs.json")
    updated, merged, added, joined = ingest(
        report, evidence, root, real_data, registry_path, handoff_path)
    with tempfile.TemporaryDirectory(prefix="px-ingest-") as scratch:
        staged = Path(scratch) / "bench"
        shutil.copytree(site, staged)
        (staged / "data/assembler-evidence.json").write_text(
            json.dumps(updated, sort_keys=True,
                       separators=(",", ":")) + "\n")
        (staged / "data/runs.json").write_text(
            json.dumps(merged, sort_keys=True, separators=(",", ":")) + "\n")
        validate_public_site(staged)
        for name in ("assembler-evidence.json", "runs.json"):
            pending = site / "data" / (name + ".pending")
            pending.write_bytes((staged / "data" / name).read_bytes())
            pending.replace(site / "data" / name)
    return updated, merged, added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--real-data", type=Path, required=True)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--handoff", type=Path)
    args = parser.parse_args()
    _, _, added = publish(args.site, args.root, args.real_data,
                          args.registry, args.handoff)
    print("PX_COHORT_INGESTED", len(added), added)


if __name__ == "__main__":
    main()
