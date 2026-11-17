"""Recover complete case records without conflating retries or changing tools."""
import hashlib
import json
from pathlib import Path

from .adapters import ASSEMBLERS
from .micall_dominant import SCORE_ORIGIN, MULTITRUTH_SCORE_ORIGIN
from .micall_synthetic_constants import TIMING_ORIGIN


def digest(path):
    stream = Path(path)
    return hashlib.sha256(stream.read_bytes()).hexdigest()


def identity(identifier, manifest, proof):
    """Immutable per-case fields for truthful restart verification."""
    mate_hashes = manifest["sha256"]
    return {
        "id": identifier, "cohort": "synthetic",
        "family": manifest["family"], "truth_validation": proof,
        "input_sha256": hashlib.sha256(
            (mate_hashes["reads/R1.fastq.gz"] +
             mate_hashes["reads/R2.fastq.gz"]).encode()
        ).hexdigest(),
    }


def existing_case(folder, fields, images):
    """Return only a fully attested case; malformed cached data fails closed."""
    file = Path(folder) / "matrix.json"
    if not file.exists():
        return None
    row = json.loads(file.read_text())
    if (not isinstance(row, dict) or
            any(row.get(key) != value for key, value in fields.items())
            or set(row.get("results", {})) != set(ASSEMBLERS)
            or set(row.get("execution_order", [])) != set(ASSEMBLERS)):
        raise ValueError(f"cached case identity/assembler mismatch: {folder}")
    version = fields["truth_validation"].get("schema") == "ivanka.mixed_viral_truth_validation.v4"
    required_score_origin = MULTITRUTH_SCORE_ORIGIN if version else SCORE_ORIGIN
    for name, result in row["results"].items():
        if (result.get("sha256") != images[name]
                or result.get("score_origin") != required_score_origin
                or result.get("timing_origin") != TIMING_ORIGIN
                or result.get("status") not in ("success", "failed")):
            raise ValueError(f"invalid cached tool evidence: {folder}/{name}")
        arm = Path(folder) / name
        evidence = arm / "execution.json"
        if not evidence.is_file() or json.loads(evidence.read_text()) != result:
            raise ValueError(f"modified/missing cached execution: {evidence}")
        if result["status"] == "success":
            if (result.get("exit_code") != 0
                    or not isinstance(result.get("seconds"), (int, float))
                    or result["seconds"] <= 0):
                raise ValueError(f"invalid cached success: {evidence}")
            final = result.get("final_dominant", {})
            sources = [
                (final.get("source_output"), final.get("conseq_csv_sha256")),
            ]
            for relative, expected in sources:
                if not relative or not expected or digest(arm / relative) != expected:
                    raise ValueError(f"modified cached MiCall output: {arm}")
    return row


def reusable_arm(folder, name, image, score_origin):
    """Recover a fully evidenced arm even when its enclosing case crashed."""
    folder = Path(folder)
    evidence = folder / "execution.json"
    if not evidence.is_file():
        return None
    record = json.loads(evidence.read_text())
    if (record.get("sha256") != image
            or record.get("score_origin") != score_origin
            or record.get("timing_origin") != TIMING_ORIGIN
            or record.get("status") not in ("success", "failed")
            or record.get("argv", []).count(image) != 1
            or record.get("argv", [])[-1:] != ["--all_projects"]):
        raise ValueError(f"{name}: incomplete arm identity or scoring evidence")
    if record["status"] == "success":
        report = record.get("final_dominant", {})
        path, expected = report.get("source_output"), report.get("conseq_csv_sha256")
        if (record.get("exit_code") != 0
                or not isinstance(record.get("seconds"), (int, float))
                or record["seconds"] <= 0 or not path or not expected
                or digest(folder / path) != expected):
            raise ValueError(f"{name}: missing or modified successful arm output")
    return record


def preserve_interrupted(output, identifier):
    """Never delete partial MiCall output; rerun in fresh, separate directory."""
    path = Path(output) / identifier
    if not path.exists():
        return
    if (path / "matrix.json").exists():
        raise ValueError("a completed case may not be overwritten")
    archived = Path(output) / "_interrupted"
    archived.mkdir(exist_ok=True)
    for number in range(1, 1000):
        target = archived / f"{identifier}-{number:03d}"
        if not target.exists():
            path.rename(target)
            return
    raise ValueError("too many interrupted attempts to recover safely")


def write_case(path, row):
    """Atomic committed case result, independent of streaming JSONL updates."""
    target = Path(path) / "matrix.json"
    if target.exists():
        raise FileExistsError("completed benchmark case is immutable")
    temporary = target.with_suffix(".json.partial")
    with temporary.open("x") as stream:
        json.dump(row, stream, sort_keys=True)
        stream.write("\n")
    temporary.replace(target)
