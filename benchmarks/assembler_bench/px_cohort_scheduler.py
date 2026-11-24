"""Resumable, reference-blind cohort planner for NONQUALIFYING PX explorers.

This module is deliberately inert: it builds a verified queue of per-case arms,
attests immutable receipts and exports only public aliases. It never launches a
MiCall process. Execution belongs to the PR411 guarded single-worker launcher
and is wired in by ``px_supervisor`` only after image-agent handoff.
"""
import csv
import hashlib
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from benchmarks.milestone198 import MANIFEST_SHA256 as PHYSICAL_MANIFEST_SHA256

from . import exploratory_policy, exploratory_space
from .px_ram_semantics import (METHOD_KEY, SCOPE_KEY, VERSION_KEY, attested,
                               observed_mib)

SCHEMA = "ivanka.px.cohort.plan.v1"
RECEIPT_SCHEMA = "ivanka.px.case.receipt.v1"
CHECKPOINT_SCHEMA = "ivanka.px.cohort.checkpoint.v1"
INDEX_SCHEMA = "ivanka.px.case.receipt-index.v1"
RESULT_SCHEMA = "ivanka.exploratory.per-sample.v1"

PHYSICAL_COUNT = 198
SYNTHETIC_COUNT = 464
MAX_SAMPLES = PHYSICAL_COUNT + SYNTHETIC_COUNT
EXPECTED_COUNTS = {"physical": PHYSICAL_COUNT, "synthetic": SYNTHETIC_COUNT}
COHORTS = ("physical", "synthetic")
ALIAS = re.compile(r"^PX-([RH])([0-9]{3})\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
PRIVATE = re.compile(r"/workspace/|/home/|\.fastq|patient[-_]?id", re.IGNORECASE)
# Keys that could let truth or a scoring reference steer an assembler arm.
FORBIDDEN_CASE_KEYS = re.compile(
    r"truth|reference|hxb2|subtype|panel|ancestry|score|scorer|psi|rank",
    re.IGNORECASE)
TERMINAL_OUTCOMES = frozenset(("success", "failure"))
FAILURE_REASONS = frozenset((
    "error", "timeout", "no_contigs", "no_final_max", "disk_stop",
    "wall_limit", "observed_rss_limit", "measurement_unavailable",
))
# Infrastructure failures preserve attempts and may be retried boundedly.
INFRASTRUCTURE_FAILURE_REASONS = frozenset(("disk_stop", "measurement_unavailable"))
MAX_INFRA_ATTEMPTS = 2
MAX_RESERVE = 4 * 1024**3
MIN_RESERVE = 1024**3
# MiCall's frozen final MAX consensus artifact, never a raw assembler contig.
MAX_ARTIFACT = "conseq.csv"
# The original v6 synthetic cohort is the authority for H001..H464 ordering.
SYNTHETIC_COHORT = Path(__file__).resolve().parents[1] / (
    "expanded/references/mixed-464-v6-cohort.json")
SYNTHETIC_COHORT_SHA256 = (
    "90990f6109553347d37f7754cde63398a4dce57c388f90c2ce4b648530bfdfe4")


def sha256_file(path):
    """Hash a file by streaming; never trust a caller-supplied digest."""
    target = Path(path).resolve(strict=True)
    if not target.is_file():
        raise ValueError("hashed arm input is not a regular file")
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def peak_ram_fields(source):
    """Copy sampler attestation from a monitor record into a receipt."""
    if not isinstance(source, dict):
        return {}
    fields = {key: source[key] for key in (METHOD_KEY, VERSION_KEY, SCOPE_KEY)
              if key in source}
    if fields and attested(fields) and source.get("peak_rss_bytes") is not None:
        fields["peak_ram_observed_mib"] = observed_mib(source["peak_rss_bytes"])
    return fields


def peak_ram_observed_mib(receipt):
    """Convert an immutable receipt's observed RSS to a public MiB metric."""
    value = receipt.get("peak_rss_bytes") if isinstance(receipt, dict) else None
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("observed peak RSS is not numeric")
    if not math.isfinite(value) or value < 0:
        raise ValueError("observed peak RSS is not finite and non-negative")
    if receipt.get(METHOD_KEY) and not attested(receipt):
        # An explicit non-container sampler never yields a comparable peak.
        return None
    return round(value / 1048576, 6)


def write_resource(root, arm, receipt):
    """Publish comparable resource evidence for every terminal arm."""
    path = Path(root) / "results" / (receipt_id(arm) + "-resource.json")
    record = {
        "schema": "ivanka.px.arm-resource.v1", "tool_id": arm["tool_id"],
        "cohort": arm["cohort"], "alias": arm["alias"],
        "outcome": receipt["outcome"], "attempt": receipt.get("attempt", 1),
        "peak_rss_bytes": receipt.get("peak_rss_bytes"),
    }
    record.update(peak_ram_fields(receipt))
    record.update({
        "peak_ram_observed_mib": peak_ram_observed_mib(receipt),
        "measurement_present": receipt.get("peak_rss_bytes") is not None,
    })
    _assert_public(record)
    return path, _atomic_json(path, record)


def _json_bytes(obj):
    return (json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _assert_public(obj):
    """Refuse private paths or identities in any exportable structure."""
    if PRIVATE.search(_json_bytes(obj).decode()):
        raise ValueError("private identifier in public PX cohort data")


def _atomic_write(path, data):
    """Publish bytes by rename so readers never observe a partial checkpoint."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name("." + target.name + "." + uuid.uuid4().hex)
    with temp.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, target)
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _atomic_json(path, obj):
    _atomic_write(path, _json_bytes(obj))
    return sha256_file(path)


def _alias(position, cohort):
    """One-based original Assembler Bench alias, never a pilot ordinal.

    Physical aliases follow sorted physical manifest sample names; synthetic
    aliases follow sorted v6 cohort case IDs. ``position`` is the 1-based rank
    in that original ordering.
    """
    if not 1 <= position <= EXPECTED_COUNTS[cohort]:
        raise ValueError("public alias position out of cohort range")
    return f"PX-{'R' if cohort == 'physical' else 'H'}{position:03d}"


def canonical_aliases(source_ids, cohort):
    """Map private source identities to their canonical public aliases."""
    ordered = sorted(source_ids)
    if len(set(ordered)) != len(ordered):
        raise ValueError("duplicated source identity in PX cohort source")
    return {source_id: _alias(position, cohort)
            for position, source_id in enumerate(ordered, 1)}


@dataclass(frozen=True)
class CasePair:
    """Private source identity and reads bound to a canonical public alias."""

    source_id: str
    alias: str
    cohort: str
    r1: Path
    r2: Path
    seeds: Path = None
    seeds_provenance: dict = None

    def input_hashes(self):
        hashes = {"R1": sha256_file(self.r1), "R2": sha256_file(self.r2)}
        if self.seeds is not None:
            hashes["seeds"] = sha256_file(self.seeds)
        return hashes

    def public(self):
        return {"alias": self.alias, "cohort": self.cohort,
                "input_sha256": self.input_hashes()}


def _physical_sample_ids(path):
    """Read the original manifest only after its pinned SHA-256 verifies."""
    if sha256_file(path) != PHYSICAL_MANIFEST_SHA256:
        raise ValueError("original physical manifest SHA256 changed")
    with Path(path).open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != PHYSICAL_COUNT or len({row["sample"] for row in rows}) != PHYSICAL_COUNT:
        raise ValueError("original physical manifest is not the 198-case cohort")
    return {row["sample"] for row in rows}


def _synthetic_case_hashes(path):
    """Return v6 case-ID read digests only after its pinned SHA-256 verifies."""
    if sha256_file(path) != SYNTHETIC_COHORT_SHA256:
        raise ValueError("original v6 synthetic cohort SHA256 changed")
    cases = json.loads(Path(path).read_bytes())["cases"]
    if len(cases) != SYNTHETIC_COUNT or len({case["id"] for case in cases}) != SYNTHETIC_COUNT:
        raise ValueError("original v6 cohort is not the 464-case cohort")
    return {case["id"]: {"R1": case["sha256"]["reads/R1.fastq.gz"],
                         "R2": case["sha256"]["reads/R2.fastq.gz"]}
            for case in cases}


class CohortSource:
    """Private read pairs bound to one-based original Assembler Bench aliases."""

    def __init__(self, physical, synthetic, *, physical_manifest=None,
                 synthetic_cohort=None, attested_inputs=None):
        self._cases = {"physical": list(physical), "synthetic": list(synthetic)}
        self._manifest = physical_manifest
        self._cohort = synthetic_cohort
        self._attested = attested_inputs or {}
        self.validate()

    def validate(self):
        for cohort in COHORTS:
            cases = self._cases[cohort]
            if len(cases) != EXPECTED_COUNTS[cohort]:
                raise ValueError("cohort size differs from the canonical PX queue")
            ids = [case.source_id for case in cases]
            canonical = canonical_aliases(ids, cohort)
            expected_inputs = self._expected_inputs(cohort, ids)
            for case in cases:
                if case.alias != canonical[case.source_id] or case.cohort != cohort:
                    # Aliases are derived from original source ordering, never
                    # from the order in which pilot arms happened to run.
                    raise ValueError("public alias is not the canonical original alias")
                if not case.r1.is_file() or not case.r2.is_file():
                    raise ValueError("paired FASTQ input is missing")
                if expected_inputs is not None and case.input_hashes() != expected_inputs.get(
                        case.source_id):
                    raise ValueError("attested paired input SHA mismatch for " + case.alias)
                if case.seeds is not None and case.seeds_provenance != {
                        "kind": "read-derived", "sample_alias": case.alias}:
                    # Only same-sample read-derived seeds may enter an arm.
                    raise ValueError("seed provenance is not read-derived same-sample")

    def _expected_inputs(self, cohort, ids):
        if (cohort == "physical" and self._manifest is not None
                and _physical_sample_ids(self._manifest) != set(ids)):
            raise ValueError("physical source identity differs from original manifest")
        if cohort == "synthetic" and self._cohort is not None:
            indexed = _synthetic_case_hashes(self._cohort)
            if set(indexed) != set(ids):
                raise ValueError("synthetic source identity differs from original cohort")
            return indexed
        attested = self._attested.get(cohort)
        if attested is not None:
            if set(attested) != set(ids):
                raise ValueError("attested input identity differs from cohort source")
            return attested
        return None

    def cases(self, cohort):
        return list(self._cases[cohort])

    def case(self, cohort, alias):
        return next(case for case in self._cases[cohort] if case.alias == alias)

    def public_view(self):
        view = {cohort: [case.public() for case in self._cases[cohort]]
                for cohort in COHORTS}
        _assert_public(view)
        return view


def _tool_rows(registry):
    data = exploratory_policy.checked(registry)
    tools = []
    for item in data["candidates"]:
        if not exploratory_policy.eligible(data, item["id"]):
            continue
        tools.append({"id": item["id"], "source_commit": item["source_commit"],
                      "adapter_commit": data["adapter_branch_commits"][item["id"]],
                      "image_sha256": item["image_sha256"]})
    if not tools:
        raise ValueError("no pilot/image-proof-certified PX assembler is eligible")
    return data, tools


def receipt_id(arm):
    return f"{arm['tool_id']}-{arm['cohort']}-{arm['alias']}"


def receipt_path(root, arm):
    return Path(root) / "receipts" / (receipt_id(arm) + ".json")


def attempt_path(root, arm, attempt):
    return Path(root) / "receipts" / "attempts" / (
        receipt_id(arm) + f".attempt-{attempt:03d}.json")


def index_path(root):
    return Path(root) / "receipts" / "index.json"


def arm_from_receipt(root, identifier):
    """Recover canonical arm identity from an indexed terminal receipt."""
    entries = _load_index(root)
    if identifier not in entries:
        return None
    path = Path(root) / "receipts" / (identifier + ".json")
    if not path.is_file() or sha256_file(path) != entries[identifier]:
        raise ValueError("PX receipt is unindexed or changed")
    data = json.loads(path.read_bytes())
    if data.get("schema") != RECEIPT_SCHEMA or data.get("terminal") is not True:
        raise ValueError("PX receipt is not terminal")
    return {key: data[key] for key in (
        "tool_id", "cohort", "alias", "input_sha256", "source_commit",
        "adapter_commit", "image_sha256")}


def _load_index(root):
    path = index_path(root)
    if not path.is_file():
        return {}
    data = json.loads(path.read_bytes())
    if data.get("schema") != INDEX_SCHEMA or not isinstance(data.get("entries"), dict):
        raise ValueError("PX receipt index is invalid")
    return data["entries"]


def _write_index(root, entries):
    return _atomic_json(index_path(root), {"schema": INDEX_SCHEMA, "entries": entries})


def _verify_receipt_data(data, arm):
    for key, expected in (("schema", RECEIPT_SCHEMA), ("tool_id", arm["tool_id"]),
                          ("cohort", arm["cohort"]), ("alias", arm["alias"]),
                          ("source_commit", arm["source_commit"]),
                          ("adapter_commit", arm["adapter_commit"]),
                          ("image_sha256", arm["image_sha256"])):
        if data.get(key) != expected:
            raise ValueError("PX receipt identity drift: " + key)
    if (data.get("qualifying") is not False or data.get("terminal") is not True
            or data.get("outcome") not in TERMINAL_OUTCOMES
            or data.get("input_sha256") != arm["input_sha256"]):
        raise ValueError("PX receipt is incomplete or not terminal")
    attempt = data.get("attempt", 1)
    if (not isinstance(attempt, int) or attempt < 1
            or attempt > MAX_INFRA_ATTEMPTS):
        raise ValueError("PX receipt attempt is invalid")
    if data["outcome"] == "success":
        if not SHA256.fullmatch(data.get("output_sha256") or ""):
            raise ValueError("successful PX receipt lacks hashed final MAX output")
    elif data.get("failure_reason") not in FAILURE_REASONS:
        raise ValueError("failed PX receipt lacks a classified reason")
    _assert_public(data)
    return data


def verify_receipt(root, arm):
    """Only a content-hashed, terminal, pin-bound receipt can end an arm."""
    path = receipt_path(root, arm)
    if not path.is_file():
        return None
    recorded = _load_index(root).get(receipt_id(arm))
    blob = path.read_bytes()
    if not isinstance(recorded, str) or sha256_file(path) != recorded:
        raise ValueError("PX case receipt is unindexed or changed")
    data = _verify_receipt_data(json.loads(blob), arm)
    attempt = data.get("attempt", 1)
    if attempt > 1:
        original = attempt_path(root, arm, 1)
        if not original.is_file():
            raise ValueError("versioned retry missing preserved original failure")
        prior = _verify_receipt_data(json.loads(original.read_bytes()), arm)
        if (prior.get("outcome") != "failure"
                or prior.get("failure_reason") not in INFRASTRUCTURE_FAILURE_REASONS):
            raise ValueError("only infrastructure failures may be retried")
    return data


def _write_canonical_receipt(root, arm, receipt):
    digest = _atomic_json(receipt_path(root, arm), receipt)
    entries = _load_index(root)
    entries[receipt_id(arm)] = digest
    _write_index(root, entries)
    return receipt


def record_outcome(root, arm, output_path, outcome, seconds=None, peak_rss=None,
                   failure_reason=None, runner_receipt_sha256=None):
    """Write an immutable terminal receipt; preserve original infra failures."""
    existing = verify_receipt(root, arm)
    attempt = 1
    if existing is not None:
        if (existing.get("outcome") == "failure"
                and existing.get("failure_reason") in INFRASTRUCTURE_FAILURE_REASONS
                and existing.get("attempt", 1) < MAX_INFRA_ATTEMPTS):
            original = attempt_path(root, arm, 1)
            if not original.is_file():
                _atomic_write(original, _json_bytes(existing))
            attempt = existing.get("attempt", 1) + 1
        else:
            raise ValueError("terminal PX arm may not be recomputed or overwritten")
    if outcome not in TERMINAL_OUTCOMES:
        raise ValueError("outcome must be terminal")
    if outcome == "success" and Path(output_path).name != MAX_ARTIFACT:
        raise ValueError("outcome must hash the final MAX consensus artifact")
    receipt = {
        "schema": RECEIPT_SCHEMA, "tool_id": arm["tool_id"],
        "cohort": arm["cohort"], "alias": arm["alias"],
        "source_commit": arm["source_commit"],
        "adapter_commit": arm["adapter_commit"],
        "image_sha256": arm["image_sha256"], "qualifying": False,
        "input_sha256": arm["input_sha256"], "outcome": outcome,
        "output_sha256": sha256_file(output_path) if outcome == "success" else None,
        "seconds": seconds, "peak_rss_bytes": peak_rss,
        "failure_reason": failure_reason,
        "runner_receipt_sha256": runner_receipt_sha256, "terminal": True,
        "attempt": attempt,
    }
    receipt.update(peak_ram_fields(arm))
    if outcome == "success" and (not isinstance(seconds, (int, float))
                                 or seconds <= 0):
        raise ValueError("successful arm needs a positive runtime")
    # An observed peak is retained for failed arms as well; null is honest
    # when monitoring never produced a measurement.
    if peak_rss is not None:
        if (isinstance(peak_rss, bool) or not isinstance(peak_rss, (int, float))
                or not math.isfinite(peak_rss) or peak_rss < 0):
            raise ValueError("observed peak RSS is invalid")
    if outcome == "failure" and failure_reason not in FAILURE_REASONS:
        raise ValueError("unclassified failure is never terminal")
    _assert_public(receipt)
    if attempt > 1:
        _atomic_json(attempt_path(root, arm, attempt), receipt)
    return _write_canonical_receipt(root, arm, receipt)


def build_plan(registry, source, root):
    """Order physical before synthetic for every eligible assembler."""
    data, tools = _tool_rows(registry)
    source.validate()
    arms, accepted_ids, pending = [], [], []
    # Founder order applies globally: every assembler finishes the 198 physical
    # cases before any assembler starts a 464-synthetic case.
    for cohort in COHORTS:
        for tool in tools:
            for case in source.cases(cohort):
                arm = {"tool_id": tool["id"], "cohort": cohort,
                       "alias": case.alias, "input_sha256": case.input_hashes(),
                       **{key: tool[key] for key in (
                           "source_commit", "adapter_commit", "image_sha256")}}
                arms.append(arm)
                receipt = verify_receipt(root, arm)
                retryable = (
                    isinstance(receipt, dict)
                    and receipt.get("outcome") == "failure"
                    and receipt.get("failure_reason") in INFRASTRUCTURE_FAILURE_REASONS
                    and receipt.get("attempt", 1) < MAX_INFRA_ATTEMPTS)
                if receipt is not None and not retryable:
                    accepted_ids.append(receipt_id(arm))
                else:
                    pending.append(arm)
    plan = {
        "schema": SCHEMA, "qualifying": False,
        "registry_sha256": sha256_file(registry),
        "frozen_seven_manifest_sha256": data["policy"]["frozen_seven_manifest_sha256"],
        "tools": [tool["id"] for tool in tools],
        "expected_counts": EXPECTED_COUNTS,
        "total_arms": len(arms), "accepted_arms": len(accepted_ids),
        "accepted_ids": accepted_ids,
        "pending_arms": len(pending), "pending": pending,
    }
    _assert_public(plan)
    return plan


def checkpoint_path(root):
    return Path(root) / "state" / "checkpoint.json"


def write_checkpoint(root, plan, completed):
    """Persist a verified snapshot; receipts remain the resume authority."""
    state = {"schema": CHECKPOINT_SCHEMA, "plan_sha256": _plan_digest(plan),
             "completed": list(completed)}
    _assert_public(state)
    return _atomic_json(checkpoint_path(root), state)


def resume(plan, root):
    """Reconcile a checkpoint with receipts; drift stops instead of guessing."""
    path = checkpoint_path(root)
    if not path.is_file():
        return plan["pending"]
    state = json.loads(path.read_bytes())
    if (state.get("schema") != CHECKPOINT_SCHEMA
            or state.get("plan_sha256") != _plan_digest(plan)):
        raise ValueError("PX checkpoint does not match its plan")
    completed = set(state.get("completed", []))
    known = set(plan["accepted_ids"]) | {receipt_id(arm) for arm in plan["pending"]}
    if not completed <= known:
        raise ValueError("PX checkpoint claims an unknown arm")
    return [arm for arm in plan["pending"] if receipt_id(arm) not in completed]


def _plan_digest(plan):
    """Hash only stable queue identity; pending shrinks as receipts accumulate."""
    stable = {key: plan[key] for key in (
        "schema", "qualifying", "registry_sha256",
        "frozen_seven_manifest_sha256", "tools", "expected_counts", "total_arms")}
    return hashlib.sha256(_json_bytes(stable)).hexdigest()


def admit_arm(registry, baseline, root, reserve_bytes):
    """Reuse the PR411 admission guard; never invent a looser budget."""
    data = exploratory_policy.checked(registry)
    if not MIN_RESERVE <= reserve_bytes <= MAX_RESERVE:
        raise ValueError("PX arm reservation must be 1-4 GiB")
    return exploratory_space.admit(data, baseline, root,
                                   baseline["image_store"], baseline["workspace"],
                                   reserve_bytes)


def posthoc_score(root, arm, scorer, expected_source_sha256, *,
                   output_dir=None, case=None):
    """Score only after the output is hashed; truth stays inside the scorer."""
    receipt = verify_receipt(root, arm)
    if receipt is None or receipt["outcome"] != "success":
        raise ValueError("only a terminal successful arm can be scored")
    if getattr(scorer, "source_sha256", None) != expected_source_sha256:
        raise ValueError("source-frozen scorer identity changed")
    kwargs = dict(alias=arm["alias"], cohort=arm["cohort"],
                  output_sha256=receipt["output_sha256"],
                  output_dir=output_dir, receipt=receipt, arm=arm, case=case)
    try:
        row = scorer.score(**kwargs)
    except TypeError:
        row = scorer.score(alias=arm["alias"], cohort=arm["cohort"],
                           output_sha256=receipt["output_sha256"])
    if (not isinstance(row, dict) or row.get("alias") != arm["alias"]
            or row.get("outcome") not in ("success", "failure")):
        raise ValueError("independent scorer returned an invalid row")
    # The comparable RAM metric comes from the immutable receipt, never from
    # the scorer; preserve null unless its sampler attests whole-container
    # scope with an explicit method and version.
    row.update(peak_ram_fields(receipt))
    row["peak_ram_observed_mib"] = peak_ram_observed_mib(receipt)
    _assert_public(row)
    return {"schema": RESULT_SCHEMA, "tool_id": arm["tool_id"],
            "source_commit": arm["source_commit"],
            "adapter_commit": arm["adapter_commit"],
            "image_sha256": arm["image_sha256"], "cohort": arm["cohort"],
            "expected_sample_count": EXPECTED_COUNTS[arm["cohort"]],
            "scorer_source_sha256": expected_source_sha256, "samples": [row]}


def write_results(root, arm, result):
    """Emit a publication-compatible, alias-only per-case results file."""
    _assert_public(result)
    path = Path(root) / "results" / (receipt_id(arm) + "-results.json")
    return path, _atomic_json(path, result)
