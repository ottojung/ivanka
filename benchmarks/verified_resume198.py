"""Read-only authenticated reuse of completed Ivanka samples after an interrupted 198 run.

A new logical cohort may admit ONLY independently verified successful samples.
A previous failure never counts as a success, even when its output resembles one.
The standard milestone198.qualify() remains the sole acceptance authority.
"""
import json
from pathlib import Path

from container_completion import verified_internal_seconds
from milestone198 import PANEL_SHA256, SAMPLE_CAP_SECONDS, finite
from reference_panel import panel_acceptance


def authenticate(record, root, row, expected, cached_iva, image, panel, sha,
                 output_names):
    """Fail closed unless immutable controls and original MiCall files still match."""
    name = row["sample"]
    invocation = record.get("invocation")
    if (record.get("sample") != name or record.get("status") != "finished"
            or record.get("failed") is not False or
            record.get("iva_baseline_reused") is not True):
        raise ValueError("Incomplete or failed source result")
    if not isinstance(invocation, str) or not invocation or "/" in invocation:
        raise ValueError("Invalid source invocation")
    if record.get("provenance") != expected or record.get("hxb2_sha256") != expected["hxb2_sha256"]:
        raise ValueError("Source input provenance differs from pinned current inputs")
    if record.get("iva") != cached_iva:
        raise ValueError("Source IVA control differs from the verified immutable cache")
    arm = record.get("ivanka")
    if not isinstance(arm, dict) or arm.get("exit_code") != 0 or arm.get("image_id") != image:
        raise ValueError("Source Ivanka image or exit is unqualified")
    if arm.get("podman_lifecycle") != "serialized_detached_v1":
        raise ValueError("Source lacks authenticated serialized container completion")
    if arm.get("timing_origin") != "micall_in_container_monotonic_v1":
        raise ValueError("Source lacks authentic in-container runtime")
    if not all(finite(arm.get(k), positive=True) for k in
               ("seconds", "container_wall_seconds")):
        raise ValueError("Source runtime evidence is missing")
    if (arm["container_wall_seconds"] > SAMPLE_CAP_SECONDS or
            arm["seconds"] > arm["container_wall_seconds"] + 1):
        raise ValueError("Source runtime exceeds frozen cap")
    folder = (root / invocation / name / "ivanka").resolve()
    if Path(arm.get("artifact_dir", "")).resolve() != folder or not folder.is_dir():
        raise ValueError("Source artifact directory is not in its own invocation")
    # A successful timer and an exit-code field are not sufficient if the
    # retained MiCall execution log has been truncated or replaced.
    # Require the authentic MiCall completion marker in the original log,
    # without reading the entire potentially large stderr into memory.
    log = folder / "podman.stderr.log"
    try:
        with log.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - 4096))
            completed = b"micall.process_run(): Done." in stream.read()
    except OSError as exc:
        raise ValueError("Missing original MiCall completion log") from exc
    if not completed:
        raise ValueError("Missing authentic MiCall Done completion witness")
    timing = verified_internal_seconds(
        folder / "micall_internal_timing.json", arm["container_wall_seconds"])
    if abs(timing - arm["seconds"]) > 1e-9:
        raise ValueError("Original in-container timing file changed")
    metrics = arm.get("metrics", {})
    outputs = metrics.get("outputs", {})
    if set(outputs) != set(output_names):
        raise ValueError("Missing expected hashed MiCall output names")
    for filename, witness in outputs.items():
        final = folder / filename
        scratch = folder / "scratch" / filename
        file = next((p for p in (final, scratch) if p.is_file()), None)
        if witness.get("exists") is True:
            if file is None or not witness.get("sha256") or sha(file) != witness["sha256"]:
                raise ValueError("Ivanka MiCall artifact missing or changed: " + filename)
        elif witness != {"exists": False} or file is not None:
            raise ValueError("MiCall artifact presence changed: " + filename)
    if metrics.get("num_final_max_conseqs", 0) < 1:
        raise ValueError("Missing final MAX consensus")
    scored = panel_acceptance(Path(cached_iva["artifact_dir"]), folder,
                              panel, min_ratio=0.90)
    if (scored != record.get("best_contig_acceptance") or
            scored.get("reference_panel_sha256") != PANEL_SHA256 or
            scored.get("pass") is not True):
        raise ValueError("Recomputed frozen-panel consensus score differs")
    return record


def load_verified(files, rows, expected_provenance, load_baseline, image,
                  panel, sha, output_names, on_progress=None):
    """Return (sample -> verified result, source digests) without cherry-picking.

    Multiple completed successes for a sample are ambiguous and rejected.
    Failed terminal records force that sample to be rerun.
    """
    by_name = {row["sample"]: row for row in rows}
    successes, failed_names, digests = {}, set(), []
    for raw_source in files:
        source = Path(raw_source).resolve(strict=True)
        if source.name != "results.jsonl":
            raise ValueError("Only an original results.jsonl can be resumed")
        before = sha(source)
        digests.append({"file": str(source), "sha256": before})
        lines = source.read_text().splitlines(keepends=True)
        for number, line in enumerate(lines, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                # An interrupted write may truncate only the final line.
                # It is NOT completed or acceptance evidence.
                if number == len(lines) and not line.endswith("\n"):
                    continue
                raise ValueError("Malformed historical result line") from exc
            if not isinstance(record, dict) or record.get("sample") not in by_name:
                raise ValueError(f"Unknown or malformed sample at {source}:{number}")
            name = record["sample"]
            if record.get("status") in ("started", "reused_verified"):
                continue
            if record.get("status") != "finished" or record.get("failed") is not False:
                failed_names.add(name)
                continue
            if name in successes:
                raise ValueError("Duplicate completed result: " + name)
            expected = expected_provenance(by_name[name])
            cached = load_baseline(name, expected)
            successes[name] = authenticate(
                record, source.parent, by_name[name], expected, cached,
                image, panel, sha, output_names)
            if on_progress is not None:
                on_progress(len(successes))
        if sha(source) != before:
            raise ValueError("Source JSONL changed during authenticated import")
    for name in failed_names:
        successes.pop(name, None)
    return successes, digests
