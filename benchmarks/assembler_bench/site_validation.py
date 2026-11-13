"""Fail-closed validation of pairwise evidence and public mapping densities."""
import copy
import json
import math
import re

from .public_dominance import enrich
from .public_metrics import CATALOG, SCHEMA as DIAGNOSTIC_SCHEMA
from .metric_explanations import INFO

SHA = re.compile(r"^[a-f0-9]{64}$")


def check_matrices(report):
    """Recompute the actual all-r proofs instead of trusting browser JSON."""
    expected = enrich(copy.deepcopy(report))
    for original, rebuilt in zip(report["runs"], expected["runs"]):
        if original.get("dominance_matrix") != rebuilt["dominance_matrix"]:
            raise ValueError("pairwise PSI matrix differs from independent proof")
        if original.get("micall_fork_provenance") != rebuilt["micall_fork_provenance"]:
            raise ValueError("fork provenance is unverified or inconsistent")
        grid = original["dominance_matrix"]
        if grid["schema"] != "assembler-bench.directed-all-r-psi.v1":
            raise ValueError("unexpected PSI matrix version")
        if original.get("eligible_for_expanded") is True and (
                original.get("micall_fork_provenance", {}).get("status")
                != "verified"):
            raise ValueError("expanded run lacks verified fork provenance")


def check_mapping_snapshot(site, report):
    source = site / "data/mapping-diagnostics.json"
    if not source.is_file():
        raise ValueError("missing public mapping/soft-clip metrics")
    snapshot = json.loads(source.read_text())
    run = next((r for r in report["runs"]
                if r["id"] == snapshot.get("run_id")), None)
    if (snapshot.get("schema") != DIAGNOSTIC_SCHEMA
            or run is None
            or run.get("hxb2_truth_verified") is not True
            or snapshot.get("status") != "INCOMPLETE"
            or snapshot.get("cases_measured") not in (0, 1)
            or snapshot.get("expected_cases") != 400
            or (snapshot.get("cases_measured") == 1
                and snapshot.get("sample_alias") not in {
                    sample["alias"] for sample in run["samples"]})
            or (snapshot.get("cases_measured") == 0
                and snapshot.get("sample_alias") is not None)
            or set(snapshot.get("tools", {})) != set(run["tools"])
            or set(snapshot.get("metric_catalog", {})) != set(CATALOG)):
        raise ValueError("unverified or incomplete diagnostic snapshot")
    for metric, (label, unit) in CATALOG.items():
        if snapshot["metric_catalog"][metric] != {
                "label": label, "unit": unit, "description": INFO[metric][0],
                "denominator": INFO[metric][1], "stage": INFO[metric][2],
                "suggested_direction": INFO[metric][3]}:
            raise ValueError("diagnostic unit or label drift")
    if snapshot["cases_measured"] == 0:
        if re.search(r"/workspace/|/home/|\.fastq|patient[-_]?id",
                     source.read_text(), re.IGNORECASE):
            raise ValueError("private identifiers leaked into mapping data")
        from .current_mapping import missing_arm
        for name, arm in snapshot["tools"].items():
            if arm != missing_arm():
                raise ValueError(f"{name}: missing mapping case must be null")
        return
    for name, arm in snapshot["tools"].items():
        data = arm.get("values", {})
        denom = arm.get("denominators", {})
        mapped = denom.get("mapped_primary_records")
        bases = denom.get("mapped_primary_read_bases")
        if (arm.get("status") != "measured"
                or not SHA.fullmatch(arm.get("source_sha256") or "")
                or arm.get("mapping_stage") != "MiCall scratch/temp.sam"
                or type(mapped) is not int or mapped < 1
                or type(bases) is not int or bases < 1):
            raise ValueError(f"{name}: unverified mapping source/denominator")
        for key, val in data.items():
            if key not in CATALOG or (val is not None and (
                    type(val) not in (int, float)
                    or not math.isfinite(val) or val < 0)):
                raise ValueError(f"{name}: invalid public diagnostic value")
        for key in ("soft_clipped_reads", "soft_clip_events",
                    "soft_clipped_bases", "clipped_read_fraction",
                    "soft_clip_events_per_1000_primary_mapped",
                    "soft_clipped_bases_per_1000_read_bases"):
            if key not in data or data[key] is None:
                raise ValueError(f"{name}: missing mandatory soft clipping")
        reads, events, clipped_bases = (
            data["soft_clipped_reads"], data["soft_clip_events"],
            data["soft_clipped_bases"])
        if not (reads <= mapped and events <= 2*reads
                and clipped_bases <= bases):
            raise ValueError(f"{name}: impossible soft-clip counts")
        if (not math.isclose(data["clipped_read_fraction"], reads/mapped)
                or not math.isclose(
                    data["soft_clip_events_per_1000_primary_mapped"],
                    events/mapped*1000)
                or not math.isclose(
                    data["soft_clipped_bases_per_1000_read_bases"],
                    clipped_bases/bases*1000)):
            raise ValueError(f"{name}: soft-clip density mismatch")
    if re.search(r"/workspace/|/home/|\.fastq|patient[-_]?id",
                 source.read_text(), re.IGNORECASE):
        raise ValueError("private identifiers leaked into public diagnostics")
