"""Measure one physical Ivanka job; a failed score never becomes a pass."""
import hashlib
import secrets

from benchmarks.expanded.comparators_first_real import atomic, PANEL, row_path


def execute(row, image, hxb2, panel, pmm, out):
    name = row["sample"]
    invocation = ("ivanka-physical-" + hashlib.sha256(name.encode())
                  .hexdigest()[:12] + "-" + secrets.token_hex(5))
    try:
        arm = pmm.run_arm(row, "ivanka", image,
                          hxb2 if row.get("project") == "NFLHIVDNA" else None,
                          3000, invocation, True)
        if arm.get("exit_code") != 0:
            raise ValueError(f"MiCall exited with {arm.get('exit_code')}")
        best = pmm.best_panel_alignment(
            pmm.final_max_sequences(arm["artifact_dir"]), panel)
        if arm.get("seconds") is None:
            raise ValueError("missing in-container monotonic completion")
        measure = {"score": float(best["score"]), "seconds": arm["seconds"]}
        failed, error = False, None
    except Exception as exc:
        if "arm" not in locals():
            arm = {"image_id": image, "exit_code": 1,
                   "error": f"{type(exc).__name__}: {exc}"}
        measure, failed = None, True
        error = f"{type(exc).__name__}: {exc}"
    result = {"sample": name, "tool": "ivanka", "image_id": image,
              "input_sha256": row["input_sha256"],
              "reference_panel_sha256": PANEL, "status": "finished",
              "failed": failed, "arm": arm, "measurement": measure,
              "error": error, "resource_timeout_seconds": 3000}
    target = row_path(out / "ivanka", name)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic(target, result)
    print("PHYSICAL_IVANKA", name, "failed" if failed else "success", flush=True)
    return result
