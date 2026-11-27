#!/usr/bin/env python3
"""PenguiN NONQUALIFYING pilot migration — deployed-guard imports, durable txn.

DO NOT APPLY TO THE LIVE ROOT. Dry-run by default; --apply needs explicit
operator authorization and all gates. --recover is strict and idempotent.

Fixes operator inspection v2 (SHA 00f2ae78): imports come ONLY from the deployed
PR536 guard tree; module __file__, live run env/HEAD and real ALIVE are checked;
a pinned sanitized PATH including actual podman is used for every guard command;
all five targets are journaled before/after with fsynced atomic writes; existing
evidence mismatch and unrelated changes fail closed; recovery never silently
drops a journal or rolls back a committed/ambiguous state.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROPOSAL = HERE
# PR536 is DEPLOYED (watchdog and PX supervisor PYTHONPATH both point here).
DEPLOYED_GUARD = Path("/workspace/ivanka-guard-pr536-staged-20261126")
sys.path[:0] = [str(DEPLOYED_GUARD), str(DEPLOYED_GUARD / "benchmarks")]
from assembler_bench import exploratory_policy as pol  # noqa: E402
from assembler_bench import px_cohort_scheduler as sched  # noqa: E402
from assembler_bench import px_execution, px_registry_migration, px_supervisor  # noqa: E402
from fail_closed_guard import heartbeat, lease, proc, watchdog_contract  # noqa: E402

LIVE_ROOT = Path("/workspace/ivanka-exploratory-ten-20261121")
REG_NAME = "private-frozen-ten-pilot-registry-20gib-20261124.json"
PROPOSED_REG = PROPOSAL / "proposed-registry-penguin-pilot-20261126.json"
PILOT_SRC = PROPOSAL / "proposed-receipts/pilot-penguin-paired-canonical-proposed-20261126.json"
IMAGE_SRC = PROPOSAL / "proposed-receipts/image-penguin-frozen-8458f9e5-8e7c55a3.json"
PILOT_NAME = "pilot-penguin-paired-canonical-20261124.json"
IMAGE_NAME = "image-penguin-frozen-8458f9e5-8e7c55a3.json"
TXN = ".penguin-txn"
SANITIZED_PATH = (
    "/home/lubko/.local/bin:"
    "/var/guix/profiles/per-user/puser/guix-profile/bin:"
    "/var/guix/profiles/per-user/puser/guix-profile/sbin:"
    "/usr/local/bin:/usr/bin:/bin"
)

EXPECTED = {
    "registry": "98de47a3eb76b45d3c09b4f3aa62a299b57f67b30642c18541a062c2dc720a7a",
    "storage_conf": "fdf5ce294ebcd8a950d1ae2016032a2620e9b16cabf33c772dc43ab425ecec21",
    "proposed_registry": "af634259fb68f90cc4acf4987ee5cd5068eae9578e559c80ba62925d24d41b7d",
    "pilot_receipt": "37d24d30b5e96c9faa51ab7f9f29d8f1e29d4fa5eadc80690c158a7d8881a6bc",
    "image_receipt": "5ab7651c768aa29da9346cd5fa51a89d5d14ff757fbdff23e16eefbf6e7af7c1",
    "guard_head": "091f56275ae823cb3291b81dbdf016fcf16c3ea0",
    "source_commit": "ac83d8fa2fd315738afe675609a3dea05837cfea",
    "adapter_commit": "8e7c55a3ebcaa4584cb09b1ac743bb5320bd1257",
    "image_sha256": "458ff3d095ecf7db1b3622b56dafb9eec0947f2c3e567fcc3da3ea69f7dba924",
    "native_binary": "a175c7af8bed75b9add8229b30ee57380eaa4ffb67e351a8f5e91e43584bec0a",
}
GRAPHROOT = "/workspace/ivanka-exploratory-podman-20261121/store"
TARGET_FILES = ("registry", "checkpoint", "handoff", "pilot_receipt", "image_receipt")


class GateError(RuntimeError):
    """A fail-closed gate refused the migration."""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def check(cond, reason):
    if not cond:
        raise GateError(reason)


def verify_shared_reserve(root):
    """Fail closed when the workspace shared reserve is below policy floor."""
    policy = load(Path(root) / REG_NAME)["policy"]
    floor = policy.get("min_workspace_free_bytes")
    check(isinstance(floor, int) and floor > 0, "reserve_policy_drift")
    check(shutil.disk_usage("/workspace").free >= floor, "shared_reserve_below_floor")


def verify_penguin_image(podman, env):
    """Prove the exact PenguiN image is present in the bound campaign store."""
    image = EXPECTED["image_sha256"]
    out = subprocess.run([podman, "image", "inspect", image, "--format", "{{.Id}}"],
                         capture_output=True, text=True, env=env, timeout=30)
    got = out.stdout.strip().removeprefix("sha256:")
    check(out.returncode == 0 and got == image, "penguin_image_drift")


def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".tmp-", dir=str(path.parent))
    os.close(fd)
    tmp = Path(name)
    try:
        with tmp.open("wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        fsync_dir(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_json(path, obj):
    atomic_write_bytes(path, (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode())


def atomic_copy(src, dst):
    atomic_write_bytes(dst, Path(src).read_bytes())


def verify_imports():
    """Every executable module must come from the deployed PR536 tree."""
    base = DEPLOYED_GUARD.resolve()
    for mod in (pol, sched, px_execution, px_registry_migration, px_supervisor,
                heartbeat, lease, proc, watchdog_contract):
        where = Path(mod.__file__).resolve()
        check(where.is_relative_to(base), "import_source_drift:" + mod.__name__)


def verify_live_context(root, *, require_root_binding):
    """Re-derive the live watchdog run context and the real ALIVE record."""
    alive = LIVE_ROOT / ".watchdog-alive.json"
    check(alive.is_file() and not alive.is_symlink(), "live_alive_missing")
    record = load(alive)
    check(record.get("schema") == heartbeat.ALIVE_SCHEMA, "live_alive_schema_drift")
    check(record.get("graphroot") == GRAPHROOT, "live_alive_graphroot_drift")
    pid = record.get("pid")
    check(isinstance(pid, int) and pid > 0, "live_alive_pid_invalid")
    check(Path("/proc").joinpath(str(pid)).is_dir(), "live_alive_pid_not_running")
    env_bytes = Path("/proc", str(pid), "environ").read_bytes()
    env = dict(line.split(b"=", 1) for line in env_bytes.split(b"\0") if b"=" in line)

    def get(key):
        value = env.get(key.encode())
        return value.decode() if value is not None else None

    check(get("WATCHDOG_CODE") == str(DEPLOYED_GUARD), "watchdog_code_drift")
    pypath = get("PYTHONPATH") or ""
    check(pypath.startswith(str(DEPLOYED_GUARD) + ":"), "watchdog_pythonpath_drift")
    path = get("PATH") or ""
    check("/var/guix/profiles/per-user/puser/guix-profile/bin" in path.split(":"),
          "live_path_missing_podman")
    cmdline = Path("/proc", str(pid), "cmdline").read_bytes().replace(b"\0", b" ").decode()
    check("fail_closed_guard.watchdog_cli" in cmdline, "watchdog_cmdline_drift")
    if require_root_binding:
        check(get("WATCHDOG_ROOT") == str(Path(root).resolve()), "watchdog_root_drift")
    guard_head = subprocess.run(["git", "-C", str(DEPLOYED_GUARD), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
    check(guard_head == EXPECTED["guard_head"], "guard_head_drift")
    return {"watchdog_pid": pid, "watchdog_code": str(DEPLOYED_GUARD),
            "guard_head": guard_head, "alive_sha256": sha(alive)}


def acquire(root, *, require_exact_registry=True):
    root = Path(root)
    check(not root.joinpath("STOP").is_symlink() and not root.joinpath("STOP").exists(),
          "stop_ambiguity")
    lock_path = root / ".global-worker.lock"
    check(lock_path.is_file() and not lock_path.is_symlink(), "unknown_worker_lock")
    fd = lock_path.open("a+")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if require_exact_registry:
            check(sha(root / REG_NAME) == EXPECTED["registry"], "registry_drift")
    except BlockingIOError as exc:
        fd.close()
        raise GateError("active_worker") from exc
    except Exception:
        fd.close()
        raise
    return fd


def guard_gates(root, fd):
    env = {"CONTAINERS_STORAGE_CONF": str(root / "storage.conf"),
           "PATH": SANITIZED_PATH}
    resolved = shutil.which("podman", path=SANITIZED_PATH)
    check(resolved is not None and Path(resolved).is_file(), "podman_unresolved")
    env["PODMAN"] = resolved
    verify_shared_reserve(root)
    verify_penguin_image(resolved, env)
    try:
        check(sha(root / "storage.conf") == EXPECTED["storage_conf"],
              "storage_conf_drift")
        out = subprocess.run([resolved, "info", "--format", "{{.Store.GraphRoot}}"],
                             capture_output=True, text=True, env=env, timeout=30)
        check(out.returncode == 0 and out.stdout.strip() == GRAPHROOT, "unknown_store")
        alive = root / ".watchdog-alive.json"
        watchdog_contract.require_watchdog_readiness(
            alive, graphroot=GRAPHROOT, snapshot=proc.snapshot)
        lease.require_clear(root, env, watchdog_path=alive,
                            graphroot=GRAPHROOT, snapshot=proc.snapshot)
    except GateError:
        raise
    except Exception as exc:
        raise GateError("watchdog_or_lease_gate: " + str(exc)) from exc
    return env, resolved


def target_paths(root):
    return {
        "registry": Path(root) / REG_NAME,
        "checkpoint": Path(root) / "state/checkpoint.json",
        "handoff": px_supervisor.handoff_path(root, "penguin"),
        "pilot_receipt": Path(root) / "receipts" / PILOT_NAME,
        "image_receipt": Path(root) / "receipts" / IMAGE_NAME,
    }


def before_hashes(root):
    return {k: (None if not p.exists() else sha(p)) for k, p in target_paths(root).items()}


def snapshot_index(root):
    idx = Path(root) / "receipts/index.json"
    entries = load(idx)["entries"]
    check(isinstance(entries, dict) and entries, "receipt_index_empty")
    for ident, digest in entries.items():
        try:
            path = Path(root) / "receipts" / (ident + ".json")
            check(path.is_file() and not path.is_symlink(), "index_entry_missing:" + ident)
            check(sha(path) == digest, "index_entry_drift:" + ident)
            arm = sched.arm_from_receipt(root, ident)
            check(arm is not None and sched.receipt_id(arm) == ident,
                  "index_entry_identity_drift:" + ident)
            check(sched.verify_receipt(root, arm) is not None,
                  "index_entry_unverifiable:" + ident)
        except GateError:
            raise
        except Exception as exc:
            raise GateError("index_entry_unverifiable:" + ident + ":" + str(exc)[:80]) from exc
    return {"index_sha256": sha(idx), "entry_count": len(entries),
            "index_digest_chain": hashlib.sha256(
                json.dumps(entries, sort_keys=True).encode()).hexdigest()}


def stage(root, snapshot, fail_after=None):
    root = Path(root)
    txn = root / TXN
    check(not txn.is_symlink(), "txn_symlink")
    if txn.exists():
        check((txn / "journal.json").is_file(), "txn_without_journal")
        raise GateError("txn_in_progress: run --recover")
    txn.mkdir(mode=0o700)
    before = before_hashes(root)
    atomic_json(txn / "journal.json", {"schema": "ivanka.px.penguin.txn.v1",
                                       "state": "staging", "before": before,
                                       "snapshot": snapshot, "root": str(root)})
    if fail_after == "staging":
        raise GateError("synthetic_crash_after_staging")
    (txn / "receipts").mkdir()
    (txn / "handoff").mkdir()
    (txn / "state").mkdir()
    for f in (Path(root) / "receipts").glob("*.json"):
        if f.is_file() and not f.is_symlink():
            atomic_copy(f, txn / "receipts" / f.name)
    for src, name, expected in ((PILOT_SRC, PILOT_NAME, EXPECTED["pilot_receipt"]),
                                (IMAGE_SRC, IMAGE_NAME, EXPECTED["image_receipt"])):
        check(sha(src) == expected, "proposal_receipt_drift")
        existing = before["pilot_receipt" if name == PILOT_NAME else "image_receipt"]
        check(existing in (None, expected), "existing_evidence_digest_mismatch")
        atomic_copy(src, txn / "receipts" / name)

    reg = load(PROPOSED_REG)
    check(sha(PROPOSED_REG) == EXPECTED["proposed_registry"], "proposal_drift")
    for item in reg["candidates"]:
        for key in ("image_evidence", "pilot_evidence", "benchmark_evidence"):
            ev = item.get(key)
            if isinstance(ev, dict) and ev.get("path"):
                ev["path"] = str(txn / "receipts" / Path(ev["path"]).name)
    row = next(x for x in reg["candidates"] if x["id"] == "penguin")
    row.update(status="pilot", image_sha256=EXPECTED["image_sha256"],
               image_evidence={"path": str(txn / "receipts" / IMAGE_NAME),
                               "sha256": EXPECTED["image_receipt"]},
               pilot_evidence={"path": str(txn / "receipts" / PILOT_NAME),
                               "sha256": EXPECTED["pilot_receipt"]})
    atomic_json(txn / "registry-for-verify.json", reg)
    data = pol.checked(txn / "registry-for-verify.json", provenance_root=txn)
    bound = dict(row, adapter_commit=data["adapter_branch_commits"]["penguin"])
    check(pol.verified_receipt(bound, row["image_evidence"], "image", txn), "image_proof_failed")
    check(pol.verified_receipt(bound, row["pilot_evidence"], "pilot", txn), "pilot_proof_failed")
    check(pol.eligible(data, "penguin") and pol.cohort_eligible(data, "penguin"), "not_eligible")
    image = load(txn / "receipts" / IMAGE_NAME)
    pilot = load(txn / "receipts" / PILOT_NAME)
    for key in ("source_commit", "adapter_commit"):
        check(image[key] == EXPECTED[key] and pilot[key] == EXPECTED[key],
              "identity_drift:" + key)
    check(image["image_sha256"] == EXPECTED["image_sha256"], "image_identity_drift")
    check(image["native_binary_sha256"] == EXPECTED["native_binary"], "native_identity_drift")
    check(pilot["qualifying"] is False and data["qualifying"] is False, "qualifying_leak")
    check("scoring_attestation" not in pilot and "per_sample_results_sha256" not in pilot,
          "retroactive_metric")

    handoff = {"schema": px_supervisor.HANDOFF_SCHEMA, "tool_id": "penguin",
               "board": px_supervisor.PX_BOARD, "agent": px_supervisor.IMAGE_AGENT,
               "tests_passed": True, "image_sha256": EXPECTED["image_sha256"],
               "image_receipt_sha256": EXPECTED["image_receipt"],
               "pilot_receipt_sha256": EXPECTED["pilot_receipt"]}
    atomic_json(txn / "handoff/penguin.json", handoff)
    check(px_supervisor.verify_handoff(txn, txn / "registry-for-verify.json", "penguin",
                                       provenance_root=txn), "handoff_rejected")

    # The active registry is rebound to this root's provenance paths before it
    # is compared with the staged candidate; no boundary field is rewritten.
    current = load(root / REG_NAME)
    for item in current["candidates"]:
        for key in ("image_evidence", "pilot_evidence", "benchmark_evidence"):
            ev = item.get(key)
            if isinstance(ev, dict) and ev.get("path"):
                ev["path"] = str(Path(root) / "receipts" / Path(ev["path"]).name)
    active_rebound = txn / "current-rebound.json"
    atomic_json(active_rebound, current)

    # The deployed generic additive gate must admit only this one tool without
    # rewriting any existing arm, boundary field or policy.
    additive_plan = {"tool_id": "penguin",
                     "active_registry": str(active_rebound.relative_to(root))}
    try:
        px_registry_migration.verify_additive(
            root, additive_plan, txn / "registry-for-verify.json", reg)
    except Exception as exc:
        raise GateError("verify_additive: " + str(exc)) from exc

    # Build the exact final registry bytes first. `_plan_digest` binds the raw
    # registry_sha256, so deriving it from txn-local proof paths would stage a
    # checkpoint digest that cannot match the post-commit live registry.
    final = json.loads(json.dumps(reg))
    for item in final["candidates"]:
        for key in ("image_evidence", "pilot_evidence", "benchmark_evidence"):
            ev = item.get(key)
            if isinstance(ev, dict) and ev.get("path"):
                ev["path"] = str(Path(root) / "receipts" / Path(ev["path"]).name)
    final_path = txn / "registry-final.json"
    atomic_json(final_path, final)
    equivalent = json.loads(json.dumps(final))
    for item in equivalent["candidates"]:
        for key in ("image_evidence", "pilot_evidence", "benchmark_evidence"):
            ev = item.get(key)
            if isinstance(ev, dict) and ev.get("path"):
                ev["path"] = str(txn / "receipts" / Path(ev["path"]).name)
    equiv_path = txn / "registry-equivalence.json"
    atomic_json(equiv_path, equivalent)
    check(sha(equiv_path) == sha(txn / "registry-for-verify.json"),
          "final_registry_not_equivalent")

    old_cp = load(root / "state/checkpoint.json")
    completed = list(old_cp["completed"])
    check(not ({"penguin-physical-PX-R053", "penguin-synthetic-PX-H452"} & set(completed)),
          "pilot_alias_in_checkpoint")
    source = px_execution.load_cohort()
    # Bind the old checkpoint to a plan built from the UNMODIFIED live registry.
    bound_old = sched.build_plan(LIVE_ROOT / REG_NAME, source, LIVE_ROOT)
    check(old_cp["plan_sha256"] == sched._plan_digest(bound_old),
          "checkpoint_not_bound_to_old_plan")
    old_plan = sched.build_plan(active_rebound, source, root,
                                provenance_root=root / "receipts")
    # Proofs were verified on the byte-equivalent txn-path registry above.
    # Delegate only `checked` so the plan is bound to the exact final bytes.
    real_checked = pol.checked

    def checked_for_final(path, *, provenance_root=None):
        return real_checked(txn / "registry-for-verify.json", provenance_root=txn)

    pol.checked = checked_for_final
    try:
        new_plan = sched.build_plan(final_path, source, root, provenance_root=txn)
    finally:
        pol.checked = real_checked
    check(new_plan["registry_sha256"] == sha(final_path),
          "plan_not_bound_to_final_registry")
    check(set(old_plan["accepted_ids"]) == set(new_plan["accepted_ids"]),
          "canonical_arms_changed")
    check(new_plan["qualifying"] is False and "penguin" in new_plan["tools"],
          "penguin_not_admitted")
    atomic_json(txn / "state/checkpoint.json", dict(old_cp,
                plan_sha256=sched._plan_digest(new_plan), completed=completed))
    check(sched.resume(new_plan, txn) is not None, "resume_failed")

    staged = {"registry": final_path,
              "checkpoint": txn / "state/checkpoint.json",
              "handoff": txn / "handoff/penguin.json",
              "pilot_receipt": txn / "receipts" / PILOT_NAME,
              "image_receipt": txn / "receipts" / IMAGE_NAME}
    after = {k: sha(v) for k, v in staged.items()}
    # Backups only for targets that existed; evidence mismatch already failed.
    (txn / "backup").mkdir(exist_ok=True)
    for k, label in (("registry", "registry"), ("checkpoint", "checkpoint"),
                     ("handoff", "handoff"), ("pilot_receipt", "pilot_receipt"),
                     ("image_receipt", "image_receipt")):
        if before[k] is not None:
            atomic_copy(target_paths(root)[k], txn / "backup" / (label + ".json"))
    meta = {"old_plan_digest": sched._plan_digest(old_plan),
            "new_plan_digest": sched._plan_digest(new_plan),
            "accepted_before": len(old_plan["accepted_ids"]),
            "accepted_after": len(new_plan["accepted_ids"]),
            "completed": completed, "tools_before": old_plan["tools"],
            "tools_after": new_plan["tools"]}
    atomic_json(txn / "journal.json", {"schema": "ivanka.px.penguin.txn.v1",
                "state": "prepared", "before": before, "after": after,
                "snapshot": snapshot, "meta": meta, "root": str(root)})
    return txn, meta


def journal(base, state, **extra):
    txn = Path(base) / TXN
    atomic_json(txn / "journal.json", {"schema": "ivanka.px.penguin.txn.v1",
                                       "state": state, **extra})


def commit(root, snapshot, *, fail_after=None):
    root = Path(root)
    txn = root / TXN
    j = load(txn / "journal.json")
    check(j["state"] == "prepared", "journal_not_prepared")
    staged = {"registry": txn / "registry-final.json",
              "checkpoint": txn / "state/checkpoint.json",
              "handoff": txn / "handoff/penguin.json",
              "pilot_receipt": txn / "receipts" / PILOT_NAME,
              "image_receipt": txn / "receipts" / IMAGE_NAME}
    paths = target_paths(root)
    for label in TARGET_FILES:
        check(sha(staged[label]) == j["after"][label], "staged_drift:" + label)
        current = sha(paths[label]) if paths[label].exists() else None
        check(current == j["before"][label], "unrelated_change:" + label)
        if current != j["after"][label]:
            atomic_copy(staged[label], paths[label])
        if fail_after == label:
            raise GateError("synthetic_crash_after_" + label)
    check(sha(root / "receipts/index.json") == snapshot["index_sha256"],
          "index_changed_during_commit")
    for label in TARGET_FILES:
        check((sha(paths[label]) if paths[label].exists() else None) == j["after"][label],
              "final_target_drift:" + label)
    # Bind the journal completion to the ACTUAL post-commit state. A plan built
    # from txn-local proof paths would disagree with the live registry digest.
    try:
        source = px_execution.load_cohort()
        post_plan = sched.build_plan(paths["registry"], source, root,
                                     provenance_root=root / "receipts")
        check(post_plan["registry_sha256"] == sha(paths["registry"]),
              "post_commit_plan_registry_drift")
        check(sched._plan_digest(post_plan) == j["meta"]["new_plan_digest"],
              "post_commit_plan_digest_drift")
        sched.resume(post_plan, root)
        handoff_dir = root / "handoff"
        roster = {item["id"] for item in load(paths["registry"])["candidates"]}
        if handoff_dir.is_dir():
            for handoff_file in sorted(handoff_dir.glob("*.json")):
                record = load(handoff_file)
                if record.get("schema") != px_supervisor.HANDOFF_SCHEMA:
                    continue  # unrelated handoff record, not a PX supervisor handoff
                tool = record.get("tool_id")
                check(tool in roster,
                      "post_commit_handoff_unknown_tool:" + handoff_file.name)
                check(px_supervisor.verify_handoff(
                    root, paths["registry"], tool,
                    provenance_root=root / "receipts"),
                    "post_commit_handoff_invalid:" + tool)
    except GateError:
        raise
    except Exception as exc:
        raise GateError("post_commit_verification: " + str(exc)) from exc
    journal(root, "done", before=j["before"], after=j["after"], snapshot=snapshot,
            meta=j["meta"], root=str(root))
    if fail_after == "done":
        raise GateError("synthetic_crash_after_done")
    return sha(paths["registry"])


def atomic_unlink(path):
    path = Path(path)
    if path.exists():
        path.unlink()
        fsync_dir(path.parent)


def remove_txn(root):
    txn = Path(root) / TXN
    if txn.exists():
        shutil.rmtree(txn)
    fsync_dir(Path(root))


def staged_paths(root):
    txn = Path(root) / TXN
    return {"registry": txn / "registry-final.json",
            "checkpoint": txn / "state/checkpoint.json",
            "handoff": txn / "handoff/penguin.json",
            "pilot_receipt": txn / "receipts" / PILOT_NAME,
            "image_receipt": txn / "receipts" / IMAGE_NAME}


def verify_supervisor_idle(root):
    """Mirror px_registry_migration._supervisor_running: no live armed arm."""
    target = str(Path(root).resolve())
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmd = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", "ignore")
        except OSError:
            continue
        if "px_execution" in cmd and "--supervise" in cmd and target in cmd:
            raise GateError("supervisor_still_running")


def recover(root, *, finish_forward=False, operator_authorized=False):
    """Strict staging/prepared/done recovery, or authorized finish-forward.

    A staging journal contains only `before`/`snapshot`/`root`: no `after` and
    no backups are required. Live recovery needs operator authorization, the
    deployed guard context and a verified idle supervisor. The transaction is
    removed (with a directory fsync) only after every target and the index are
    verified at the requested terminal state.
    """
    root = Path(root)
    check(not root.joinpath("STOP").is_symlink() and not root.joinpath("STOP").exists(),
          "stop_ambiguity")
    is_live = root.resolve() == LIVE_ROOT.resolve()
    if is_live:
        check(operator_authorized, "missing_operator_authorization")
        verify_imports()
        verify_live_context(root, require_root_binding=True)
        verify_supervisor_idle(root)
    fd = acquire(root, require_exact_registry=False)
    try:
        if is_live:
            guard_gates(root, fd)
        txn = root / TXN
        check((txn / "journal.json").is_file(), "no_journal")
        j = load(txn / "journal.json")
        state = j.get("state")
        check(snapshot_index(root) == j["snapshot"], "index_drift_during_recovery")
        paths, before = target_paths(root), j["before"]
        check(set(before) == set(TARGET_FILES), "journal_targets_incomplete")
        current = {k: (sha(paths[k]) if paths[k].exists() else None) for k in TARGET_FILES}

        # Staging wrote no target and has no after/backups: verify unchanged
        # before hashes and index, then clean up without any rollback attempt.
        if state == "staging":
            check(not finish_forward, "finish_forward_requires_prepared")
            for label in TARGET_FILES:
                check(current[label] == before[label],
                      "unrelated_change_during_staging:" + label)
            result = {"recovered": False, "state": "staging",
                      "note": "no live target was modified during staging"}
            remove_txn(root)
            return result

        after = j.get("after")
        check(isinstance(after, dict) and set(after) == set(TARGET_FILES),
              "journal_after_missing")
        for label in TARGET_FILES:
            check(current[label] in (before[label], after[label]),
                  "unrelated_change_no_rollback:" + label)

        if state == "done":
            check(not finish_forward, "finish_forward_requires_prepared")
            for label in TARGET_FILES:
                check(current[label] == after[label], "committed_state_drift:" + label)
            result = {"recovered": False, "already_committed": True, "state": "done"}
            remove_txn(root)
            return result

        check(state == "prepared", "unknown_journal_state")
        backups = {}
        for label in TARGET_FILES:
            if before[label] is None:
                check(current[label] in (None, after[label]),
                      "unrelated_change_no_rollback:" + label)
                continue
            backup = txn / "backup" / (label + ".json")
            check(backup.is_file() and not backup.is_symlink()
                  and sha(backup) == before[label],
                  "invalid_backup_no_rollback:" + label)
            backups[label] = backup

        if finish_forward:
            check(operator_authorized, "missing_operator_authorization_for_finish_forward")
            staged = staged_paths(root)
            # Preflight ALL staged artifacts before the first write.
            for label in TARGET_FILES:
                src = staged[label]
                check(src.is_file() and not src.is_symlink() and sha(src) == after[label],
                      "staged_drift:" + label)
            for label in TARGET_FILES:
                if current[label] != after[label]:
                    atomic_copy(staged[label], paths[label])
            terminal, action = after, "finished_forward"
        else:
            for label in TARGET_FILES:
                if current[label] == before[label]:
                    continue
                if before[label] is None:
                    atomic_unlink(paths[label])
                else:
                    atomic_copy(backups[label], paths[label])
            terminal, action = before, "rolled_back"

        for label in TARGET_FILES:
            final = sha(paths[label]) if paths[label].exists() else None
            check(final == terminal[label], "terminal_target_drift:" + label)
        check(snapshot_index(root) == j["snapshot"], "index_changed_during_recovery")
        result = {"recovered": not finish_forward, "action": action,
                  "state": "done" if finish_forward else "prepared",
                  "index_sha256": j["snapshot"]["index_sha256"],
                  "targets": {k: (sha(paths[k]) if paths[k].exists() else None)
                              for k in TARGET_FILES}}
        if finish_forward:
            atomic_json(root / "penguin-migration-recovery.json", result)
        remove_txn(root)
        return result
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


def migrate(root, *, apply=False, operator_authorized=False, fail_after=None):
    check(not Path(root).is_symlink(), "root_symlink")
    root = Path(root).resolve()
    check(apply or root != LIVE_ROOT.resolve(), "live_root_requires_apply")
    if apply:
        check(operator_authorized, "missing_operator_authorization")
    check(not (root / TXN).exists(), "txn_in_progress: run --recover")
    verify_imports()
    live = verify_live_context(root, require_root_binding=root == LIVE_ROOT.resolve())
    if root == LIVE_ROOT.resolve():
        verify_supervisor_idle(root)
    fd = acquire(root)
    try:
        _, podman = guard_gates(root, fd)
        snapshot = snapshot_index(root)
        txn, meta = stage(root, snapshot, fail_after=fail_after)
        if fail_after == "prepared":
            raise GateError("synthetic_crash_after_prepared")
        registry_after = commit(root, snapshot, fail_after=fail_after)
        record = {"schema": "ivanka.px.penguin.migration-receipt.v3",
                  "mode": "apply" if apply else "dry-run", "root": str(root),
                  "live_context": live, "podman": podman, "snapshot": snapshot,
                  "meta": meta, "index_sha256_after": sha(root / "receipts/index.json"),
                  "registry_after_sha256": registry_after,
                  "argv_mount_capture_gap_retained": True,
                  "no_retroactive_metric": True}
        check(record["index_sha256_after"] == snapshot["index_sha256"],
              "index_changed_during_migration")
        out = root / ("penguin-migration-" + ("apply" if apply else "dryrun") + ".json")
        atomic_json(out, record)
        remove_txn(root)
        return {"ok": True, "record": str(out), "sha256": sha(out)}
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=LIVE_ROOT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-have-operator-authorization", action="store_true")
    ap.add_argument("--recover", action="store_true")
    ap.add_argument("--finish-forward", action="store_true")
    args = ap.parse_args()
    try:
        result = recover(args.root, finish_forward=args.finish_forward,
                         operator_authorized=args.i_have_operator_authorization) \
            if args.recover else migrate(
            args.root, apply=args.apply,
            operator_authorized=args.i_have_operator_authorization)
    except GateError as exc:
        print(json.dumps({"ok": False, "gate": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
