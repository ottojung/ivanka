"""Source-only reference-based MiCall remap plan, receipt and row builder.

This module is the execution side of Intent 017 (`micall-remap`). It builds
an *exact* guarded command from the audited frozen contract, binds an immutable
receipt to that command, and emits the additive diagnostic rows consumed by
the publication boundary. It deliberately contains no process launcher: pilot
and cohort execution remain a separate, reviewed change behind the shared
capacity guard and exclusive slot.

Three invariants make the comparator diagnostic, never qualifying:

* The only command difference from the frozen de-novo arm is the single
  ``--denovo`` token. Reads, image, guard and output paths are unchanged.
* The reconstruction workflow sees only original paired reads and the
  packaged frozen reference assets. No truth or panel file is mounted or
  bound; the scoring panel is provenance only.
* Metrics that require native/stitched/unstitched contigs stay null and are
  named in ``unavailable``; no zero, contig or launcher-group RAM is invented.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import guarded_canary_launcher as launcher
from .px_ram_semantics import (
    COMPARABLE_KEY, COMPARABLE_METHOD, COMPARABLE_METHOD_VERSION,
    COMPARABLE_SCOPE, METHOD_KEY, SCOPE_KEY, UNAVAILABLE_KEY, VERSION_KEY,
)

TOOL_ID = "micall-remap"
LABEL = "MiCall remap (reference-based)"
METHOD_KIND = "reference-based"
PLAN_SCHEMA = "ivanka.remap-diagnostic.plan.v1"
RECEIPT_SCHEMA = "ivanka.remap-diagnostic.receipt.v1"
ROWS_SCHEMA = "ivanka.remap-diagnostic.rows.v1"
CAPACITY_SCHEMA = "ivanka.remap-diagnostic.capacity.v1"

# Audited from the immutable frozen source snapshot and image attestation;
# none of these values is inferred at runtime or taken from a result file.
SOURCE_COMMIT = "8458f9e5d34c39a6694b1fb6a40e055d7ce89553"
SOURCE_TREE = "4174e1cd850352788f7de5fe6cd66f12fbe27a70"
SAMPLE_PY_SHA256 = "8c4e4f130dd0eede5df0adba1c6842afd6ff6731ab64af4188a0b6cb91baf82c"
PROJECTS_JSON_SHA256 = "f5a5cfeb99c1b8f5b497cd7f416846b49141640de2a6b4b12293a3307c1790cd"
IMAGE_ID = "da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad"
IMAGE_DIGEST = (
    "sha256:52e6bed1b52e2cb4c21cdde850b86e82caa96f05b82271978e9cae34305d5eff")
PANEL_SHA256 = "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"
FROZEN_MANIFEST_SHA256 = (
    "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f")
INVOCATION = (
    "micall analyze sample /reads/R1.fastq.gz /reads/R2.fastq.gz /results "
    "--keep_scratch --bad_cycles_csv /results/bad_cycles.csv --all_projects")
INVOCATION_SHA256 = launcher.sha256_bytes(INVOCATION.encode())

GUARD = {
    "rss_limit_bytes": 4_000_000_000,
    "wall_seconds": 2400,
    "cpu_allocation": 2,
    "cid_bind_timeout_seconds": 30,
    "max_retry_attempts": 1,
    "kernel_enforcement": False,
    "minimum_free_bytes": 32 * 1024 ** 3,
}
RESERVE_BYTES = GUARD["minimum_free_bytes"]
COHORTS = frozenset(("real", "synthetic"))
SHA64 = re.compile(r"^[0-9a-f]{64}$")
ALIAS = re.compile(r"^[RH][0-9]{3}$")
RUN_ID = re.compile(r"^remap-[a-z0-9][a-z0-9_-]*$")

# Mapping mode never emits these de-novo-only stages (sample.py 239-312).
NA_METRICS = (
    "final_contig_count", "final_contig_total_bases",
    "final_contig_unknown_count", "final_contig_exact_duplicates",
    "final_contig_31mer_redundancy_fraction",
    "stitched_contig_count", "unstitched_contig_count",
)
NA_OUTPUTS = (
    "contigs.csv", "nuc_detail.csv", "amino_detail.csv",
    "conseq_region.csv", "unstitched_contigs.csv",
)


@dataclass(frozen=True)
class Case:
    """One original read pair bound to a canonical cohort alias."""
    alias: str
    cohort: str
    r1_sha256: str
    r2_sha256: str
    reads_dir: str
    attempt_dir: str
    timer: str
    cidfile: str
    storage_root: str
    runroot: str
    name: str
    stamp: str | None = None
    token: str | None = None
    r1_name: str = "R1.fastq.gz"
    r2_name: str = "R2.fastq.gz"


def canonical(payload) -> bytes:
    """Stable JSON encoding used for every digest in this module."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def digest(payload) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def input_manifest(cases) -> str:
    """Derive a cohort input digest from original read pairs only.

    Truth genomes and scoring panels are deliberately excluded: a remap input
    manifest must describe sequencing reads, never an evaluator asset.
    """
    entries = []
    for case in cases:
        if case.cohort not in COHORTS or not ALIAS.fullmatch(case.alias):
            raise ValueError("invalid remap cohort case identity")
        if not SHA64.fullmatch(case.r1_sha256) or not SHA64.fullmatch(case.r2_sha256):
            raise ValueError("remap case is not bound to hashed original reads")
        entries.append((case.alias, case.r1_sha256, case.r2_sha256))
    if not entries or len({item[0] for item in entries}) != len(entries):
        raise ValueError("remap input manifest has no unique cases")
    return digest(sorted(entries))


def read_pair(case: Case) -> dict:
    return {"R1": case.r1_sha256, "R2": case.r2_sha256}


def isolate_reads(*, source_dir, r1_name, r2_name, r1_sha256, r2_sha256,
                  destination_root) -> Path:
    """Hard-link exactly two attested originals into a private read mount.

    No bytes are copied and no sample directory metadata is exposed: the
    mount is a fresh directory whose only entries are the two original FASTQ
    names, linked to their attested inodes. Hard links keep the original
    basenames inside the container and survive a read-only bind mount.
    """
    root = Path(destination_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    mount = Path(tempfile.mkdtemp(prefix="remap-reads-", dir=str(root)))
    for name, expected in ((r1_name, r1_sha256), (r2_name, r2_sha256)):
        if not SHA64.fullmatch(expected) or "/" in name or ".." in name:
            raise ValueError("unsafe read pin for isolated mount")
        source = Path(source_dir).resolve() / name
        if not source.is_file() or source.is_symlink():
            raise ValueError("original read is not a regular attested file")
        target = mount / name
        os.link(source, target)
        if launcher.sha256_file(target) != expected:
            raise ValueError("isolated read does not match its attested hash")
    launcher.verify_isolated_reads(
        mount, reads=(r1_name, r2_name), sha256s=(r1_sha256, r2_sha256))
    return mount


def plan_case(case: Case, manifest: str, *, stamp: str, token: str) -> dict:
    """Build and validate the exact reference-based command; never launch it."""
    if not SHA64.fullmatch(manifest):
        raise ValueError("remap plan lacks the read-only cohort manifest")
    if case.cohort not in COHORTS or not ALIAS.fullmatch(case.alias):
        raise ValueError("invalid remap plan identity")
    expected_prefix = "R" if case.cohort == "real" else "H"
    if not case.alias.startswith(expected_prefix):
        raise ValueError("remap alias does not match its declared cohort")
    launcher.verify_isolated_reads(
        Path(case.reads_dir), reads=(case.r1_name, case.r2_name),
        sha256s=(case.r1_sha256, case.r2_sha256))
    argv = launcher.build_command(
        image=IMAGE_DIGEST,
        launch_image=IMAGE_ID,
        reads_dir=Path(case.reads_dir),
        attempt_dir=Path(case.attempt_dir),
        timer=Path(case.timer),
        cidfile=Path(case.cidfile),
        storage_root=Path(case.storage_root),
        runroot=Path(case.runroot),
        name=case.name,
        cpus=GUARD["cpu_allocation"],
        memory_bytes=GUARD["rss_limit_bytes"],
        timeout=GUARD["wall_seconds"] - 2,
        denovo=False,
        reads=(case.r1_name, case.r2_name),
    )
    if "--denovo" in argv or "--all_projects" not in argv:
        raise ValueError("remap plan is not the ordinary reference-based mode")
    plan = {
        "schema": PLAN_SCHEMA,
        "tool_id": TOOL_ID,
        "label": LABEL,
        "method_kind": METHOD_KIND,
        "de_novo": False,
        "qualification_claim": "NONE",
        "run_id": f"remap-{case.cohort}-{stamp.lower()}-{token}",
        "cohort": case.cohort,
        "alias": case.alias,
        "attempt_id": f"remap-{case.alias}-{stamp}-{token}",
        "argv": argv,
        "argv_sha256": launcher.sha256_bytes(json.dumps(argv, sort_keys=True).encode()),
        "guard": dict(GUARD),
        "source": {
            "commit": SOURCE_COMMIT, "tree": SOURCE_TREE,
            "sample_py_sha256": SAMPLE_PY_SHA256,
            "projects_json_sha256": PROJECTS_JSON_SHA256,
        },
        "image": {"id": IMAGE_ID, "digest": IMAGE_DIGEST,
                  "reuse": "frozen-clinical-base", "rebuilt": False},
        "reference": {
            "panel_sha256": PANEL_SHA256,
            "panel_role": "post_hoc_scoring_panel_only_never_mounted",
            "reconstruction_assets": "packaged-projects.json-in-frozen-base",
            "reconstruction_assets_sha256": PROJECTS_JSON_SHA256,
            "truth_mounted": False, "synthetic_truth_mounted": False,
            "scoring_panel_mounted": False,
        },
        "inputs": {
            "canonical_manifest_sha256": manifest,
            "paired_input_sha256": digest(read_pair(case)),
            "read_sha256": read_pair(case),
            "read_basenames": [case.r1_name, case.r2_name],
            "read_mount_entries": sorted(
                path.name for path in Path(case.reads_dir).iterdir()),
        },
        "outputs": {"unstitched_contigs": "not-applicable"},
        "unavailable": list(NA_METRICS),
        "executed": False,
    }
    if not RUN_ID.fullmatch(plan["run_id"]):
        raise ValueError("remap run identity is not distinct or malformed")
    return plan


def capacity_decision(free_bytes: int) -> dict:
    """Typed capacity gate; capacity alone never authorizes a live run."""
    if type(free_bytes) is not int or free_bytes < 0:
        raise ValueError("free bytes must be a non-negative integer")
    admitted = free_bytes >= RESERVE_BYTES
    return {
        "schema": CAPACITY_SCHEMA,
        "free_bytes": free_bytes,
        "reserved_bytes": RESERVE_BYTES,
        "deficit_bytes": 0 if admitted else RESERVE_BYTES - free_bytes,
        "capacity_admitted": admitted,
        "requires_independent_review": True,
        "requires_exclusive_shared_slot": True,
        "executed": False,
    }


CID64 = re.compile(r"^[0-9a-f]{64}$")


def _finite_number(value):
    return (type(value) in (int, float)
            and not isinstance(value, bool)
            and math.isfinite(value))


def validate_whole_container_observation(resource: dict, *, guard: dict) -> dict:
    """Accept only an ended, whole-container process-tree observation.

    Launcher-process-group bytes, unattested scopes, missing CID binding, or
    unfinished observations are never promoted to the comparable RAM metric.
    """
    if not isinstance(resource, dict):
        raise ValueError("resource observation must be a record")
    method = resource.get(METHOD_KEY)
    version = resource.get(VERSION_KEY)
    scope = resource.get(SCOPE_KEY)
    if method != COMPARABLE_METHOD or version != COMPARABLE_METHOD_VERSION or scope != COMPARABLE_SCOPE:
        raise ValueError("resource observation lacks attested whole-container scope")
    cid = resource.get("bound_cid") or resource.get("cid")
    if not isinstance(cid, str) or not CID64.fullmatch(cid):
        raise ValueError("resource observation lacks exact bound CID")
    if resource.get("observation_ended") is not True:
        raise ValueError("resource observation is not ended")
    samples = resource.get("samples")
    if not isinstance(samples, int) or isinstance(samples, bool) or samples < 2:
        raise ValueError("resource observation lacks enough samples")
    peak = resource.get("peak_rss_bytes")
    if not isinstance(peak, int) or isinstance(peak, bool) or peak < 0:
        raise ValueError("resource observation peak_rss_bytes is invalid")
    if peak > guard["rss_limit_bytes"]:
        raise ValueError("resource observation exceeds guard RSS limit")
    return {
        "bound_cid": cid,
        "observation_ended": True,
        "samples": samples,
        "peak_rss_bytes": peak,
    }


def attested_ram(resource: dict) -> dict:
    """Attach only a validated whole-container attestation.

    Any missing/invalid field forces comparable RAM to null with an explicit
    unavailable reason; launcher-group scope is never promoted.
    """
    diagnostics = {
        COMPARABLE_KEY: None,
        METHOD_KEY: COMPARABLE_METHOD,
        VERSION_KEY: COMPARABLE_METHOD_VERSION,
        SCOPE_KEY: COMPARABLE_SCOPE,
        UNAVAILABLE_KEY: "No valid ended whole-container RSS observation",
    }
    try:
        valid = validate_whole_container_observation(resource, guard=GUARD)
    except Exception:
        return diagnostics
    diagnostics[COMPARABLE_KEY] = round(valid["peak_rss_bytes"] / 1048576, 6)
    diagnostics.pop(UNAVAILABLE_KEY, None)
    return diagnostics


def build_receipt(plan: dict, *, status: str, diagnostics: dict | None = None,
                  unavailable=None, outputs=None, resource=None,
                  failure_reason=None, score=None, seconds=None) -> dict:
    """Bind one observed attempt to its exact plan and return a receipt."""
    if status not in ("attempted", "measured", "failed", "unavailable"):
        raise ValueError("unknown remap attempt status")
    if plan.get("executed") is not False or plan.get("de_novo") is not False:
        raise ValueError("remap receipt requires a source-only reference-based plan")
    values = dict(diagnostics or {})
    unavailable = sorted(set(NA_METRICS) | set(unavailable or ()))
    for key in NA_METRICS:
        values[key] = None
    for key in unavailable:
        if values.get(key) is not None:
            raise ValueError("unavailable remap metric carries a fabricated value")
    if resource is not None:
        values.update(attested_ram(resource))
    resource_record = dict(resource or {})
    guard_receipt = resource_record.get("guard_receipt") or {}
    if status == "measured":
        if not _finite_number(score) or not _finite_number(seconds):
            raise ValueError("measured remap case needs finite score and runtime")
        if score < 0 or not 0 < seconds <= GUARD["wall_seconds"]:
            raise ValueError("measured remap case violates the resource contract")
        if not isinstance(outputs, dict) or not outputs:
            raise ValueError("measured remap case lacks output evidence")
        if not SHA64.fullmatch(str(outputs.get("conseq_csv_sha256", ""))):
            raise ValueError("measured remap case lacks conseq output hash")
        validate_whole_container_observation(resource_record, guard=GUARD)
        if not isinstance(guard_receipt, dict):
            raise ValueError("measured remap case lacks guard receipt")
        bound_cid = guard_receipt.get("bound_cid") or guard_receipt.get("cid")
        if not isinstance(bound_cid, str) or not CID64.fullmatch(bound_cid):
            raise ValueError("measured remap case lacks guard receipt bound CID")
        if bound_cid != resource_record.get("bound_cid") and bound_cid != resource_record.get("cid"):
            raise ValueError("guard receipt CID does not bind resource observation")
        expected_guard = {
            "rss_limit_bytes": GUARD["rss_limit_bytes"],
            "wall_seconds": GUARD["wall_seconds"],
            "cpu_allocation": GUARD["cpu_allocation"],
        }
        for key, value in expected_guard.items():
            if guard_receipt.get(key) != value:
                raise ValueError(f"guard receipt {key} does not match exact bound")
        if guard_receipt.get("kernel_enforcement") is not False:
            raise ValueError("guard receipt kernel_enforcement must be false")
    elif score is not None or seconds is not None:
        raise ValueError("unmeasured remap case fabricates a measurement")
    if status != "measured" and not failure_reason:
        raise ValueError("unmeasured remap case needs an explicit reason")
    receipt_resource = dict(resource or {})
    if receipt_resource.get("bound_cid") or receipt_resource.get("cid"):
        cid = receipt_resource.get("bound_cid") or receipt_resource.get("cid")
        receipt_resource["bound_cid"] = cid
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "run_id": plan["run_id"],
        "cohort": plan["cohort"],
        "alias": plan["alias"],
        "attempt_id": plan["attempt_id"],
        "status": status,
        "qualification_claim": "NONE",
        "method": METHOD_KIND,
        "de_novo": False,
        "invocation": INVOCATION,
        "argv_sha256": plan["argv_sha256"],
        "guard_bounds": dict(GUARD),
        "guard_receipt": dict((resource_record.get("guard_receipt") or {})),
        "source": dict(plan["source"]),
        "image": dict(plan["image"]),
        "reference": dict(plan["reference"]),
        "inputs": dict(plan["inputs"]),
        "resource": receipt_resource,
        "outputs": dict(outputs or {}, unstitched_contigs="not-applicable"),
        "diagnostics": values,
        "unavailable": unavailable,
        "score": score,
        "seconds": seconds,
        "failure_reason": failure_reason,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


def build_rows(receipts, *, run_id: str, cohort: str) -> dict:
    """Emit the additive rows schema consumed by the display boundary."""
    if cohort not in COHORTS or not RUN_ID.fullmatch(run_id):
        raise ValueError("invalid remap rows identity")
    cases = []
    seen = set()
    for receipt in receipts:
        if (receipt.get("schema") != RECEIPT_SCHEMA
                or receipt.get("cohort") != cohort
                or receipt.get("run_id") != run_id
                or receipt.get("qualification_claim") != "NONE"
                or receipt.get("de_novo") is not False):
            raise ValueError("remap row is not bound to this diagnostic run")
        alias = receipt["alias"]
        if alias in seen or not ALIAS.fullmatch(alias):
            raise ValueError("duplicate or invalid remap row alias")
        seen.add(alias)
        if receipt["status"] not in ("measured", "failed", "unavailable"):
            raise ValueError("only terminal remap attempts can become rows")
        expected = dict(receipt)
        expected.pop("receipt_sha256", None)
        if receipt["receipt_sha256"] != digest(expected):
            raise ValueError("remap receipt digest does not match its bytes")
        cases.append({
            "alias": alias,
            "status": receipt["status"],
            "score": receipt["score"],
            "seconds": receipt["seconds"],
            "reference_panel_sha256": receipt["reference"]["panel_sha256"],
            "canonical_manifest_sha256": receipt["inputs"]["canonical_manifest_sha256"],
            "read_sha256": dict(receipt["inputs"]["read_sha256"]),
            "paired_input_sha256": receipt["inputs"]["paired_input_sha256"],
            "receipt_sha256": receipt["receipt_sha256"],
            "diagnostics": dict(receipt["diagnostics"]),
            "unavailable": list(receipt["unavailable"]),
            "unstitched_contigs": "not-applicable",
            "failure_reason": receipt["failure_reason"],
        })
    if not cases:
        raise ValueError("remap rows have no authentic cases")
    return {
        "schema": ROWS_SCHEMA,
        "tool_id": TOOL_ID,
        "method_kind": METHOD_KIND,
        # Display-bound identity fields required by the opt-in registry.
        "mode": METHOD_KIND,
        "denovo": False,
        "image_sha256": IMAGE_ID,
        "frozen_master_commit": SOURCE_COMMIT,
        "invocation_sha256": INVOCATION_SHA256,
        "run_id": run_id,
        "cohort": cohort,
        "cases": cases,
    }
