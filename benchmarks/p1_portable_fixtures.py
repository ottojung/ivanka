"""Source-only fixtures for the portable postbuild receipt contract.

The lease journal is produced by the REAL ``lease.acquire`` /
``lease.bind_group`` / ``lease.release`` functions and fail-closed evidence by
the REAL ``watchdog.blocked_evidence`` writer, into a caller-supplied temp root.
No build, OCI image, Podman, PX root, STOP or live lease is touched.
"""
import hashlib
import json
from pathlib import Path

from benchmarks.fail_closed_guard import lease, watchdog

from expanded import p1_bounded_pilot_runner as r


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(root, *, source_commit, role, portable_sha, native_sha,
          prebuild_plan_sha, image, expected_labels, plan_sha=None,
          base_layers=None, added_digest=None, mutate_result=None,
          mutate_receipt=None, fail_closed=False, omit_bind=False,
          duplicate_bind=False, replay_acquire=False, foreign_proof=False,
          omit_release=False, wrong_release_proof=False, wrong_bind_plan=False,
          wrong_bind_graphroot=False, wrong_bind_storage_conf=False,
          wrong_teardown=False, foreign_owner_release=False, omit_result=False,
          portable_binary_path="/fixture/portable-binary", base_image=None):
    """Create a complete, schema-authentic copy_overlay postbuild evidence set."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    plan_sha = plan_sha or "a" * 64
    ident = "copy-" + plan_sha[:16]
    base_layers = list(base_layers or ["sha256:" + "b" * 64])
    added = added_digest or "sha256:" + "c" * 64
    layers = base_layers + [added]
    base = base_image or r.PARENT_IMAGE
    pid = 4242
    cleanup = {
        "graphroot": r.SHARED_PX_BOUNDARY["graphroot"],
        "method": "exact_full_id_base_proof",
        "expected_base": base,
        "expected_name": "fixture-working",
        "baseline_ids": [], "removed": [],
        "fresh_absence_check": True, "kernel_enforcement": False,
    }
    teardown = {"process_group": pid, "stopped": True,
                "method": "verified_exact_group", "kernel_enforcement": False,
                "orphan_cleanup": cleanup}

    # Real copy_overlay result.json shape.
    result = {
        "tool": "copy_overlay", "lease": ident, "owner": ident,
        "plan_sha256": plan_sha, "status": "completed", "reason": None,
        "exit_code": 0, "peak_rss": 1234,
        "enforcement": "userspace_observed", "kernel_enforcement": False,
        "teardown": teardown,
        "image_receipt": {
            "image": image, "labels": dict(expected_labels),
            "base_layers": base_layers, "layers": layers,
            "one_layer_overlay": True, "kernel_enforcement": False,
        },
        "orphan_baseline_ids": [],
    }
    if mutate_result:
        mutate_result(result)
    result_path = root / "copy-overlay-result.json"
    if not omit_result:
        result_path.write_text(json.dumps(result, sort_keys=True))
    result_sha = _hash(result_path) if result_path.is_file() else "0" * 64

    # Authentic durable lease lifecycle via the real guard functions.
    lease.acquire(root, ident, "copy_overlay", owner=ident)
    bind_kwargs = dict(
        owner=ident,
        plan_sha256=("f" * 64 if wrong_bind_plan else plan_sha),
        graphroot=("wrong" if wrong_bind_graphroot
                   else r.SHARED_PX_BOUNDARY["graphroot"]),
        helper=True, baseline_ids=[], base_image=base,
        base_layers=base_layers,
        storage_conf_sha256=("f" * 64 if wrong_bind_storage_conf
                            else r.PINS_V2["storage_conf"]))
    if not omit_bind:
        lease.bind_group(root, ident, pid, pid, [5, 7], **bind_kwargs)
        if duplicate_bind:
            lease.bind_group(root, ident, pid, pid, [5, 7], **bind_kwargs)
    if replay_acquire:
        lease.acquire(root, ident, "copy_overlay", owner=ident)
    if foreign_owner_release:
        lease.append(root, {"schema": lease.SCHEMA, "lease": ident,
                            "owner": "foreign", "state": "released",
                            "proof": teardown, "at_utc": 2})
    elif not omit_release:
        lease.release(root, ident, owner=ident,
                      proof=({"process_group": 1} if wrong_release_proof
                             else ({"process_group": 2} if foreign_proof
                                   else ({"process_group": pid} if wrong_teardown
                                         else teardown))))

    if fail_closed:
        watchdog.blocked_evidence(root, ident, "wall_limit",
                                  "fixture fail-closed observation")

    receipt = {
        "schema": r.PORTABLE_POSTBUILD_SCHEMA,
        "prebuild_plan_sha256": prebuild_plan_sha,
        "build_executed": True,
        "image_identity_verified": True,
        "source_commit": source_commit,
        "native_binary_sha256": native_sha,
        "portable_binary_sha256": portable_sha,
        "portable_binary_path": portable_binary_path,
        "image_digest": image,
        "portable_image": image,
        "copy_overlay_result": {
            "path": str(result_path), "sha256": result_sha,
            "plan_sha256": plan_sha,
        },
    }
    if mutate_receipt:
        mutate_receipt(receipt)
    receipt_path = root / "portable-postbuild.json"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True))
    return {"root": root, "result_path": result_path, "result_sha": result_sha,
            "receipt_path": receipt_path, "receipt_sha": _hash(receipt_path),
            "plan_sha": plan_sha, "ident": ident, "image": image,
            "labels": dict(expected_labels), "teardown": teardown}
