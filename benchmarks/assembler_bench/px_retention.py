"""Bounded, fail-closed artifact retention for PX cohorts.

Receipts, final MAX outputs, results, diagnostics and their SHA-256 sidecars are
protected and never removed. Disposable scratch and known disposable scratch
archives may be reclaimed only after diagnostics are complete, final MAX is
preserved outside scratch, and hashes are revalidated immediately before
deletion. Proven-dead terminal failures retain their final files and logs; infrastructure
stops and unproven teardown preserve scratch. Storage is accounted from real
measurements, never from an invented project ceiling; measured usage is never
a licence to discard evidence.
Lossless table compression is inherited from the common ``terminal_retire``
policy through the sealed, dead-container ``retire_finished_arm`` path only;
receipt-only bulk reclaim has no seal or liveness proof and never compresses.
"""
import fcntl
import json
import os
import shutil
import subprocess
from pathlib import Path

from benchmarks.retained_artifacts import (
    _promotion_plan, promote_finals, remove_visuals, seal_terminal_evidence, terminal_retire)

from . import exploratory_space
from . import px_cohort_scheduler as sched

SCHEMA = "ivanka.px.retention.plan.v1"
DISPOSABLE_DIRS = frozenset(("scratch", "tmp"))
# Post-measurement MiCall scratch archives are disposable only after final MAX
# and complete diagnostics are preserved; they are never removed before that.
DISPOSABLE_FILES = frozenset(("scratch.tar.gz", "scratch.tgz"))
INFRASTRUCTURE_REASONS = frozenset(("disk_stop", "measurement_unavailable"))
DIAGNOSTICS_SCHEMA = "ivanka.px.diagnostics.v3"
METRICS = ("final_max", "canonical_micall", "exact_coverage")


def arm_output_dir(root, arm):
    """The per-arm results mount used by the supervised runner."""
    return Path(root) / "outputs" / (arm["tool_id"] + "-" + arm["alias"])


def is_infrastructure(receipt):
    """Distinguish infrastructure disk failures from assembler outcomes."""
    return (isinstance(receipt, dict)
            and receipt.get("outcome") == "failure"
            and receipt.get("failure_reason") in INFRASTRUCTURE_REASONS)


def _verified_json(path):
    target = Path(path)
    sidecar = Path(str(target) + ".sha256")
    if not target.is_file() or not sidecar.is_file():
        return None
    digest = sched.sha256_file(target)
    if sidecar.read_text().strip() != digest:
        raise ValueError("attested record hash mismatch: " + str(target))
    return json.loads(target.read_bytes())


def diagnostics_complete(record):
    """Complete means every metric is extracted or explicitly unavailable."""
    if not isinstance(record, dict) or record.get("schema") != DIAGNOSTICS_SCHEMA:
        return False
    metrics = record.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(METRICS):
        return False
    for name in METRICS:
        metric = metrics.get(name)
        if not isinstance(metric, dict):
            return False
        status = metric.get("status")
        reason = metric.get("unavailable_reason")
        if status == "unavailable":
            if not isinstance(reason, str) or not reason:
                return False
        elif status == "extracted":
            if reason is not None or "values" not in metric:
                return False
        else:
            return False
    return True


def promote_final_max(root, arm, receipt):
    """Keep a verified final MAX outside scratch before scratch can be removed."""
    output_dir = arm_output_dir(root, arm)
    target = output_dir / sched.MAX_ARTIFACT
    if (target.is_file()
            and sched.sha256_file(target) == receipt["output_sha256"]):
        return target
    if target.exists():
        raise ValueError("final MAX artifact changed since receipt")
    source = output_dir / "scratch" / sched.MAX_ARTIFACT
    if (not source.is_file()
            or sched.sha256_file(source) != receipt["output_sha256"]):
        raise ValueError("no verified final MAX to preserve before retention")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name("." + target.name + ".retention.part")
    shutil.copyfile(source, temporary)
    if sched.sha256_file(temporary) != receipt["output_sha256"]:
        temporary.unlink(missing_ok=True)
        raise ValueError("final MAX copy failed hash verification")
    temporary.replace(target)
    return target


def reclaimable_receipt(root, arm):
    """Return receipt only when complete diagnostics justify disposal."""
    receipt = sched.verify_receipt(root, arm)
    if receipt is None:
        raise ValueError("retention requires a verified terminal receipt")
    if receipt["outcome"] != "success" or is_infrastructure(receipt):
        return None  # Preserve failed and infrastructure attempts intact.
    promote_final_max(root, arm, receipt)
    ident = sched.receipt_id(arm)
    results = _verified_json(Path(root) / "results" / (ident + "-results.json"))
    diagnostics = _verified_json(Path(root) / "diagnostics" / (ident + ".json"))
    if results is None or diagnostics is None:
        raise ValueError("diagnostics and results must be attested before retention")
    if not diagnostics_complete(diagnostics):
        raise ValueError("diagnostics are not complete enough for retention")
    if diagnostics.get("output_sha256") != receipt["output_sha256"]:
        raise ValueError("diagnostics are not bound to the terminal output")
    return receipt


def _observed_dead(root, cid):
    """Recheck the exact reaped CID in the dedicated store, never kill anything."""
    from .exploratory_runtime import pilot
    if Path(root).resolve() != pilot.ROOT:
        return False
    env = {**os.environ, "CONTAINERS_STORAGE_CONF": str(pilot.ROOT / "storage.conf")}
    try:
        graph = pilot.command(["podman", "info", "--format", "{{.Store.GraphRoot}}"], env)
        if graph != pilot.STORE:
            return False
        listed = pilot.command(["podman", "ps", "-a", "--no-trunc",
                                "--format", "{{.ID}}"], env)
        return cid not in listed.splitlines()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return False


def retire_finished_arm(root, arm, receipt, report):
    """Use common terminal retirement only with current guarded-launcher proof."""
    root = Path(root).resolve()
    cid = report.get("retention_container_id")
    log_hash = report.get("runner_receipt_sha256")
    if (not sched.SHA256.fullmatch(cid or "")
            or not sched.SHA256.fullmatch(log_hash or "")
            or receipt.get("runner_receipt_sha256") != log_hash
            or is_infrastructure(receipt)):
        return None
    output = arm_output_dir(root, arm)
    if (not output.is_dir() or output.is_symlink()
            or not output.resolve().is_relative_to(root / "outputs")):
        return None
    with (root / ".global-worker.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        if not _observed_dead(root, cid):
            return None
        if sched.verify_receipt(root, arm) != receipt:
            raise ValueError("terminal PX receipt changed before retirement")
        source = {"receipt": sched.sha256_file(sched.receipt_path(root, arm)),
                  "launcher_log": log_hash, "launcher_container_id": cid}
        evidence = {"launcher_container_id": cid}
        if receipt["outcome"] == "success":
            if reclaimable_receipt(root, arm) != receipt:
                raise ValueError("terminal PX results are not reclaimable")
            ident = sched.receipt_id(arm)
            for path in (root / "results" / (ident + "-results.json"),
                         root / "diagnostics" / (ident + ".json")):
                source[path.name] = sched.sha256_file(path)
            # Hash the same canonical outputs that the common retention policy
            # verifies, without executing or changing any scientific measurement.
            from benchmarks.podman_full_micall import score_outputs
            evidence["metrics"] = score_outputs(output, None)
            if evidence["metrics"]["outputs"][sched.MAX_ARTIFACT].get("sha256") != receipt["output_sha256"]:
                raise ValueError("terminal PX consensus differs from receipt")
        else:
            evidence["failure"] = receipt
        evidence_path = output / "terminal_evidence.json"
        # Keep the initial seal immutable on retries; the common policy checks
        # its digest and exact source binding before any further removal.
        if not evidence_path.exists() and not evidence_path.is_symlink():
            seal_terminal_evidence(output, evidence, source)
        # Shared-codec compression runs inside the common policy only after
        # the dead-container probe and this sealed receipt are verified, so
        # PX and P1 completed arms get identical shrink-only post-core behaviour.
        return terminal_retire(output, evidence_path=evidence_path,
                               container_dead=lambda: _observed_dead(root, cid),
                               source_hashes=source)


def _disposable_entries(root, arm):
    output_dir = arm_output_dir(root, arm)
    entries = []
    for name in sorted(DISPOSABLE_DIRS):
        target = output_dir / name
        if target.is_dir() and not target.is_symlink():
            entries.append(target)
    for name in sorted(DISPOSABLE_FILES):
        target = output_dir / name
        if target.is_file() and not target.is_symlink():
            entries.append(target)
    return entries


def _assert_disposable(target, root, arm):
    """Refuse path escapes, symlinks and anything outside the arm policy."""
    resolved = Path(target).resolve()
    base = Path(root).resolve()
    output_dir = arm_output_dir(base, arm).resolve()
    if not resolved.is_relative_to(output_dir) or resolved == output_dir:
        raise ValueError("retention target escaped the arm output directory")
    name = resolved.name
    if Path(target).is_symlink():
        raise ValueError("retention target is a symlink")
    if name in DISPOSABLE_DIRS and resolved.is_dir():
        return resolved
    if name in DISPOSABLE_FILES and resolved.is_file():
        return resolved
    raise ValueError("retention target is not disposable")


def _remove(target):
    if target.is_dir():
        if target.name == "scratch":
            promote_finals(target.parent)
        shutil.rmtree(target)
    else:
        target.unlink()
    remove_visuals(target.parent)


def reclaim_one(root, arm, target=None):
    """Reclaim one disposable artifact after immediate revalidation."""
    base = Path(root).resolve()
    if reclaimable_receipt(base, arm) is None:
        return None
    candidates = _disposable_entries(base, arm)
    if target is None:
        if not candidates:
            return None
        removed = []
        for item in candidates:
            # Revalidate before every destructive action; never trust a stale plan.
            if reclaimable_receipt(base, arm) is None:
                raise ValueError("retention became ineligible during deletion")
            resolved = _assert_disposable(item, base, arm)
            _remove(resolved)
            removed.append(str(resolved))
        return {"removed": removed, "reason": "diagnostics_measured_hashes_verified"}
    resolved = _assert_disposable(target, base, arm)
    if resolved not in [path.resolve() for path in candidates]:
        raise ValueError("scratch path is not a verified disposable target")
    _remove(resolved)
    return {"removed": [str(resolved)],
            "reason": "diagnostics_measured_hashes_verified"}


def _arm_from_receipt(receipt):
    return {key: receipt[key] for key in (
        "tool_id", "cohort", "alias", "source_commit", "adapter_commit",
        "image_sha256", "input_sha256")}


def plan(root, arms, allocated=None):
    """Compute a hash-verified retention plan without removing any artifact."""
    measure = allocated or exploratory_space.allocated
    base = Path(root).resolve()
    reclaim, preserved, infra = [], [], []
    total = measure(base)
    scratch_bytes = 0
    for arm in arms:
        receipt = sched.verify_receipt(base, arm)
        if receipt is None:
            continue
        if is_infrastructure(receipt):
            infra.append({"alias": arm["alias"], "cohort": arm["cohort"],
                          "failure_reason": receipt["failure_reason"]})
        if receipt["outcome"] != "success" or is_infrastructure(receipt):
            preserved.append({"alias": arm["alias"], "cohort": arm["cohort"],
                              "tool_id": arm["tool_id"]})
            continue
        if reclaimable_receipt(base, arm) is None:
            continue
        entry_arm = _arm_from_receipt(receipt)
        for target in _disposable_entries(base, arm):
            size = measure(target) if target.is_dir() else target.stat().st_blocks * 512
            if target.name == "scratch":
                for source, dest in _promotion_plan(target.parent) or ():
                    if not dest.exists():
                        size -= (measure(source) if source.is_dir()
                                 else source.stat().st_blocks * 512)
            scratch_bytes += max(0, size)
            reclaim.append({**entry_arm, "target": str(target.resolve()),
                            "kind": "dir" if target.is_dir() else "file"})
    retained = total - scratch_bytes
    return {
        "schema": SCHEMA,
        "total_bytes": total, "reclaimable_bytes": scratch_bytes,
        "projected_retained_bytes": retained,
        "reclaim": reclaim, "preserved_attempts": preserved,
        "infrastructure_failures": infra,
    }


def apply(root, decision):
    """Revalidate and remove only currently eligible disposable artifacts."""
    if not isinstance(decision, dict) or decision.get("schema") != SCHEMA:
        raise ValueError("retention decision schema mismatch")
    base = Path(root).resolve()
    removed = []
    for entry in decision.get("reclaim", []):
        arm = {key: entry[key] for key in (
            "tool_id", "cohort", "alias", "source_commit", "adapter_commit",
            "image_sha256", "input_sha256")}
        # Never trust plan freshness: recheck receipt, hashes and completeness.
        if reclaimable_receipt(base, arm) is None:
            raise ValueError("stale retention plan: arm no longer reclaimable")
        target = _assert_disposable(entry["target"], base, arm)
        current = [path.resolve() for path in _disposable_entries(base, arm)]
        if target not in current:
            raise ValueError("stale retention plan: target not disposable")
        _remove(target)
        removed.append(str(target))
    return removed
