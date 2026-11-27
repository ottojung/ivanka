"""Guarded remap-diagnostic pilot controller, scoring and retention plan.

This advances PR548's source-only remap_runner from plan/receipt/rows into a
guarded execution path. It does not duplicate PR548/549 code: plan building,
receipt/rows schema, display registry and launcher command validation stay in
remap_runner.py, guarded_canary_launcher.py and remap_diagnostic.py.

The controller is intentionally fail-closed. No case is executed unless the
preflight proves: attested same reads, frozen common image, guarded exclusive
slot ownership, reserve 32GiB plus reservation admission, 40m/4e9 guard bounds,
no truth mounted, and a distinct posthoc scoring identity. Actual benchmark or
image operations are never performed when reserve/capacity is unavailable.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import guarded_canary_launcher as launcher
from . import px_ram_semantics, remap_runner
from .px_ram_semantics import (
    COMPARABLE_METHOD,
    COMPARABLE_METHOD_VERSION,
    COMPARABLE_SCOPE,
    METHOD_KEY,
    SCOPE_KEY,
    UNAVAILABLE_KEY,
    VERSION_KEY,
)

CONTROLLER_SCHEMA = "ivanka.remap-diagnostic.controller.v1"
PLAN_SCHEMA = "ivanka.remap-diagnostic.pilot-plan.v1"
PREFLIGHT_SCHEMA = "ivanka.remap-diagnostic.preflight.v1"
EXECUTION_SCHEMA = "ivanka.remap-diagnostic.execution.v1"
SCORING_SCHEMA = "ivanka.remap-diagnostic.posthoc-score.v1"
RETENTION_SCHEMA = "ivanka.remap-diagnostic.retention.v1"

# Guarded execution is only the frozen 40m wall / 4e9 RSS diagnostic contract.
WALL_SECONDS = remap_runner.GUARD["wall_seconds"]
RSS_LIMIT_BYTES = remap_runner.GUARD["rss_limit_bytes"]
CPU_ALLOCATION = remap_runner.GUARD["cpu_allocation"]
RESERVE_BYTES = remap_runner.RESERVE_BYTES
MAX_ATTEMPTS_PER_CASE = 1

PHYSICAL_COHORT = "real"
SYNTHETIC_COHORT = "synthetic"
PILOT_COHORTS = (PHYSICAL_COHORT, SYNTHETIC_COHORT)

# Posthoc scoring methods are diagnostic; they never make a qualification claim.
PHYSICAL_SCORING_METHOD = "best_final_max_contig_local_alignment_over_reference_panel"
SYNTHETIC_SCORING_METHOD = "micall_final_max_abundant_truths_balanced_v2"

# Final MiCall output used for canonical scoring; raw contigs are never scored.
FINAL_MAX = "conseq.csv"
RETAINED_LOG_NAMES = (
    "launcher.stdout.log",
    "launcher.stderr.log",
    "container.log",
    "timing.json",
)
RETAINED_RECEIPT_NAMES = (
    "plan.json",
    "preflight.json",
    "execution.json",
    "posthoc-score.json",
    "receipt.json",
    "retention.json",
)
SHA64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PilotCase:
    """One guarded pilot case with read pins and posthoc scoring inputs.

    ``truth_manifest`` and ``truth_fasta`` are posthoc-only inputs. They MUST
    NOT be passed to the assembler container, mount builder, or argv builder.
    """

    case: remap_runner.Case
    panel_path: str | None = None
    panel_sha256: str | None = None
    truth_manifest: str | None = None
    truth_fasta: str | None = None
    expected_truth_sha256: str | None = None

    @property
    def cohort(self) -> str:
        return self.case.cohort

    @property
    def alias(self) -> str:
        return self.case.alias


def canonical(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def digest(payload) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_sha256(value: str, label: str) -> str:
    if not SHA64.fullmatch(str(value or "")):
        raise ValueError(f"{label} must be a sha256 hex digest")
    return str(value)


def _require_absent_truth_mounts(argv: list[str]) -> None:
    lowered = [str(token).lower() for token in argv]
    forbidden = ("hidden-truth", "truth", "haplotypes.fasta", "hxb2", "panel")
    for token in lowered:
        if any(word in token for word in forbidden):
            raise ValueError("truth/reference path leaked into assembler argv")


def _require_frozen_image(plan: dict) -> None:
    image = plan.get("image") or {}
    if image.get("id") != remap_runner.IMAGE_ID:
        raise ValueError("plan is not bound to the frozen remap image id")
    if image.get("digest") != remap_runner.IMAGE_DIGEST:
        raise ValueError("plan is not bound to the frozen remap image digest")
    if image.get("reuse") != "frozen-clinical-base" or image.get("rebuilt") is not False:
        raise ValueError("plan must reuse frozen clinical base without rebuild")


def _require_attested_reads(plan: dict) -> None:
    inputs = plan.get("inputs") or {}
    read_sha = inputs.get("read_sha256") or {}
    if set(read_sha) != {"R1", "R2"}:
        raise ValueError("plan is missing attested R1/R2 read hashes")
    _require_sha256(read_sha["R1"], "R1 sha256")
    _require_sha256(read_sha["R2"], "R2 sha256")
    basenames = inputs.get("read_basenames") or []
    if sorted(basenames) != sorted(read_sha):
        # read_basenames are original basenames, not R1/R2 keys; keep check narrow.
        if len(basenames) != 2 or not all(isinstance(n, str) and n for n in basenames):
            raise ValueError("plan is missing original read basenames")
    paired = inputs.get("paired_input_sha256")
    expected = remap_runner.digest({"R1": read_sha["R1"], "R2": read_sha["R2"]})
    if paired != expected:
        raise ValueError("plan paired_input_sha256 is not bound to attested reads")


def _require_guard_bounds(plan: dict) -> None:
    guard = plan.get("guard") or {}
    if guard.get("wall_seconds") != WALL_SECONDS:
        raise ValueError("plan wall guard is not 40m/2400s")
    if guard.get("rss_limit_bytes") != RSS_LIMIT_BYTES:
        raise ValueError("plan RSS guard is not 4e9 bytes")
    if guard.get("cpu_allocation") != CPU_ALLOCATION:
        raise ValueError("plan CPU allocation drifted")
    if guard.get("minimum_free_bytes") != RESERVE_BYTES:
        raise ValueError("plan reserve guard is not 32GiB")
    if guard.get("kernel_enforcement") is not False:
        raise ValueError("kernel enforcement must remain false/unclaimed")


def preflight(plan: dict, *, free_bytes: int, exclusive_slot: bool,
              image_present: bool = True, image_rebuilt: bool = False) -> dict:
    """Fail-closed preflight for one guarded remap pilot case."""
    reasons: list[str] = []
    if plan.get("schema") != remap_runner.PLAN_SCHEMA:
        reasons.append("plan_schema")
    if plan.get("qualification_claim") != "NONE":
        reasons.append("qualification_claim")
    if plan.get("de_novo") is not False:
        reasons.append("de_novo")
    try:
        _require_frozen_image(plan)
    except ValueError:
        reasons.append("frozen_image")
    try:
        _require_attested_reads(plan)
    except ValueError:
        reasons.append("attested_reads")
    try:
        _require_guard_bounds(plan)
    except ValueError:
        reasons.append("guard_bounds")
    argv = plan.get("argv")
    if not isinstance(argv, list) or not argv:
        reasons.append("argv")
    else:
        try:
            _require_absent_truth_mounts(argv)
        except ValueError:
            reasons.append("truth_mounted")
    reference = plan.get("reference") or {}
    if reference.get("truth_mounted") is not False:
        reasons.append("reference_truth_mounted")
    if reference.get("synthetic_truth_mounted") is not False:
        reasons.append("reference_synthetic_truth_mounted")
    if reference.get("scoring_panel_mounted") is not False:
        reasons.append("reference_panel_mounted")
    if not exclusive_slot:
        reasons.append("exclusive_slot")
    if not image_present:
        reasons.append("image_missing")
    if image_rebuilt:
        reasons.append("image_rebuilt")
    capacity = remap_runner.capacity_decision(int(free_bytes))
    if not capacity["capacity_admitted"]:
        reasons.append("reserve")
    admitted = not reasons
    return {
        "schema": PREFLIGHT_SCHEMA,
        "admitted": admitted,
        "reasons": reasons,
        "capacity": capacity,
        "exclusive_slot": bool(exclusive_slot),
        "image_present": bool(image_present),
        "image_rebuilt": bool(image_rebuilt),
        "no_truth_mounted": "truth_mounted" not in reasons
        and "reference_truth_mounted" not in reasons
        and "reference_synthetic_truth_mounted" not in reasons
        and "reference_panel_mounted" not in reasons,
    }


def final_max_path(output_dir) -> Path | None:
    root = Path(output_dir)
    for candidate in (root / FINAL_MAX, root / "scratch" / FINAL_MAX):
        if candidate.is_file():
            return candidate
    return None


def _score_physical(output_dir, *, panel_path, panel_sha256) -> dict:
    """Posthoc physical scoring via the frozen 33-reference panel.

    This is diagnostic-only. The panel is never mounted into reconstruction.
    """
    seqs = _final_max_sequences(output_dir)
    if not panel_path or not Path(panel_path).is_file():
        raise ValueError("physical posthoc scorer missing reference panel")
    panel_sha256 = _require_sha256(panel_sha256 or sha256_file(panel_path),
                                   "panel_sha256")
    actual = sha256_file(panel_path)
    if actual != panel_sha256:
        raise ValueError("physical reference panel hash mismatch")
    panel_obj = json.loads(Path(panel_path).read_bytes())
    if not seqs:
        return {
            "schema": SCORING_SCHEMA,
            "method": PHYSICAL_SCORING_METHOD,
            "cohort": PHYSICAL_COHORT,
            "score": 0.0,
            "reference_panel_sha256": panel_sha256,
            "best_reference": None,
            "multitruth": None,
        }
    from benchmarks.reference_panel import best_panel_alignment, panel_sha256 as panel_digest
    if panel_digest(panel_obj) != panel_sha256:
        raise ValueError("prepared reference panel digest mismatch")
    best = best_panel_alignment(seqs, panel_obj)
    return {
        "schema": SCORING_SCHEMA,
        "method": PHYSICAL_SCORING_METHOD,
        "cohort": PHYSICAL_COHORT,
        "score": float(best["score"]),
        "reference_panel_sha256": panel_sha256,
        "best_reference": best.get("reference"),
        "multitruth": None,
    }


def _final_max_sequences(output_dir):
    from benchmarks.project_references import final_max_sequences

    return final_max_sequences(Path(output_dir))


def _score_synthetic(output_dir, *, truth_manifest, truth_fasta,
                     expected_truth_sha256=None) -> dict:
    manifest_path = Path(truth_manifest)
    truth_path = Path(truth_fasta)
    if not manifest_path.is_file() or not truth_path.is_file():
        raise ValueError("synthetic posthoc scorer missing truth inputs")
    manifest = json.loads(manifest_path.read_bytes())
    pinned = ((manifest.get("sha256") or {}).get("hidden-truth/haplotypes.fasta"))
    if not SHA64.fullmatch(str(pinned or "")):
        raise ValueError("synthetic truth hash is not pinned in manifest")
    actual_truth = sha256_file(truth_path)
    if actual_truth != pinned:
        raise ValueError("synthetic truth hash mismatch")
    if expected_truth_sha256 and _require_sha256(expected_truth_sha256, "expected truth") != pinned:
        raise ValueError("synthetic expected truth hash mismatch")
    seqs = _final_max_sequences(output_dir)
    if seqs:
        from benchmarks.expanded.score import score_sequences

        scored = score_sequences(manifest, truth_path, seqs)
        score = float(scored["score"])
        per_truth = scored.get("per_truth") or {}
        reference_count = int(scored.get("reference_count") or len(per_truth) or 0)
    else:
        score = 0.0
        per_truth = {}
        reference_count = 0
    return {
        "schema": SCORING_SCHEMA,
        "method": SYNTHETIC_SCORING_METHOD,
        "cohort": SYNTHETIC_COHORT,
        "score": score,
        "truth_sha256": pinned,
        "reference_count": reference_count,
        "multitruth": {
            "diagnostic_only": True,
            "per_truth": per_truth,
            "truth_count": len(per_truth),
            "all_abundant_truths_scored": bool(per_truth),
        },
    }


def posthoc_score(plan: dict, pilot_case: PilotCase, output_dir) -> dict:
    """Score retained final MAX after execution; never during reconstruction."""
    cohort = plan.get("cohort")
    if cohort == PHYSICAL_COHORT:
        result = _score_physical(
            output_dir,
            panel_path=pilot_case.panel_path,
            panel_sha256=pilot_case.panel_sha256,
        )
    elif cohort == SYNTHETIC_COHORT:
        result = _score_synthetic(
            output_dir,
            truth_manifest=pilot_case.truth_manifest,
            truth_fasta=pilot_case.truth_fasta,
            expected_truth_sha256=pilot_case.expected_truth_sha256,
        )
    else:
        raise ValueError("unknown remap cohort")
    result["run_id"] = plan.get("run_id")
    result["alias"] = plan.get("alias")
    result["qualification_claim"] = "NONE"
    return result


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_bytes())


def _write_json(path: Path, payload: dict) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical(payload)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return hashlib.sha256(data).hexdigest()


def _copy_log(source: Path | None, dest: Path) -> str | None:
    if source is None:
        return None
    src = Path(source)
    if not src.is_file():
        return None
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dest.resolve():
        return sha256_file(dest)
    shutil.copyfile(src, dest)
    return sha256_file(dest)


def collect_resource_evidence(*, peak_rss_bytes=None, samples=None,
                              observation_ended=None, wall_seconds=None,
                              exit_status=None) -> dict:
    resource = {}
    if peak_rss_bytes is not None:
        resource["peak_rss_bytes"] = int(peak_rss_bytes)
    if samples is not None:
        resource["samples"] = int(samples)
    if observation_ended is not None:
        resource["observation_ended"] = bool(observation_ended)
    if wall_seconds is not None:
        resource["wall_seconds"] = float(wall_seconds)
    if exit_status is not None:
        resource["exit_status"] = int(exit_status)
    return resource


def classify_execution(*, returncode: int | None, final_max_exists: bool,
                       timed_out: bool = False) -> tuple[str, str | None]:
    if timed_out:
        return "failed", "wall_limit"
    if returncode is None:
        return "failed", "missing_exit_status"
    if returncode != 0:
        return "failed", f"exit_{returncode}"
    if not final_max_exists:
        return "failed", "no_final_max"
    return "measured", None


def retain_case_artifacts(*, attempt_dir: Path, receipt: dict,
                          logs: dict[str, str | None] | None = None,
                          extra: dict[str, str] | None = None) -> dict:
    attempt_dir = Path(attempt_dir)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    kept_logs = {}
    for name, src in (logs or {}).items():
        if src is None:
            continue
        dest = attempt_dir / "logs" / Path(name).name
        digest = _copy_log(Path(src), dest)
        if digest:
            kept_logs[dest.name] = digest
    receipt_path = attempt_dir / "receipt.json"
    receipt_sha = _write_json(receipt_path, receipt)
    manifest = {
        "schema": RETENTION_SCHEMA,
        "attempt_dir": str(attempt_dir),
        "receipt_sha256": receipt_sha,
        "logs": kept_logs,
        "extra": dict(extra or {}),
        "retained": True,
    }
    _write_json(attempt_dir / "retention.json", manifest)
    return manifest


def execute_case(pilot_case: PilotCase, *, plan: dict, preflight_result: dict,
                 runner, output_dir: Path, attempt_dir: Path,
                 scorer=None) -> dict:
    """Execute one guarded remap pilot case with injected runner.

    ``runner`` is callable: runner(plan, output_dir, attempt_dir) -> dict with
    keys returncode, peak_rss_bytes, samples, observation_ended, wall_seconds,
    timed_out, log_paths (dict), stdout_path/stderr_path optional. Tests inject
    a fake runner; production wiring uses a guarded podman launcher.
    """
    output_dir = Path(output_dir)
    attempt_dir = Path(attempt_dir)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    _write_json(attempt_dir / "plan.json", plan)
    _write_json(attempt_dir / "preflight.json", preflight_result)

    if not preflight_result.get("admitted"):
        reason = "preflight:" + ",".join(preflight_result.get("reasons", ["unknown"]))
        receipt = remap_runner.build_receipt(
            plan, status="failed", failure_reason=reason,
            unavailable=list(remap_runner.NA_METRICS),
        )
        retain_case_artifacts(attempt_dir=attempt_dir, receipt=receipt)
        return receipt

    run = runner(plan, output_dir, attempt_dir) or {}
    returncode = run.get("returncode")
    timed_out = bool(run.get("timed_out"))
    log_paths = dict(run.get("log_paths") or {})
    for k in ("stdout_path", "stderr_path", "container_log_path"):
        if k in run and run[k]:
            log_paths.setdefault(Path(str(run[k])).name, str(run[k]))

    final_max = final_max_path(output_dir)
    status, failure_reason = classify_execution(
        returncode=returncode, final_max_exists=final_max is not None,
        timed_out=timed_out,
    )
    resource = collect_resource_evidence(
        peak_rss_bytes=run.get("peak_rss_bytes"),
        samples=run.get("samples"),
        observation_ended=run.get("observation_ended"),
        wall_seconds=run.get("wall_seconds"),
        exit_status=returncode,
    )
    diagnostics = {}
    unavailable = list(remap_runner.NA_METRICS)
    score = None
    seconds = run.get("wall_seconds")
    scoring_payload = None

    if status == "measured":
        score_fn = scorer or (lambda p, c, o: posthoc_score(p, c, o))
        try:
            scoring_payload = score_fn(plan, pilot_case, output_dir)
            score = float(scoring_payload["score"])
            _write_json(attempt_dir / "posthoc-score.json", scoring_payload)
            # Multitruth diagnostic is posthoc-only metadata; never mounted.
            if scoring_payload.get("multitruth") is not None:
                diagnostics["multitruth_diagnostic"] = scoring_payload["multitruth"]
                diagnostics["synthetic_abundant_truth_count"] = scoring_payload.get(
                    "reference_count")
        except Exception as exc:  # fail closed: no fabricated score
            status = "failed"
            failure_reason = f"posthoc_scoring_error:{type(exc).__name__}"
            score = None
            seconds = None

    execution = {
        "schema": EXECUTION_SCHEMA,
        "run_id": plan.get("run_id"),
        "alias": plan.get("alias"),
        "status": status,
        "returncode": returncode,
        "timed_out": timed_out,
        "final_max_present": final_max is not None,
        "final_max_sha256": sha256_file(final_max) if final_max else None,
        "resource": resource,
        "failure_reason": failure_reason,
    }
    _write_json(attempt_dir / "execution.json", execution)

    outputs = {}
    if final_max is not None:
        outputs["conseq_csv_sha256"] = sha256_file(final_max)
        outputs["final_max_path_retained"] = str(final_max)

    receipt = remap_runner.build_receipt(
        plan,
        status=status,
        diagnostics=diagnostics,
        unavailable=unavailable,
        outputs=outputs,
        resource=resource,
        failure_reason=failure_reason,
        score=score,
        seconds=seconds if status == "measured" else None,
    )
    if scoring_payload is not None:
        receipt["posthoc_scoring"] = {
            "schema": scoring_payload.get("schema"),
            "method": scoring_payload.get("method"),
            "reference_panel_sha256": scoring_payload.get("reference_panel_sha256"),
            "truth_sha256": scoring_payload.get("truth_sha256"),
            "reference_count": scoring_payload.get("reference_count"),
            "qualification_claim": "NONE",
        }
    retain_case_artifacts(attempt_dir=attempt_dir, receipt=receipt, logs=log_paths)
    return receipt


def build_pilot_plan(*, physical_cases: list[PilotCase],
                     synthetic_cases: list[PilotCase],
                     stamp: str, token: str) -> dict:
    """Build a diagnostic-only pilot plan for physical+synthetic+multitruth.

    No execution, no image build, no scoring, no frozen result mutation.
    """
    if not SHA64.fullmatch(token) and not re.fullmatch(r"[a-z0-9_-]{6,64}", token):
        raise ValueError("pilot plan token must be an explicit bounded identifier")
    cases = []
    for pc in physical_cases:
        if pc.cohort != PHYSICAL_COHORT:
            raise ValueError("physical case cohort mismatch")
        cases.append({"alias": pc.alias, "cohort": pc.cohort,
                      "multitruth_diagnostic": False})
    for sc in synthetic_cases:
        if sc.cohort != SYNTHETIC_COHORT:
            raise ValueError("synthetic case cohort mismatch")
        cases.append({"alias": sc.alias, "cohort": sc.cohort,
                      "multitruth_diagnostic": True})
    aliases = [c["alias"] for c in cases]
    if len(set(aliases)) != len(aliases):
        raise ValueError("pilot plan aliases must be distinct")
    return {
        "schema": PLAN_SCHEMA,
        "controller_schema": CONTROLLER_SCHEMA,
        "qualification_claim": "NONE",
        "diagnostic_only": True,
        "execution_performed": False,
        "stamp": stamp,
        "token": token,
        "guards": {
            "reserve_bytes": RESERVE_BYTES,
            "reservation_required": True,
            "exclusive_slot_required": True,
            "wall_seconds": WALL_SECONDS,
            "rss_limit_bytes": RSS_LIMIT_BYTES,
            "cpu_allocation": CPU_ALLOCATION,
            "kernel_enforcement": False,
            "no_truth_mounted": True,
            "frozen_common_image": remap_runner.IMAGE_DIGEST,
            "attested_same_reads_required": True,
        },
        "posthoc": {
            "canonical_scoring": True,
            "physical_method": PHYSICAL_SCORING_METHOD,
            "synthetic_method": SYNTHETIC_SCORING_METHOD,
            "multitruth_diagnostic": True,
        },
        "retention": {
            "retained_logs": list(RETAINED_LOG_NAMES),
            "retained_receipts": list(RETAINED_RECEIPT_NAMES),
            "distinct_receipts_per_attempt": True,
            "null_unavailable_metrics": list(remap_runner.NA_METRICS),
        },
        "cohorts": {
            "physical": [c for c in cases if c["cohort"] == PHYSICAL_COHORT],
            "synthetic": [c for c in cases if c["cohort"] == SYNTHETIC_COHORT],
        },
        "case_count": len(cases),
    }
