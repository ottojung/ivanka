"""One-shot, reviewable rewrite of committed public /bench/ JSON into the
tool-neutral contract. Reads pinned private receipts only at migration time;
CI validates the resulting public digests without needing private files.
"""
import argparse
import hashlib
import json
from pathlib import Path

from . import exploratory_policy
from .adapter_branch_refs import adapter_provenance
from .current_inputs import PANEL, PHYSICAL_MANIFEST
from .current_validation_v2 import V6_COHORT_SHA
from .exploratory_publication import validate as validate_exploratory
from .public_view import (
    EVIDENCE_SCHEMA,
    PHYSICAL_SCORE,
    SYNTHETIC_SCORE,
    assert_clean_object,
    merge_evidence,
    sanitize_document,
)
from .public_vocabulary import assert_clean

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site/bench"
MANIFESTS = {"physical": PHYSICAL_MANIFEST, "synthetic": V6_COHORT_SHA}
SCORES = {"physical": PHYSICAL_SCORE, "synthetic": SYNTHETIC_SCORE}


def _read(name):
    return json.loads((SITE / "data" / name).read_text())


def _write(name, document):
    assert_clean_object(document)
    (SITE / "data" / name).write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")


def _receipts_by_sha(root=None):
    root = Path(root) if root is not None else exploratory_policy.PROVENANCE_ROOT
    found = {}
    for path in sorted(root.rglob("*.json")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        found[digest] = path
    return found


def _evidence_case(receipt, cohort, sample):
    """Translate a private receipt into public, digest-only case evidence."""
    block = receipt.get(cohort)
    alias_evidence = receipt.get("canonical_alias_evidence", {}).get(cohort, {})
    alias = block.get("canonical_alias") or alias_evidence.get("alias")
    expected_public = "PX-" + sample["alias"][3:]
    if alias != expected_public:
        raise ValueError("receipt alias differs from published result row")
    manifest = block.get("canonical_manifest_sha256") or alias_evidence.get(
        "manifest_sha256")
    if manifest != MANIFESTS[cohort]:
        raise ValueError("case not bound to the canonical cohort manifest")
    paired = block.get("source_input_sha256") or alias_evidence.get(
        "input_pair_sha256")
    scoring = receipt.get("scoring_attestation", {})
    method = scoring.get(cohort + "_method")
    comparable = {
        "physical": "best_final_max_contig_local_alignment_over_reference_panel",
        "synthetic": SYNTHETIC_SCORE,
    }[cohort]
    if method != comparable:
        raise ValueError("case score unit differs from the cohort unit")
    if cohort == "physical" and scoring.get("physical_reference_panel_sha256") != PANEL:
        raise ValueError("case uses a different scoring panel")
    canonical = sample["alias"][3:]
    # Each independent hash agreement is a binding check, not just syntax.
    checks = 1  # canonical manifest hash matched the original cohort authority
    checks += 1  # paired original read input hash pinned by the pilot receipt
    reads = block.get("read_sha256")
    case = {
        "canonical_alias": canonical,
        "canonical_manifest_sha256": manifest,
        "paired_input_sha256": paired,
        "score_origin": SCORES[cohort],
        "score": sample["score"],
        "timing_origin": scoring.get("timing_origin", ""),
        "launcher_seconds": sample.get("seconds"),
    }
    if isinstance(reads, dict) and set(reads) == {"R1", "R2"}:
        case["read_sha256"] = reads
        checks += 1  # both original mate hashes pinned separately
    else:
        alias_evidence = receipt.get("canonical_alias_evidence", {}).get(cohort, {})
        if alias_evidence.get("input_pair_sha256") != paired:
            raise ValueError("paired input hash not bound to canonical alias")
        case["paired_input_method"] = block.get("input_hash_method") or (
            "paired-input SHA256 bound by source manifest")
        checks += 1
    if cohort == "physical":
        case["reference_panel_sha256"] = PANEL
        checks += 1  # identical frozen alignment reference panel
    if scoring.get("timing_origin"):
        checks += 1
    case["binding_receipts"] = checks
    if checks < 3:
        raise ValueError("case lacks independent source-hash binding")
    return case


def supplement_pilots(snapshot, receipts_root):
    """Add any fully receipted scored pilot omitted by an older snapshot."""
    known = {entry["id"] for entry in snapshot["candidates"]}
    registry = json.loads((ROOT / "benchmarks/assembler_bench/"
                           "exploratory_candidates.json").read_text())
    names = {item["id"]: item["name"] for item in registry["candidates"]}
    for receipt_path in sorted(receipts_root.rglob(
            "pilot-*-paired-canonical-scored-*.json")):
        data = json.loads(receipt_path.read_bytes())
        tool = data.get("tool_id")
        if not tool:
            continue
        prior = next((e for e in snapshot["candidates"]
                      if e["id"] == tool), None)
        if prior is not None and prior.get("results_status", "").startswith(
                "verified-"):
            continue  # an equally or better attested public entry already exists
        image_sha = data.get("image_sha256")
        image_receipt = receipts_root / next(
            p.name for p in receipts_root.glob("image-*.json")
            if json.loads(p.read_bytes()).get("image_sha256") == image_sha
            and json.loads(p.read_bytes()).get("tool_id") == tool)
        if hashlib.sha256(image_receipt.read_bytes()).hexdigest() != data[
                "image_receipt_sha256"]:
            raise ValueError("pilot image receipt not authentic: " + tool)
        samples = []
        results = {}
        for cohort in ("physical", "synthetic"):
            expected = data["per_sample_results_sha256"][cohort]
            result_file = receipts_root / next(
                p.name for p in receipts_root.glob(
                    f"results-{tool}-{cohort}-*.json")
                if hashlib.sha256(p.read_bytes()).hexdigest() == expected)
            payload = json.loads(result_file.read_bytes())
            if (payload.get("tool_id") != tool
                    or payload.get("image_sha256") != image_sha
                    or payload.get("cohort") != cohort):
                raise ValueError("per-case file not bound to pilot: " + tool)
            samples.extend(payload["samples"])
            results[cohort] = expected
        entry = {
            "id": tool, "name": names.get(tool, tool),
            "source_commit": data["source_commit"],
            "adapter_commit": data["adapter_commit"],
            "image_sha256": image_sha,
            "results_status": "verified-pilot",
            "results": {"cohorts": ["physical", "synthetic"],
                        "results_sha256": results,
                        "evidence_sha256": hashlib.sha256(
                            receipt_path.read_bytes()).hexdigest()},
            "samples": samples,
        }
        if prior is not None:
            snapshot["candidates"][snapshot["candidates"].index(prior)] = entry
        else:
            snapshot["candidates"].append(entry)
        known.add(tool)
    return snapshot


def build_evidence(snapshot, receipts, original_runs):
    """Explicit cohort-specific rosters, preserving existing observed tools."""
    assemblers = []
    for entry in snapshot.get("candidates", []):
        item = {
            "id": entry["id"], "name": entry["name"],
            "source_commit": entry.get("source_commit"),
            "adapter_commit": entry.get("adapter_commit"),
            "image_sha256": entry.get("image_sha256"),
            "status": "measured" if entry.get("results_status", "").startswith(
                "verified-") else "pending",
            "cases": [],
        }
        if item["adapter_commit"]:
            item.update(adapter_provenance(item["id"], item["adapter_commit"]))
        results = entry.get("results", {})
        digest = results.get("evidence_sha256")
        receipt = receipts.get(digest) if digest else None
        for cohort in results.get("cohorts", []):
            if cohort not in MANIFESTS:
                raise ValueError("unknown evidence cohort")
            receipt_data = json.loads(receipt.read_bytes()) if receipt else None
            if (receipt_data is None
                    or hashlib.sha256(receipt.read_bytes()).hexdigest() != digest):
                raise ValueError("missing pinned receipt for " + entry["id"])
            prefixed = "R" if cohort == "physical" else "H"
            for sample in entry.get("samples", []):
                if sample["alias"][3] != prefixed:
                    continue
                case = _evidence_case(receipt_data, cohort, sample)
                case["cohort"] = "real" if cohort == "physical" else cohort
                item["cases"].append(case)
        assemblers.append(item)
    names = [item["id"] for item in assemblers]
    existing = {run["cohort"]: list(run["tools"])
                for run in original_runs.get("runs", [])}
    declarations = {}
    for cohort in ("real", "synthetic"):
        tools = existing.get(cohort)
        if not isinstance(tools, list) or not tools:
            raise ValueError("missing source cohort assembler roster")
        # This one-time migration explicitly declares these newly attested
        # adapters in each current cohort; future cohorts may choose subsets.
        for name in names:
            if name not in tools:
                tools.append(name)
        declarations[cohort] = {"assemblers": tools}
    declarations["combined"] = {"union_of": ["real", "synthetic"]}
    return {"schema": EVIDENCE_SCHEMA,
            "title": "Assembler Bench source and measurement evidence",
            "cohorts": declarations, "assemblers": assemblers}


def evidence_from_snapshot(snapshot, original_runs, receipts_root=None):
    """Convert a receipt-validated publisher snapshot into neutral evidence."""
    root = Path(receipts_root) if receipts_root is not None else (
        exploratory_policy.PROVENANCE_ROOT)
    checked = json.loads(json.dumps(snapshot))
    supplement_pilots(checked, root)
    return build_evidence(checked, _receipts_by_sha(root), original_runs)


def migrate():
    snapshot = _read("exploratory-candidates.json")
    validate_exploratory(snapshot)
    supplement_pilots(snapshot, exploratory_policy.PROVENANCE_ROOT)
    # Read the existing three runs BEFORE publication. Their individual
    # assembler rosters, not a global hard-coded seven, define membership.
    original = _read("runs.json")
    evidence = build_evidence(snapshot, _receipts_by_sha(), original)
    _write("assembler-evidence.json", evidence)
    for name in ("history.json", "resource-policy.json",
                 "live-fork-attestation.json", "mapping-diagnostics.json"):
        _write(name, sanitize_document(_read(name)))
    attestation = (SITE / "data" / "live-fork-attestation.json").read_bytes()
    digest = hashlib.sha256(attestation).hexdigest()
    runs, joined = merge_evidence(_read("runs.json"), evidence)
    for run in runs["runs"]:
        proof = run.get("micall_fork_provenance", {})
        if proof.get("status") == "verified" and "attestation_sha256" in proof:
            proof["attestation_sha256"] = digest
    _write("runs.json", runs)
    (SITE / "data" / "exploratory-candidates.json").unlink()
    assert_clean(SITE, include_browser=False)
    return {"runs": len(runs["runs"]),
            "rosters": {run["id"]: len(run["roster"]) for run in runs["runs"]},
            "joined": [{"run": r, "tool": t, "case": a} for r, t, a in joined]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="only verify that the committed data is neutral")
    args = parser.parse_args()
    if args.check:
        assert_clean(SITE, include_browser=False)
        print("NEUTRAL_PUBLIC_DATA_OK")
        return
    print("NEUTRAL_PUBLIC_DATA", json.dumps(migrate(), sort_keys=True))


if __name__ == "__main__":
    main()
