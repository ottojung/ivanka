"""Source-only fixtures for the portable postbuild receipt contract.

Everything is written into a caller-supplied temp directory using the REAL
copy_overlay result.json shape and the real lease/watchdog journal schemas.
No build, OCI image, Podman, PX root, lease or STOP is touched by this module.
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
          mutate_receipt=None, fail_closed=False, omit_release=False,
          wrong_release_proof=False, omit_result=False,
          portable_binary_path="/fixture/portable-binary",
          base_image=None):
    """Create a complete, schema-real copy_overlay postbuild evidence set."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    plan_sha = plan_sha or "a" * 64
    ident = "copy-" + plan_sha[:16]
    base_layers = list(base_layers or ["sha256:" + "b" * 64])
    added = added_digest or "sha256:" + "c" * 64
    layers = base_layers + [added]
    teardown = {"process_group": 4242, "signal": "SIGKILL",
                "orphan_cleanup": {"reclaimed": []}}
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

    events = [
        {"schema": lease.SCHEMA, "lease": ident, "owner": ident,
         "state": "acquired", "mode": "copy_overlay", "at_utc": 1},
        {"schema": lease.SCHEMA, "lease": ident, "owner": ident,
         "state": "active", "mode": "copy_overlay", "helper": True,
         "pid": 4242, "pgid": 4242, "fingerprint": [5, 7],
         "plan_sha256": plan_sha, "graphroot": "/fixture/graphroot",
         "base_image": base_image or "d" * 64,
         "base_layers": base_layers, "at_utc": 1},
        {"schema": lease.SCHEMA, "lease": ident, "owner": ident,
         "state": "released", "proof": (dict(teardown)
                                        if not wrong_release_proof
                                        else {"process_group": 1}),
         "at_utc": 2},
    ]
    if omit_release:
        events = events[:1]
    (root / lease.JOURNAL_NAME).write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n")
    if fail_closed:
        event = {"schema": watchdog.SCHEMA, "worker": ident,
                 "result": "fail_closed", "reason": "wall_limit",
                 "action": {"action": "teardown"}}
        (root / watchdog.EVIDENCE_NAME).write_text(
            json.dumps(event, sort_keys=True) + "\n")

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
