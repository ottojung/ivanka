"""Fail-closed validation of the neutral public /bench/ contract.

Private Ivanka acceptance is validated on canonical source artifacts inside
the publisher before this layer runs. Everything here is tool-neutral: it
checks provenance, measured evidence, per-cohort rosters and independently
recomputed all-pairs Ψ, without any external project acceptance criteria.
"""
import json
import math
import re

from .adapter_branch_refs import adapter_provenance
from . import px_timing_semantics as timing
from .public_psi import public_matrix
from .public_view import EVIDENCE_SCHEMA, assert_clean_object
from .public_vocabulary import assert_clean

SCHEMA = "ivanka.assembler-bench.public.v1"
HISTORY_SCHEMA = "ivanka.assembler-bench.execution-history.v1"
ALIAS = re.compile(r"^[SHR][0-9]{3}$")
RUN_ID = re.compile(r"^[a-zA-Z0-9_-]+$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SECRET = re.compile(r"/workspace/|/home/|_R[12]_[0-9]{3}|"
                    r"\.fastq(?:\.gz)?|private[-_]sample|patient[-_](?:id|name)",
                    re.IGNORECASE)


def check_evidence(evidence):
    if (evidence.get("schema") != EVIDENCE_SCHEMA
            or not isinstance(evidence.get("assemblers"), list)
            or not isinstance(evidence.get("cohorts"), dict)
            or "baseline_assemblers" in evidence):
        raise ValueError("invalid public assembler evidence")
    assert_clean_object(evidence)
    seen = set()
    for name, entry in evidence["cohorts"].items():
        if not isinstance(entry, dict) or not name:
            raise ValueError("invalid cohort roster declaration")
        if "union_of" in entry:
            if not isinstance(entry["union_of"], list) or not entry[
                    "union_of"]:
                raise ValueError("invalid explicit roster union")
        elif (not isinstance(entry.get("assemblers"), list)
                or not entry["assemblers"]
                or len(entry["assemblers"]) != len(set(entry["assemblers"]))):
            raise ValueError("invalid explicit cohort assembler roster")
    for item in evidence["assemblers"]:
        if (not RUN_ID.fullmatch(item.get("id", ""))
                or item["id"] in seen
                or item.get("status") not in ("measured", "pending",
                                               "failed", "unavailable")):
            raise ValueError("duplicate or invalid public assembler identity")
        seen.add(item["id"])
        provenance = item.get("provenance", item)
        for key in ("source_commit", "adapter_commit"):
            if provenance.get(key) and not re.fullmatch(
                    "[0-9a-f]{40}", provenance[key]):
                raise ValueError("unverified source pin in public evidence")
        adapter = provenance.get("adapter_commit")
        if adapter:
            expected = adapter_provenance(item["id"], adapter)
            if any(provenance.get(k) != v for k, v in expected.items()):
                raise ValueError("adapter branch or commit URL mismatch")
        image = provenance.get("image_sha256")
        if image is not None and not SHA64.fullmatch(image):
            raise ValueError("unverified image digest in public evidence")
        for case in item.get("cases", []):
            mates = case.get("read_sha256") or case.get("input_sha256") or {}
            bound = (SHA64.fullmatch(case.get("paired_input_sha256", "")) or
                     (set(mates) == {"R1", "R2"} and
                      all(SHA64.fullmatch(mates.get(m, ""))
                          for m in ("R1", "R2"))))
            if (not ALIAS.fullmatch(case.get("canonical_alias", ""))
                    or not bound
                    or type(case.get("binding_receipts")) is not int
                    or case["binding_receipts"] < 3
                    or "launcher_seconds" not in case
                    or case.get("score_origin") not in (
                        "micall_final_max_reference_panel_v1",
                        "micall_final_max_abundant_truths_balanced_v2")):
                raise ValueError("unbound per-case evidence")
    return len(seen)


def check_joined_measurements(run, evidence):
    """A joined score must match an attested case and never invent runtime."""
    # An alias is NOT unique across assemblers: all tools can measure R053.
    # Key by tool and alias so one proof cannot mask another tool's tampering.
    cases = {}
    for item in evidence["assemblers"]:
        for case in item.get("cases", []):
            key = (item["id"], case["canonical_alias"])
            if key in cases:
                raise ValueError("duplicate per-tool per-case evidence")
            cases[key] = case
    proof = {}
    for sample in run.get("samples", []):
        alias = sample.get("alias")
        # A combined cohort must verify the SAME physical/synthetic source
        # receipt under its published R-Rxxx / S-Hxxx namespace.
        source_alias = alias
        if (run.get("cohort") == "combined" and isinstance(alias, str)
                and alias.startswith(("R-R", "S-H"))):
            source_alias = alias[2:]
        for tool in sample.get("score", {}):
            key = (tool, source_alias)
            case = cases.get(key)
            if case is None:
                continue
            if sample["score"][tool] != case["score"]:
                raise ValueError("joined score differs from attested case value")
            seconds = sample.get("seconds", {}).get(tool)
            item = sample.get("measurement_evidence", {}).get(tool, {})
            if seconds is not None:
                runtime = timing.comparable_seconds(case)
                if runtime is None or not timing.attested(item):
                    raise ValueError("launcher wall time cannot replace runtime")
                if seconds != runtime:
                    raise ValueError("joined runtime differs from attested case")
                if item.get(timing.RUNTIME_KEY) != runtime:
                    raise ValueError("joined runtime proof differs from case")
                for key in timing.PROOF_KEYS:
                    if item.get(key) != case.get(key):
                        raise ValueError("joined timing proof differs from case")
            if ("paired_input_sha256" in case and
                    item.get("paired_input_sha256") != case[
                        "paired_input_sha256"]):
                raise ValueError("joined case input hash mismatch")
            if ("input_sha256" in case and
                    item.get("input_sha256") != case["input_sha256"]):
                raise ValueError("joined source pair hash mismatch")
            if ("diagnostics" in case and case["diagnostics"] and
                    sample.get("diagnostics", {}).get(tool) !=
                    case["diagnostics"]):
                raise ValueError("joined diagnostic metrics differ")
            if ("peak_ram_observed_mib" in case and
                    item.get("peak_ram_observed_mib") !=
                    case["peak_ram_observed_mib"]):
                raise ValueError("joined peak RAM differs")
            proof.setdefault(tool, set()).add(alias)
    return proof


def check_matrix(run):
    """Recompute the full roster's Ψ from public values; no private flags."""
    expected = public_matrix(run)
    if run.get("dominance_matrix") != expected:
        raise ValueError("public pairwise Ψ differs from independent recompute")
    grid = expected
    if (grid["tools"] != run["tools"]
            or sum(len(row) for row in grid["metrics"]["alignment"].values())
            != len(run["tools"]) ** 2):
        raise ValueError("public Ψ matrix does not cover the cohort roster")
    return len(run["tools"])


def check_history(history, current_ids):
    """Validate archived evidence without importing Ivanka release policy."""
    if (history.get("schema") != HISTORY_SCHEMA
            or not isinstance(history.get("runs"), list)
            or not history["runs"]):
        raise ValueError("missing immutable execution history")
    ids = set(current_ids)
    for run in history["runs"]:
        name = run.get("id")
        if (not isinstance(name, str) or not RUN_ID.fullmatch(name)
                or name in ids):
            raise ValueError("duplicate or invalid archived run identifier")
        ids.add(name)
        tools = run.get("tools", [])
        if (run.get("schema") != SCHEMA
                or run.get("cohort") not in ("real", "synthetic")
                or not tools or len(set(tools)) != len(tools)
                or set(run.get("images", {})) != set(tools)
                or any(not is_hash(value) for value in run["images"].values())
                or run.get("psi") != {}):
            raise ValueError("archived public metadata invalid")
        provenance = run.get("micall_fork_provenance", {}).get("images", {})
        for tool, image in run["images"].items():
            if provenance.get(tool, {}).get("image_sha256") != image:
                raise ValueError("archived image provenance mismatch")
        samples = run.get("samples", [])
        if (not isinstance(samples, list) or not samples
                or run.get("sample_count") != len(samples)
                or len({row.get("alias") for row in samples}) != len(samples)):
            raise ValueError("archived sample count or aliases invalid")
        archive = run.get("archive", {})
        if not all(is_hash(archive.get(field)) for field in (
                "manifest_sha256", "results_sha256",
                "source_attestation_sha256")):
            raise ValueError("archived source evidence digest absent")
        for row in samples:
            if (not ALIAS.fullmatch(row.get("alias", ""))
                    or set(row.get("score", {})) != set(tools)
                    or set(row.get("seconds", {})) != set(tools)):
                raise ValueError("archived case alias or tool matrix incomplete")
            for tool in tools:
                score, seconds = row["score"][tool], row["seconds"][tool]
                if score is not None and (
                        type(score) not in (int, float)
                        or not math.isfinite(score) or score < 0):
                    raise ValueError("archived score changed")
                if seconds is not None and (
                        type(seconds) not in (int, float)
                        or not math.isfinite(seconds)
                        or not 0 < seconds <= 1800):
                    raise ValueError("archived runtime changed")
    if SECRET.search(json.dumps(history)):
        raise ValueError("private data in archived public results")
    return len(history["runs"])


def is_hash(value):
    return isinstance(value, str) and bool(SHA64.fullmatch(value))


def check_public_site(site):
    """Validate an entire neutral public site snapshot."""
    assert_clean(site, include_browser=True)
    report = json.loads((site / "data/runs.json").read_text())
    evidence = json.loads((site / "data/assembler-evidence.json").read_text())
    history = json.loads((site / "data/history.json").read_text())
    if report.get("schema") != SCHEMA or not report.get("runs"):
        raise ValueError("unsupported public result schema")
    assert_clean_object(report)
    check_evidence(evidence)
    joined = {}
    declared = {item["id"]: item for item in evidence["assemblers"]}
    for run in report["runs"]:
        if run.get("status") not in ("complete", "incomplete", "archived",
                                     "measured", "failed", "pending",
                                     "unavailable"):
            raise ValueError("invalid public run status")
        roster = run.get("roster", [])
        if ([item["id"] for item in roster] != run["tools"]
                or any(set(item) != {"id", "name", "status", "provenance",
                                     "cases"} for item in roster)):
            raise ValueError("incoherent cohort-owned assembler roster")
        for item in roster:
            expected = declared.get(item["id"], {})
            if expected.get("adapter_commit"):
                actual = item["provenance"]
                for key in ("adapter_commit", "source_branch", "source_url"):
                    if actual.get(key) != expected.get(key):
                        raise ValueError("cohort roster lost adapter branch evidence")
        for sample in run.get("samples", []):
            failed = set(sample.get("failures", []))
            if not failed <= set(run["tools"]):
                raise ValueError("unknown failed assembler in public case")
            for tool in failed:
                if (sample.get("score", {}).get(tool) is not None
                        or sample.get("seconds", {}).get(tool) is not None):
                    raise ValueError("failed arm shows a measurement")
            if failed and sample.get("outcome") != "failure":
                raise ValueError("failed case concealed in public data")
        joined[run["cohort"]] = check_joined_measurements(run, evidence)
        check_matrix(run)
    archived = check_history(history, {run["id"] for run in report["runs"]})
    if SECRET.search(json.dumps(report)):
        raise ValueError("private sample identifier in public results")
    return len(report["runs"]) + archived
