"""Validate only source-attested cohorts and reproducible combined views."""
import math
import re

from benchmarks.expanded.adapters import ASSEMBLERS
from .combined_public import (
    ID as COMBINED_ID, DEDICATED_ID as DEDICATED_COMBINED,
    preview as combined_preview)
from .real_public import ID as REAL_ID, DEDICATED_ID as DEDICATED_REAL
from .dedicated_image_attestation import SCHEMA as DEDICATED_SCHEMA
from .real_progress import validate_public
from .site_validation import SHA

SYNTH_ID = "hxb2-v4-fork-source-attested-live"
DEDICATED_SYNTH = "hxb2-v4-dedicated-source-live"
EXPECTED = {SYNTH_ID, REAL_ID, COMBINED_ID}
DEDICATED_EXPECTED = {DEDICATED_SYNTH, DEDICATED_REAL,
                      DEDICATED_COMBINED}
REAL_ALIAS = re.compile(r"^R[0-9]{3}$")


def check_physical(run, progress):
    if (run["status"] != "incomplete" or run.get("cohort") != "real"
            or run.get("expected_sample_count") != 198
            or run.get("eligible_for_expanded") is not False
            or run.get("psi") != {}
            or run.get("physical_progress") != progress["candidates"]
            or run.get("source_manifest_sha256")
            != progress["run_manifest_sha256"]):
        raise ValueError("unqualified physical-198 result incorrectly represented")
    seen, events = set(), {name: 0 for name in progress["candidates"]}
    for sample in run["samples"]:
        alias = sample["alias"]
        if not REAL_ALIAS.fullmatch(alias) or alias in seen:
            raise ValueError("physical sample alias unsafe or duplicated")
        seen.add(alias)
        if (set(sample) != {"alias", "score", "seconds", "failures",
                            "floor_ok", "outcome"}
                or set(sample["score"]) != set(ASSEMBLERS)
                or set(sample["seconds"]) != set(ASSEMBLERS)
                or len(sample["failures"]) != len(set(sample["failures"]))
                or set(sample["failures"]) - set(ASSEMBLERS)):
            raise ValueError("physical sample measurements malformed")
        for tool in ASSEMBLERS:
            score, seconds = sample["score"][tool], sample["seconds"][tool]
            if (score is None) != (seconds is None):
                raise ValueError("physical case has unmatched score and timing")
            if score is not None and (
                    type(score) not in (float, int) or
                    type(seconds) not in (float, int) or
                    not math.isfinite(score) or score < 0 or
                    not math.isfinite(seconds) or not 0 < seconds <= 1800):
                raise ValueError("physical case has invalid scored runtime")
        measured = sum(sample["score"][tool] is not None for tool in ASSEMBLERS)
        if (not measured and not sample["failures"]
                or sample["floor_ok"] is not None
                and (measured != 7 or sample["failures"])):
            raise ValueError("physical case incorrectly claims completion/floor")
        for tool in events:
            if sample["score"][tool] is not None or tool in sample["failures"]:
                events[tool] += 1
    if len(seen) != run["sample_count"]:
        raise ValueError("physical case count mismatch")
    if any(events[name] > item["finished"] for name, item in
           progress["candidates"].items()):
        raise ValueError("physical case evidence exceeds finished attempts")


def check_current(report):
    runs = {run["id"]: run for run in report["runs"]}
    active = set(runs)
    if len(runs) != 3 or active not in (EXPECTED, DEDICATED_EXPECTED):
        raise ValueError("only three coherent source-attested views allowed")
    identifiers = ((DEDICATED_SYNTH, DEDICATED_REAL, DEDICATED_COMBINED)
                   if active == DEDICATED_EXPECTED
                   else (SYNTH_ID, REAL_ID, COMBINED_ID))
    synthetic, real, combined = (runs[name] for name in identifiers)
    progress = report.get("real_progress")
    validate_public(progress)
    if (synthetic["cohort"] != "synthetic"
            or synthetic["status"] != "incomplete"
            or not synthetic.get("hxb2_truth_verified")
            or combined["status"] != "incomplete"
            or combined["cohort"] != "combined"
            or combined.get("eligible_for_expanded") is not False):
        raise ValueError("current cohort status misrepresented")
    if any(set(run["tools"]) != set(ASSEMBLERS)
           or run["images"] != synthetic["images"]
           or run.get("micall_fork_provenance", {}).get("status") != "verified"
           for run in report["runs"]):
        raise ValueError("current runs are not identical seven-assembler builds")
    if len(set(synthetic["images"].values())) != 7:
        raise ValueError("current contenders lack distinct pinned images")
    if active == DEDICATED_EXPECTED:
        proof = synthetic["micall_fork_provenance"]
        source = proof.get("images", {})
        if (proof.get("attestation_schema") != DEDICATED_SCHEMA
                or len({item.get("source_commit") for item in
                        source.values()}) != 7
                or any(source[tool].get("source_branch")
                       != "bench/assembler-" + tool
                       for tool in ASSEMBLERS)):
            raise ValueError("qualifying run needs seven dedicated source branches")
    check_physical(real, progress)
    expected = combined_preview(synthetic, real)
    for key, value in expected.items():
        if key == "dominance_matrix":
            continue
        if combined.get(key) != value:
            raise ValueError("combined cohort is not a faithful normalized join")
    if real["source_manifest_sha256"] != progress["run_manifest_sha256"]:
        raise ValueError("physical cohort manifest lost authenticity")
