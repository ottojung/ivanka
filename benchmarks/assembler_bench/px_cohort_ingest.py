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
from .px_ram_semantics import (COMPARABLE_KEY, RAW_BYTES_KEY, classify,
                               normalize_case, observed_mib,
                               validate_publication)

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
    raw = receipt.get(RAW_BYTES_KEY)
    if (isinstance(raw, bool) or not isinstance(raw, (int, float))
            or not math.isfinite(raw) or raw < 0
            or resource.get(RAW_BYTES_KEY) != raw):
        raise ValueError("PX observed peak RAM is not reconciled")
    # A legacy receipt attests no sampling method. Only a versioned whole-
    # container attestation may promote the raw reading to a comparable peak.
    fields, ram_diagnostics = classify(raw, receipt, resource, row)
    for record in (resource, row):
        if (record.get(COMPARABLE_KEY) is not None
                and record[COMPARABLE_KEY] != observed_mib(raw)):
            raise ValueError("attested peak RAM differs from the raw receipt")
    coverage = diagnostics["metrics"].get("exact_coverage", {})
    metrics = _metrics(diagnostics)
    metrics.update(ram_diagnostics)
    fields.update({
        "cohort": cohort, "canonical_alias": alias,
        "outcome": receipt["outcome"],
        "canonical_manifest_sha256": PHYSICAL_MANIFEST,
        "failure_reason": failure, "score": score,
        "score_origin": "micall_final_max_reference_panel_v1",
        "reference_panel_sha256": PANEL, "method": SCORE_METHOD,
        "scorer_source_sha256": result.get("scorer_source_sha256"),
        "launcher_seconds": receipt.get("seconds"),
        "timing_origin": "guarded_launcher_total_wall_with_podman_cleanup_v1",
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
    })
    return fields


def assert_no_stale_scores(report, evidence, incoming=None):
    """Never replace provenance under a score that disagrees with a receipt.

    Aliases repeat across tools and cohorts, so the guard is keyed by tool and
    cohort as well as alias. Incoming receipts are checked before any
    provenance is adopted, not only the already published evidence rows.
    """
    published = {}
    for run in report.get("runs", []):
        cohort = run.get("cohort")
        for sample in run.get("samples", []):
            alias = sample["alias"]
            source = cohort
            if cohort == "combined":
                source = ("real" if alias.startswith("R-") else
                          "synthetic" if alias.startswith("S-") else None)
            alias = alias.split("-", 1)[-1]
            sources = [source] if source else ["real", "synthetic"]
            for tool, score in sample.get("score", {}).items():
                if score is not None:
                    for name in sources:
                        published[(tool, name, alias)] = score
    items = list(evidence.get("assemblers", [])) + list(incoming or [])
    for item in items:
        for case in item.get("cases", []):
            alias = case.get("canonical_alias")
            cohort = case.get("cohort")
            keys = [(item["id"], cohort, alias)] if cohort else [
                (item["id"], name, alias) for name in ("real", "synthetic")]
            for key in keys:
                if (key in published and case.get("score") is not None
                        and published[key] != case["score"]):
                    raise ValueError("preexisting sample score disagrees with evidence")


def refresh_registry_provenance(evidence, registry_path, handoff_dir):
    """Adopt every verified supervisor handoff in a registry activation.

    All activated tools are treated equally: a handoff is accepted only when
    its image/pilot receipt digests, adapter pin and image identity match the
    active registry entry and its source-bound receipts.
    """
    from . import exploratory_policy
    from .adapter_branch_refs import adapter_provenance
    registry = _load(registry_path)
    if registry.get("schema") != "ivanka.exploratory.assemblers.v1":
        raise ValueError("unsupported PX registry activation schema")
    branches = registry.get("adapter_branch_commits", {})
    candidates = {item["id"]: item for item in registry["candidates"]}
    assemblers = {item["id"]: item for item in evidence["assemblers"]}
    adopted = []
    for path in sorted(Path(handoff_dir).glob("*.json")):
        handoff = _load(path)
        if handoff.get("schema") != "ivanka.px.supervisor.handoff.v1":
            continue
        tool = handoff.get("tool_id")
        item = candidates.get(tool)
        target = assemblers.get(tool)
        if item is None or target is None:
            continue
        adapter = branches.get(tool)
        image_evidence = item.get("image_evidence") or {}
        pilot_evidence = item.get("pilot_evidence") or {}
        # An activated handoff without pilot evidence is not publishable; the
        # generic reader skips it instead of inventing provenance or crashing.
        if (not image_evidence.get("path") or not pilot_evidence.get("path")
                or not Path(image_evidence["path"]).is_file()
                or not Path(pilot_evidence["path"]).is_file()):
            continue
        pilot = _load(pilot_evidence["path"])
        # Handoff digests must be the digests carried by the registry itself.
        if (not all(SHA64.fullmatch(handoff.get(key, "")) for key in (
                "image_receipt_sha256", "pilot_receipt_sha256"))
                or image_evidence.get("sha256") != handoff["image_receipt_sha256"]
                or pilot_evidence.get("sha256") != handoff["pilot_receipt_sha256"]
                or _digest(image_evidence["path"]) != handoff[
                    "image_receipt_sha256"]
                or _digest(pilot_evidence["path"]) != handoff[
                    "pilot_receipt_sha256"]):
            raise ValueError("handoff receipt digests do not bind registry evidence")
        if (not adapter or adapter != pilot.get("adapter_commit")
                or item.get("image_sha256") != handoff.get("image_sha256")
                or item.get("image_sha256") != pilot.get("image_sha256")
                or pilot.get("source_commit") != item.get("source_commit")):
            raise ValueError("handoff adapter/image/source pins disagree")
        # The registry's exact adapter pin is authoritative. Every activated
        # tool is treated alike: no hardcoded per-tool exception, and no
        # provenance unless that exact commit has an independently observed
        # fork branch.
        try:
            neutral_pins = adapter_provenance(tool, adapter)
        except ValueError:
            continue
        item = dict(item, adapter_commit=adapter)
        if (not exploratory_policy.verified_receipt(
                item, image_evidence, "image")
                or not exploratory_policy.verified_receipt(
                    item, pilot_evidence, "pilot")):
            raise ValueError("activated tool lacks source-bound receipts")
        outcomes = {cohort: pilot.get(cohort, {}).get("status")
                    for cohort in ("physical", "synthetic")}
        if any(status != "success" for status in outcomes.values()):
            # A failed or partial pilot cannot promote tool-level provenance.
            continue
        for case in target.get("cases", []):
            if (case.get("score") is not None
                    and case.get("adapter_commit")
                    and case.get("image_sha256")
                    and (case["adapter_commit"] != adapter
                         or case["image_sha256"] != handoff["image_sha256"])):
                raise ValueError("handoff would rewrite measured case provenance")
        profile = dict(target)
        profile["adapter_commit"] = adapter
        profile["image_sha256"] = item["image_sha256"]
        profile.update(neutral_pins)
        profile["pilot"] = {
            "image_receipt_sha256": handoff["image_receipt_sha256"],
            "pilot_receipt_sha256": handoff["pilot_receipt_sha256"],
            "outcomes": outcomes,
        }
        if profile == target:
            continue  # already published: no artificial addition
        target.clear()
        target.update(profile)
        adopted.append(tool)
    return adopted


def ingest(report, evidence, root, real_data, registry_path=None,
           handoff_dir=None):
    """Return updated evidence and report with genuine cohort receipts joined."""
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("unsupported assembler evidence schema")
    root = Path(root)
    index = _read_index(root)
    result = scrub(json.loads(json.dumps(evidence)))
    added = []
    assemblers = {item["id"]: item for item in result["assemblers"]}
    if registry_path and handoff_dir:
        incoming = []
        for name in sorted(index["entries"]):
            receipt = _load(root / "receipts" / (name + ".json"))
            if receipt.get("tool_id") not in assemblers:
                continue
            result_path = root / "results" / (name + "-results.json")
            if not result_path.is_file():
                continue
            row = _load(result_path).get("samples", [{}])[0]
            incoming.append({"id": receipt["tool_id"], "cases": [{
                "cohort": "real" if receipt.get("cohort") == "physical"
                else receipt.get("cohort"),
                "canonical_alias": (receipt.get("alias") or "").replace(
                    "PX-", "", 1), "score": row.get("score")}]})
        assert_no_stale_scores(report, evidence, incoming)
        for tool in refresh_registry_provenance(
                result, registry_path, handoff_dir):
            added.append(("registry", tool, "activation"))
    # Re-scope older evidence rows whose launcher-group reading was published
    # as a comparable peak. Raw receipts are never rewritten.
    for item in assemblers.values():
        for case in item.get("cases", []):
            normalize_case(case)
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


def publish(site, root, real_data, registry_path=None, handoff_dir=None):
    """Atomically update evidence and runs.json after full-site validation."""
    from .site_build import validate_public_site
    site = Path(site)
    evidence = _load(site / "data/assembler-evidence.json")
    report = _load(site / "data/runs.json")
    updated, merged, added, joined = ingest(
        report, evidence, root, real_data, registry_path, handoff_dir)
    validate_publication(merged, updated)
    with tempfile.TemporaryDirectory(prefix="px-ingest-") as scratch:
        staged = Path(scratch) / "bench"
        shutil.copytree(site, staged)
        # The catalog may have gained a scoped RAM diagnostic in the source
        # while the site still carries the previous generated snapshot.
        from .current_runs import blank_mapping
        mapping_path = staged / "data/mapping-diagnostics.json"
        mapping_path.write_text(
            json.dumps(blank_mapping(merged["runs"][0]),
                       sort_keys=True, indent=2) + "\n")
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
    parser.add_argument("--handoff-dir", type=Path)
    args = parser.parse_args()
    _, _, added = publish(args.site, args.root, args.real_data,
                          args.registry, args.handoff_dir)
    print("PX_COHORT_INGESTED", len(added), added)


if __name__ == "__main__":
    main()
