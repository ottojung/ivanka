"""Run only a verified failed arm at 50 minutes; save it in a new directory."""
import hashlib
import secrets

from benchmarks.expanded.comparators_first_real import atomic, row_path
from benchmarks.expanded.real_resume import digest


def execute(row, tool, images, reference, panel, pmm, out, original):
    sample = row["sample"]
    target = row_path(out / tool, sample)
    target.parent.mkdir(exist_ok=True, parents=True)
    previous = row_path(original / tool, sample)
    invocation = ("retry-" + tool + "-" +
                  hashlib.sha256(sample.encode()).hexdigest()[:12] +
                  "-" + secrets.token_hex(5))
    arm_name = "iva" if tool == "iva" else "ivanka"
    try:
        arm = pmm.run_arm(row, arm_name, images[tool],
                          reference if row.get("project") == "NFLHIVDNA" else None,
                          3000, invocation, True)
        if arm.get("exit_code") != 0:
            raise ValueError("MiCall arm nonzero exit: " + str(arm.get("exit_code")))
        best = pmm.best_panel_alignment(
            pmm.final_max_sequences(arm["artifact_dir"]), panel)
        if arm.get("seconds") is None:
            raise ValueError("successful MiCall arm has no verified timer")
        value = {"score": float(best["score"]), "seconds": arm["seconds"]}
        failed, reason = False, None
    except Exception as exc:
        if "arm" not in locals():
            arm = {"image_id": images[tool], "exit_code": 1,
                   "error": f"{type(exc).__name__}: {exc}"}
        value, failed, reason = None, True, f"{type(exc).__name__}: {exc}"
    record = {"sample": sample, "tool": tool, "image_id": images[tool],
              "input_sha256": row["input_sha256"],
              "reference_panel_sha256": original_panel_hash(),
              "status": "finished", "failed": failed, "arm": arm,
              "measurement": value, "error": reason,
              "original_checkpoint_sha256": digest(previous),
              "resource_timeout_seconds": 3000}
    atomic(target, record)
    print("RESOURCE_PHYSICAL_RESULT", tool, sample[:8],
          "success" if not failed else "failed", flush=True)
    return record


def original_panel_hash():
    from benchmarks.expanded.comparators_first_real import PANEL
    return PANEL
