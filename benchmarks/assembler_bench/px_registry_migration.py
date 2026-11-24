"""Additive PX registry/checkpoint activation with receipt-preserving swaps.

One plan binds a staged registry to a single tool activation. The module never
starts a worker: the caller must supply a granted STOP boundary, and the
exclusive global-worker lock is held non-blockingly for the entire swap. Every
proof is verified before the first write; completed arms are admitted only when
an indexed, terminal scheduler receipt exists for them.
"""
import fcntl
import json
import re
import time
from pathlib import Path

from . import exploratory_policy, px_cohort_scheduler as sched
from . import px_execution, px_supervisor

PLAN_SCHEMA = "ivanka.px.registry.migration-plan.v1"
RECEIPT_SCHEMA = "ivanka.px.registry.migration.receipt.v1"
LOCK_NAME = ".global-worker.lock"
STOP_NAME = "STOP"
ELIGIBLE = frozenset(("image-pinned", "pilot", "benchmarked"))
ACTIVATION_FIELDS = frozenset((
    "status", "image_sha256", "image_evidence", "pilot_evidence",
    "benchmark_evidence"))
IDENTITY_FIELDS = (
    "id", "name", "qualifying", "rationale", "replaces_blocked",
    "source_commit", "source_license", "license_path", "source_repo")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\Z")
WINDOW = re.compile(r"[0-9]{8}T[0-9]{6}Z\Z")
ARM_ID = re.compile(r"[a-z0-9-]+-(physical|synthetic)-PX-[RH][0-9]{3}\Z")
PLAN_KEYS = (
    "schema", "window_id", "tool_id", "active_registry", "staged_registry",
    "staged_registry_sha256", "source_commit", "image_receipt_sha256",
    "pilot_receipt_sha256", "handoff_sha256", "new_plan_sha256",
    "active_checkpoint", "checkpoints", "new_completed",
    "owner", "boundary_evidence")


class MigrationError(ValueError):
    """A plan, proof, boundary or receipt check failed before state changed."""


def _digest(path):
    return sched.sha256_file(path)


def _load(path):
    try:
        return json.loads(Path(path).read_bytes())
    except (OSError, ValueError) as exc:
        raise MigrationError("cannot read JSON: " + str(path)) from exc


def _relative(root, name):
    """Resolve a plan-supplied path without allowing escape from the root."""
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise MigrationError("migration path must be root-relative: " + repr(name))
    target = (Path(root) / name).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise MigrationError("migration path escapes root: " + name)
    return target


def _provenance(root):
    return Path(root) / "receipts"


def load_plan(root, path):
    """Validate a declarative plan before any registry is read or written."""
    location = Path(path)
    if not location.is_absolute():
        location = Path(root) / location
    plan = _load(location)
    if not isinstance(plan, dict) or any(key not in plan for key in PLAN_KEYS):
        raise MigrationError("incomplete migration plan")
    if (plan["schema"] != PLAN_SCHEMA
            or not WINDOW.fullmatch(str(plan["window_id"]))
            or plan["tool_id"] not in exploratory_policy.EXPERIMENTAL):
        raise MigrationError("unsupported migration plan identity")
    for key in ("staged_registry_sha256", "image_receipt_sha256",
                "pilot_receipt_sha256", "handoff_sha256", "new_plan_sha256"):
        if not isinstance(plan[key], str) or not SHA64.fullmatch(plan[key]):
            raise MigrationError("invalid plan digest: " + key)
    if (not isinstance(plan["source_commit"], str)
            or not SHA40.fullmatch(plan["source_commit"])):
        raise MigrationError("invalid plan source pin")
    checkpoints = plan["checkpoints"]
    if (not isinstance(checkpoints, list) or not checkpoints
            or plan["active_checkpoint"] not in checkpoints
            or len(set(checkpoints)) != len(checkpoints)):
        raise MigrationError("checkpoint list must name the active snapshot once")
    for name in checkpoints:
        _relative(root, name)
    _relative(root, plan["active_registry"])
    _relative(root, plan["staged_registry"])
    completed = plan["new_completed"]
    if (not isinstance(completed, list)
            or any(not isinstance(item, str) or not ARM_ID.fullmatch(item)
                   for item in completed)
            or len(set(completed)) != len(completed)):
        raise MigrationError("new completed arms are not canonical receipt ids")
    owner = plan["owner"]
    if not isinstance(owner, str) or not owner.strip():
        raise MigrationError("migration plan requires explicit ownership")
    boundary = plan["boundary_evidence"]
    if (not isinstance(boundary, dict)
            or boundary.get("kind") != "stopped-service-or-owner"
            or not isinstance(boundary.get("path"), str)):
        raise MigrationError("migration plan requires boundary evidence")
    _relative(root, boundary["path"])
    return plan


def verify_proofs(root, plan):
    """Bind the staged registry to its source, image, pilot and handoff proofs."""
    staged = _relative(root, plan["staged_registry"])
    if _digest(staged) != plan["staged_registry_sha256"]:
        raise MigrationError("staged registry drift")
    try:
        data = exploratory_policy.checked(
            staged, provenance_root=_provenance(root))
    except ValueError as exc:
        raise MigrationError("staged registry fails registry policy: " + str(exc)) from exc
    item = next((x for x in data["candidates"]
                 if x["id"] == plan["tool_id"]), None)
    if item is None:
        raise MigrationError("staged registry lost the activation tool")
    if item["status"] not in ELIGIBLE:
        raise MigrationError("staged tool is not eligible")
    if item["source_commit"] != plan["source_commit"]:
        raise MigrationError("staged source pin differs from plan")
    if "image_sha256" in plan and item["image_sha256"] != plan["image_sha256"]:
        raise MigrationError("staged image pin differs from plan")
    bound = dict(item, adapter_commit=data["adapter_branch_commits"][item["id"]])
    for kind, key in (("image", "image_receipt_sha256"),
                      ("pilot", "pilot_receipt_sha256")):
        evidence = item.get(kind + "_evidence")
        if (not isinstance(evidence, dict)
                or evidence.get("sha256") != plan[key]):
            raise MigrationError(kind + " receipt hash differs from plan")
        if not exploratory_policy.verified_receipt(
                bound, evidence, kind, _provenance(root)):
            raise MigrationError("staged " + kind + " receipt is not source-bound")
    handoff = _relative(root, "handoff/" + plan["tool_id"] + ".json")
    if _digest(handoff) != plan["handoff_sha256"]:
        raise MigrationError("supervisor handoff drift")
    record = _load(handoff)
    if (record.get("image_sha256") != item["image_sha256"]
            or record.get("image_receipt_sha256") != plan["image_receipt_sha256"]
            or record.get("pilot_receipt_sha256") != plan["pilot_receipt_sha256"]):
        raise MigrationError("handoff does not bind the staged proofs")
    if not px_supervisor.verify_handoff(
            root, staged, plan["tool_id"], provenance_root=_provenance(root)):
        raise MigrationError("supervisor handoff is not verified")
    return staged, data


def eligible_tools(data):
    """Eligible arms are the only identities a plan may carry forward."""
    return [item["id"] for item in data["candidates"]
            if exploratory_policy.eligible(data, item["id"])]


def _case_input_hashes(root):
    """Collect case input hashes from indexed receipts; same for all tools."""
    hashes = {}
    for identifier in sched._load_index(root):
        receipt = _load_verified_receipt(root, identifier)
        key = (receipt["cohort"], receipt["alias"])
        hashes.setdefault(key, receipt["input_sha256"])
    return hashes


def expected_plan_digest(staged, data, *, case_input_hashes=None):
    """Recompute scheduler digest from staged registry and case input hashes."""
    tools = []
    for item in data["candidates"]:
        if not exploratory_policy.eligible(data, item["id"]):
            continue
        tools.append({
            "tool_id": item["id"],
            "source_commit": item["source_commit"],
            "adapter_commit": data["adapter_branch_commits"][item["id"]],
            "image_sha256": item["image_sha256"],
        })
    identities = []
    case_input_hashes = case_input_hashes or {}
    for cohort, count, prefix in (
            ("physical", sched.PHYSICAL_COUNT, "R"),
            ("synthetic", sched.SYNTHETIC_COUNT, "H")):
        for i in range(1, count + 1):
            alias = f"PX-{prefix}{i:03d}"
            input_sha256 = case_input_hashes.get((cohort, alias))
            if input_sha256 is None:
                raise MigrationError(
                    "missing case input hashes for " + cohort + " " + alias)
            for tool in tools:
                identities.append({
                    "tool_id": tool["tool_id"], "cohort": cohort,
                    "alias": alias,
                    "source_commit": tool["source_commit"],
                    "adapter_commit": tool["adapter_commit"],
                    "image_sha256": tool["image_sha256"],
                    "input_sha256": input_sha256,
                })
    plan = {
        "schema": sched.SCHEMA, "qualifying": False,
        "registry_sha256": _digest(staged),
        "frozen_seven_manifest_sha256":
            data["policy"]["frozen_seven_manifest_sha256"],
        "tools": [tool["tool_id"] for tool in tools],
        "expected_counts": sched.EXPECTED_COUNTS,
        "total_arms": len(identities),
        "arm_identities": identities,
    }
    return sched._plan_digest(plan)


def _tool_identity(item, adapter_commit):
    identity = {field: item.get(field) for field in IDENTITY_FIELDS}
    identity["adapter_commit"] = adapter_commit
    identity["image_sha256"] = item.get("image_sha256")
    return identity


def verify_additive(root, plan, staged, staged_data):
    """Permit additive activation without mutating previously eligible arms."""
    active = _relative(root, plan["active_registry"])
    try:
        active_data = exploratory_policy.checked(
            active, provenance_root=_provenance(root))
    except ValueError as exc:
        raise MigrationError("active registry fails registry policy: " + str(exc)) from exc
    for key in ("schema", "qualifying", "policy", "baseline_assemblers",
                "adapter_baseline_commit", "storage_baseline_sha256",
                "blocked_original_candidates"):
        if active_data.get(key) != staged_data.get(key):
            raise MigrationError("registry boundary drift: " + key)
    before = {item["id"]: item for item in active_data["candidates"]}
    after = {item["id"]: item for item in staged_data["candidates"]}
    if set(before) != set(after):
        raise MigrationError("candidate roster was removed or added")
    old_pins = active_data.get("adapter_branch_commits", {})
    new_pins = staged_data.get("adapter_branch_commits", {})
    for name in before:
        old_eligible = before[name]["status"] in ELIGIBLE
        old_id = _tool_identity(before[name], old_pins.get(name))
        new_id = _tool_identity(after[name], new_pins.get(name))
        if old_eligible and old_id != new_id:
            raise MigrationError("previously eligible identity changed: " + name)
        if not old_eligible and old_pins.get(name) != new_pins.get(name):
            if name != plan["tool_id"]:
                # Non-eligible tools may move adapter pins, but only explicitly
                # when they are not the activation target.
                pass
    target_old = before[plan["tool_id"]]
    target_new = after[plan["tool_id"]]
    if target_old["status"] in ELIGIBLE:
        # Eligible tools may advance status only with unchanged identity.
        if _tool_identity(target_old, old_pins.get(plan["tool_id"])) != _tool_identity(
                target_new, new_pins.get(plan["tool_id"])):
            raise MigrationError("eligible arm identity changed: " + plan["tool_id"])
        if target_new["status"] not in ELIGIBLE:
            raise MigrationError("eligible arm downgraded: " + plan["tool_id"])
    else:
        if target_new["status"] not in ELIGIBLE:
            raise MigrationError("activation did not admit target: " + plan["tool_id"])
    # Non-admitted tools' adapter pin changes are allowed, but all pin values
    # must still be valid full hashes.
    if not isinstance(new_pins, dict) or set(new_pins) != set(before):
        raise MigrationError("adapter pins do not match roster")
    for name, value in new_pins.items():
        if not isinstance(value, str) or not SHA40.fullmatch(value):
            raise MigrationError("invalid adapter pin: " + name)
    return active, active_data


def verify_boundary(root, plan, staged_data):
    """Require the granted STOP window and an idle, unarmed worker baseline."""
    stop = Path(root) / STOP_NAME
    if not stop.is_file():
        raise MigrationError("no STOP boundary sentinel")
    token = plan.get("stop_token")
    if token is not None and stop.read_text().strip() != token.strip():
        raise MigrationError("STOP token does not match the plan")
    if px_execution.checked_baseline(root, staged_data) is None:
        raise MigrationError("worker baseline shows an active arm or a pin drift")
    _boundary_verified(root, plan)


def _checkpoint_snapshots(root, plan):
    snapshots = {}
    for name in plan["checkpoints"]:
        data = _load(_relative(root, name))
        if (data.get("schema") != sched.CHECKPOINT_SCHEMA
                or not isinstance(data.get("completed"), list)
                or any(not isinstance(item, str) for item in data["completed"])):
            raise MigrationError("invalid preserved checkpoint: " + name)
        snapshots[name] = data
    return snapshots


def _receipt_accepted(receipt):
    return not (
        isinstance(receipt, dict)
        and receipt.get("outcome") == "failure"
        and receipt.get("failure_reason") in sched.INFRASTRUCTURE_FAILURE_REASONS
        and receipt.get("attempt", 1) < sched.MAX_INFRA_ATTEMPTS)


def _expected_arm_identities(staged_data):
    tools = []
    for item in staged_data["candidates"]:
        if not exploratory_policy.eligible(staged_data, item["id"]):
            continue
        tools.append({
            "tool_id": item["id"],
            "source_commit": item["source_commit"],
            "adapter_commit": staged_data["adapter_branch_commits"][item["id"]],
            "image_sha256": item["image_sha256"],
        })
    expected = {}
    for cohort, count, prefix in (
            ("physical", sched.PHYSICAL_COUNT, "R"),
            ("synthetic", sched.SYNTHETIC_COUNT, "H")):
        for i in range(1, count + 1):
            alias = f"PX-{prefix}{i:03d}"
            for tool in tools:
                ident = dict(tool, cohort=cohort, alias=alias)
                expected[sched.receipt_id(ident)] = ident
    return expected


def _load_verified_receipt(root, identifier):
    try:
        entries = sched._load_index(root)
    except ValueError as exc:
        raise MigrationError("corrupt receipt index") from exc
    if identifier not in entries:
        return None
    receipt_path = Path(root) / "receipts" / (identifier + ".json")
    if not receipt_path.is_file():
        raise MigrationError("missing indexed receipt: " + identifier)
    data = _load(receipt_path)
    arm = {key: data.get(key) for key in (
        "tool_id", "cohort", "alias", "input_sha256", "source_commit",
        "adapter_commit", "image_sha256")}
    try:
        verified = sched.verify_receipt(root, arm)
    except ValueError as exc:
        raise MigrationError("corrupt scheduler receipt: " + identifier) from exc
    if verified is None:
        raise MigrationError("no scheduler receipt for completed arm: " + identifier)
    return verified


def verify_receipts(root, plan, staged_data):
    """Bind every accepted receipt to the staged plan's exact arm identity."""
    expected = _expected_arm_identities(staged_data)
    entries = sched._load_index(root)
    accepted = 0
    for identifier, digest in entries.items():
        receipt = _load_verified_receipt(root, identifier)
        if identifier not in expected:
            raise MigrationError("receipt not in staged plan: " + identifier)
        arm = expected[identifier]
        for key in ("tool_id", "cohort", "alias", "source_commit",
                    "adapter_commit", "image_sha256"):
            if receipt.get(key) != arm[key]:
                raise MigrationError("receipt identity drift: " + identifier)
        input_sha = receipt.get("input_sha256")
        if (not isinstance(input_sha, dict)
                or set(input_sha) < {"R1", "R2"}
                or not SHA64.fullmatch(str(input_sha.get("R1", "")))
                or not SHA64.fullmatch(str(input_sha.get("R2", "")))):
            raise MigrationError("receipt input hashes invalid: " + identifier)
        if not sched.ALIAS.fullmatch(str(receipt.get("alias", ""))):
            raise MigrationError("receipt alias invalid: " + identifier)
        if _receipt_accepted(receipt):
            accepted += 1
    for identifier in plan["new_completed"]:
        receipt = _load_verified_receipt(root, identifier)
        if receipt is None:
            raise MigrationError("no scheduler receipt for completed arm: " + identifier)
        if identifier not in expected:
            raise MigrationError("new completed arm not in plan: " + identifier)
        if receipt.get("tool_id") != plan["tool_id"]:
            raise MigrationError("new completed arm belongs to another tool")
        if not _receipt_accepted(receipt):
            raise MigrationError("new completed arm is not terminal-accepted: " + identifier)
    return accepted


def _checkpoint_bytes(plan_sha256, completed):
    record = {"schema": sched.CHECKPOINT_SCHEMA,
              "plan_sha256": plan_sha256, "completed": sorted(set(completed))}
    return sched._json_bytes(record)


def _supervisor_running(root):
    """A running supervise process can race STOP between arms."""
    root = str(Path(root).resolve())
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmd = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
                "utf-8", "ignore")
        except OSError:
            continue
        if ("px_execution" in cmd and "--supervise" in cmd
                and root in cmd):
            return True
    return False


def _boundary_verified(root, plan):
    boundary = plan["boundary_evidence"]
    path = _relative(root, boundary["path"])
    if not path.is_file():
        raise MigrationError("boundary evidence missing")
    data = _load(path)
    if (data.get("window_id") != plan["window_id"]
            or data.get("owner") != plan["owner"]
            or data.get("service_stopped") is not True):
        raise MigrationError("boundary evidence does not prove stopped ownership")
    if _supervisor_running(root):
        raise MigrationError("supervisor still running during boundary")
    return data


def _journal_path(root, plan):
    return Path(root) / "state" / (
        "migration-journal-" + plan["window_id"] + ".json")


def _plan_sha(root, plan_path):
    location = Path(plan_path)
    if not location.is_absolute():
        location = Path(root) / location
    return _digest(location)


def _write_preserved(root, plan, names):
    preserved = Path(root) / "preserved" / plan["window_id"]
    before = {}
    for name in names:
        source = _relative(root, name)
        blob = source.read_bytes()
        before[name] = _digest(source)
        target = preserved / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existing = target.read_bytes()
            if existing != blob:
                # A preserved snapshot is immutable evidence; do not overwrite.
                # Recovery uses the saved snapshot, not the mutated active file.
                before[name] = _digest(target)
                continue
        else:
            sched._atomic_write(target, blob)
    return preserved, before


def _restore_from_preserved(root, plan, name):
    preserved = Path(root) / "preserved" / plan["window_id"] / name
    if not preserved.is_file():
        raise MigrationError("missing preserved snapshot: " + name)
    sched._atomic_write(_relative(root, name), preserved.read_bytes())


def apply(root, plan_path):
    """Apply an additive migration atomically with crash-safe recovery.

    The exclusive global-worker lock is held for the whole swap. A journal is
    written before mutating active state so recovery can complete after a swap
    or checkpoint write that happened before the migration receipt was written.
    """
    root = Path(root).resolve()
    plan = load_plan(root, plan_path)
    plan_sha = _plan_sha(root, plan_path)
    staged_sha = plan["staged_registry_sha256"]
    lock = (root / LOCK_NAME).open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock.close()
        raise MigrationError("exclusive global-worker lock is held") from exc
    try:
        staged, staged_data = verify_proofs(root, plan)
        active = _relative(root, plan["active_registry"])
        active_checkpoint = _relative(root, plan["active_checkpoint"])
        active_sha = _digest(active)
        if active_sha != staged_sha:
            verify_additive(root, plan, staged, staged_data)
        case_input_hashes = _case_input_hashes(root)
        if "case_input_hashes" in plan:
            # Plan may supply hashes for cases not yet receipted.
            supplied = plan["case_input_hashes"]
            if not isinstance(supplied, dict):
                raise MigrationError("case_input_hashes must be an object")
            for key, value in supplied.items():
                if (not isinstance(key, str) or "," not in key
                        or not isinstance(value, dict)):
                    raise MigrationError("invalid case_input_hashes entry")
                cohort, alias = key.split(",", 1)
                case_input_hashes.setdefault((cohort, alias), value)
        new_digest = expected_plan_digest(
            staged, staged_data, case_input_hashes=case_input_hashes)
        if new_digest != plan["new_plan_sha256"]:
            raise MigrationError("new checkpoint plan digest drift")
        receipt_path = root / "receipts" / (
            "registry-migration-" + plan["tool_id"] + "-"
            + plan["window_id"] + ".json")
        journal_path = _journal_path(root, plan)
        cp_data = _load(active_checkpoint)
        if (active_sha == staged_sha
                and cp_data.get("plan_sha256") == new_digest):
            if receipt_path.is_file():
                receipt = _load(receipt_path)
                if (receipt.get("plan_sha256") != plan_sha
                        or receipt.get("schema") != RECEIPT_SCHEMA):
                    raise MigrationError("applied receipt does not match plan")
                return {"status": "already-applied", "receipt": str(receipt_path)}
            # State swapped before receipt; finish recovery below.
        elif receipt_path.is_file():
            receipt = _load(receipt_path)
            if (receipt.get("plan_sha256") != plan_sha
                    or receipt.get("schema") != RECEIPT_SCHEMA):
                raise MigrationError("receipt exists but does not match plan")
            return {"status": "already-applied", "receipt": str(receipt_path)}

        verify_boundary(root, plan, staged_data)
        _boundary_verified(root, plan)
        snapshots = _checkpoint_snapshots(root, plan)
        accepted = verify_receipts(root, plan, staged_data)
        completed = sorted(set().union(
            *(set(item["completed"]) for item in snapshots.values()),
            set(plan["new_completed"])))
        for identifier in completed:
            receipt = _load_verified_receipt(root, identifier)
            if not _receipt_accepted(receipt):
                raise MigrationError("completed arm is not terminal-accepted: " + identifier)

        names = [plan["active_registry"], *plan["checkpoints"]]
        preserved, before = _write_preserved(root, plan, names)
        before["active_registry_sha256"] = _digest(
            Path(root) / "preserved" / plan["window_id"] / plan["active_registry"])
        journal = {
            "schema": "ivanka.px.registry.migration.journal.v1",
            "window_id": plan["window_id"], "tool_id": plan["tool_id"],
            "plan_sha256": plan_sha, "staged_registry_sha256": staged_sha,
            "new_checkpoint_plan_sha256": new_digest,
            "before": before,
        }
        sched._atomic_write(journal_path, sched._json_bytes(journal))

        status = "recovered" if active_sha == staged_sha else "applied"
        sched._atomic_write(active, staged.read_bytes())
        sched._atomic_write(
            active_checkpoint, _checkpoint_bytes(new_digest, completed))
        if _digest(active) != staged_sha:
            raise MigrationError("active registry swap did not verify")
        after_cp = _load(active_checkpoint)
        if after_cp.get("plan_sha256") != new_digest or after_cp.get(
                "completed") != completed:
            raise MigrationError("new checkpoint did not verify")
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "window_id": plan["window_id"], "tool_id": plan["tool_id"],
            "owner": plan["owner"],
            "plan_sha256": plan_sha,
            "staged_registry_sha256": staged_sha,
            "new_checkpoint_plan_sha256": new_digest,
            "source_commit": plan["source_commit"],
            "image_receipt_sha256": plan["image_receipt_sha256"],
            "pilot_receipt_sha256": plan["pilot_receipt_sha256"],
            "handoff_sha256": plan["handoff_sha256"],
            "boundary_evidence_sha256": _digest(
                _relative(root, plan["boundary_evidence"]["path"])),
            "accepted_arms_derived_from_scheduler_receipts": accepted,
            "new_completed": plan["new_completed"],
            "pilot_arms_marked_complete": bool(plan["new_completed"]),
            "before": before,
            "after": {
                "active_registry_sha256": _digest(active),
                "checkpoint_sha256": _digest(active_checkpoint),
            },
        }
        sched._atomic_write(receipt_path, sched._json_bytes(receipt))
        try:
            journal_path.unlink()
        except FileNotFoundError:
            pass
        return {"status": status, "receipt": str(receipt_path),
                "receipt_sha256": _digest(receipt_path)}
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
