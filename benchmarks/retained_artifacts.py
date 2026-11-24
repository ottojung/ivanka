"""Retire MiCall scratch after retaining final data and computed measurements.

MiCall's --keep_scratch is necessary to expose some final files, but its
large intermediate SAM/FASTQ/remapping files are not benchmark evidence.
Move terminal data out of scratch *after* the container and score extraction.
Never delete the arm's results, timing, logs, or independent JSONL report.

The terminal policy is fail-closed. Deletion requires sealed terminal evidence
(metrics on success, a failure receipt otherwise), verified source hashes and
an observed-dead container. Until then scratch and logs are preserved. Final
scientific tables may be plain or losslessly compressed: retention recognises
both and verifies the SHA-256 of the *uncompressed* logical content, which is
the interface the compression workfront registers its reader through.
"""
import argparse
import bz2
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import time

# Intermediate read-level tables are large, regenerable and NOT final metrics.
INTERMEDIATE_CSV = {
    "aligned.csv", "unstitched_aligned.csv",
    "remap.csv", "unstitched_remap.csv",
}
FINAL_EXTENSIONS = {".csv", ".fasta", ".fa", ".json"}
# Visual outputs are never scientific evidence, at any nesting depth. PDFs are
# included alongside raster/vector plots and page-layout figures.
VISUAL_EXTENSIONS = frozenset({".png", ".svg", ".jpg", ".jpeg", ".gif",
                               ".webp", ".bmp", ".tif", ".tiff", ".avif",
                               ".eps", ".pdf"})
PRESERVED_SUBDIRS = {"coverage_maps", "resistance_reports"}
ARM_NAMES = {"iva", "ivanka", "haploflow", "megahit",
             "abyss", "spades", "velvet"}
# Disposable read-level/al/index inputs. The check is applied to the logical
# name (one codec suffix stripped) so a compressed FASTQ is still disposable.
DISPOSABLE_SUFFIXES = frozenset({".fastq", ".fq", ".sam", ".bam", ".bai",
                                 ".bt2", ".bt2i", ".bt2b", ".ebwt",
                                 ".index", ".fai", ".dict", ".part", ".tmp"})
# Losslessly compressed final tables keep their logical scientific name. The
# compression workfront may register further codec suffixes; it never edits
# this module and this module never parses its files.
COMPRESSED_SUFFIXES = {".zst", ".gz", ".bz2", ".xz"}
CONTENT_HASHER = None  # optional callable(path) -> sha256 of logical content
RECEIPT_SCHEMA = "ivanka.retention.terminal.v1"


class RetentionGateError(RuntimeError):
    """Terminal preconditions are unmet; scratch and logs are preserved."""


def register_compressed_suffix(suffix):
    """Allow a lossless codec's final tables through the retention filter."""
    suffix = suffix.lower()
    if not suffix.startswith(".") or len(suffix) < 2:
        raise ValueError("compressed suffix must look like '.zst'")
    COMPRESSED_SUFFIXES.add(suffix)


def set_content_hasher(hasher):
    """Register logical-content hashing for compressed final tables.

    The compression workfront owns its reader. Retention only needs its digest
    of the uncompressed bytes so recorded SHA-256 values stay comparable.
    The reader is consulted only for files whose suffix is in
    COMPRESSED_SUFFIXES; plain finals are hashed directly. A codec-specific
    reader therefore cannot break arms that write uncompressed CSV/FASTA.
    """
    global CONTENT_HASHER
    if hasher is not None and not callable(hasher):
        raise ValueError("content hasher must be callable or None")
    CONTENT_HASHER = hasher


def logical_name(name):
    """Strip one recognised lossless codec suffix from a file name."""
    path = Path(name)
    if path.suffix.lower() in COMPRESSED_SUFFIXES:
        return path.stem
    return path.name


def _hash(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _logical_stream(path):
    """Open a final table as a stream of its uncompressed bytes."""
    suffix = Path(path.name).suffix.lower()
    if suffix == ".gz":
        return gzip.open(path, "rb")
    if suffix == ".bz2":
        return bz2.open(path, "rb")
    if suffix == ".xz":
        return lzma.open(path, "rb")
    if suffix == ".zst":
        try:
            import zstandard as zstd
        except ImportError as exc:
            raise RetentionGateError(
                "zstd final table needs a registered content hasher") from exc
        return zstd.ZstdDecompressor().stream_reader(path.open("rb"))
    return path.open("rb")


def content_sha256(path):
    """SHA-256 of the logical (uncompressed) content of a retained table.

    A registered reader is only used for recognised compressed suffixes. Plain
    finals must never be handed to a codec-only reader: doing so would fail
    every promotion and roll all scratch back, even when no codec is involved.
    """
    if (Path(path.name).suffix.lower() in COMPRESSED_SUFFIXES
            and CONTENT_HASHER is not None):
        return CONTENT_HASHER(path)
    hasher = hashlib.sha256()
    with _logical_stream(path) as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _retained(name):
    logical = logical_name(name)
    if (logical in INTERMEDIATE_CSV or logical in {"temp.fasta", "temp.fa"}
            or re.fullmatch(r"nuc_read_counts[^/]*\.csv", logical)):
        return False
    if Path(logical).suffix.lower() in DISPOSABLE_SUFFIXES:
        return False
    return Path(logical).suffix.lower() in FINAL_EXTENSIONS


def _safe_existing(dst, src):
    if dst.is_symlink() or (dst.exists() and dst.is_dir()):
        raise ValueError(f"refusing to replace nonregular retained artifact: {dst}")
    if dst.exists() and _hash(dst) != _hash(src):
        raise ValueError(f"conflicting final artifact: {dst}")


def _assert_inside(path, base):
    """Refuse any target that resolves outside the arm's own directory tree."""
    resolved = Path(path).resolve()
    root = Path(base).resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError(f"retention target escaped arm directory: {path}")
    if Path(path).is_symlink():
        raise ValueError(f"retention target is a symlink: {path}")
    return resolved


def _promotion_plan(arm):
    arm = Path(arm)
    scratch = arm / "scratch"
    if not scratch.exists() and not scratch.is_symlink():
        return None
    if arm.is_symlink() or scratch.is_symlink() or not scratch.is_dir():
        raise ValueError(f"unsafe benchmark scratch: {scratch}")
    chosen = []
    for item in sorted(scratch.iterdir()):
        if item.is_symlink():
            continue  # unlink during discard; never follow it
        if item.is_file() and _retained(item.name):
            target = arm / item.name
            if target.exists() and not target.is_symlink() and target.is_file():
                if _hash(target) != _hash(item):
                    # Historical MiCall versions may write different root and
                    # scratch results. Preserve both rather than overwriting.
                    target = arm / ("scratch_" + item.name)
            _safe_existing(target, item)
            chosen.append((item, target))
        elif item.is_dir() and item.name in PRESERVED_SUBDIRS:
            target = arm / item.name
            if target.exists() or target.is_symlink():
                target = arm / ("scratch_" + item.name)
                if target.exists() or target.is_symlink():
                    raise ValueError(f"conflicting metrics directory: {target}")
            chosen.append((item, target))
    return chosen


def promote_finals(arm):
    """Move verified final scientific files out of scratch without discarding it."""
    plan = _promotion_plan(arm)
    if plan is None:
        return []
    promoted = []
    for source, target in plan:
        if target.exists():
            continue
        os.replace(source, target)
        promoted.append((source, target))
    return promoted


def _discard_scratch(arm):
    arm = Path(arm)
    scratch = arm / "scratch"
    if scratch.is_symlink() or (scratch.exists() and not scratch.is_dir()):
        raise ValueError(f"unsafe benchmark scratch: {scratch}")
    if not scratch.exists():
        return False
    shutil.rmtree(scratch)
    return True


def retain_arm(arm):
    """Promote terminal products before recursively removing scratch.

    This is idempotent; it never follows symlinks out of the arm. An existing
    conflicting final file is retained separately, never overwritten.
    """
    plan = _promotion_plan(arm)
    if plan is None:
        return {"scratch_present": False, "removed": False,
                "promoted": [], "bytes_before": 0}
    promoted = []
    for source, target in plan:
        if target.exists():
            continue
        os.replace(source, target)
        promoted.append(target.name)
    _discard_scratch(arm)
    return {"scratch_present": True, "removed": True, "promoted": promoted}


def remove_visuals(arm):
    """Remove plots from a completed arm, including failed executions.

    Walk nested diagnostic folders without following symlinks. Never remove
    scientific CSV/FASTA/JSON evidence or touch files outside the arm. The
    caller must wait until the container has terminated.
    """
    arm = Path(arm)
    if arm.is_symlink() or not arm.is_dir():
        raise ValueError(f"unsafe benchmark output: {arm}")
    root = arm.resolve()
    removed = 0
    bytes_removed = 0
    for parent, dirs, files in os.walk(arm, followlinks=False):
        dirs[:] = [name for name in dirs
                   if not (Path(parent) / name).is_symlink()]
        for name in files:
            path = Path(parent) / name
            if path.suffix.lower() not in VISUAL_EXTENSIONS or path.is_symlink():
                continue
            if not path.is_file():
                continue
            _assert_inside(path, root)
            bytes_removed += path.stat().st_size
            path.unlink()
            removed += 1
    return {"removed_images": removed, "removed_image_bytes": bytes_removed}


def seal_terminal_evidence(arm, evidence, source_hashes,
                           name="terminal_evidence.json"):
    """Write a sealed receipt (payload plus raw SHA-256 sidecar) atomically."""
    arm = Path(arm)
    if arm.is_symlink() or not arm.is_dir():
        raise ValueError(f"unsafe benchmark output: {arm}")
    target = arm / name
    _assert_inside(target, arm.resolve())
    payload = {**evidence, "schema": RECEIPT_SCHEMA, "sealed": True,
               "source_hashes": dict(source_hashes), "sealed_at": time.time()}
    temporary = target.with_name("." + name + ".part")
    with temporary.open("w") as stream:
        json.dump(payload, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    digest = _hash(temporary)
    temporary.replace(target)
    sidecar = target.with_name(target.name + ".sha256")
    sidecar.write_text(digest + "\n")
    return target, sidecar


def _load_sealed_evidence(evidence_path, source_hashes):
    path = Path(evidence_path)
    sidecar = Path(str(path) + ".sha256")
    if not path.is_file() or not sidecar.is_file() or path.is_symlink():
        raise RetentionGateError("terminal evidence is not sealed on disk")
    if sidecar.read_text().strip() != _hash(path):
        raise RetentionGateError("terminal evidence hash mismatch")
    evidence = json.loads(path.read_text())
    if evidence.get("schema") != RECEIPT_SCHEMA or evidence.get("sealed") is not True:
        raise RetentionGateError("terminal evidence schema or seal is invalid")
    if not ("metrics" in evidence or "failure" in evidence):
        raise RetentionGateError("terminal evidence has no metrics or failure receipt")
    sealed_hashes = evidence.get("source_hashes")
    if (not isinstance(sealed_hashes, dict) or not sealed_hashes
            or any(not isinstance(value, str) or not value
                   for value in sealed_hashes.values())
            or not any(re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in sealed_hashes.values())):
        raise RetentionGateError("terminal evidence has no valid source hashes")
    if source_hashes is not None and sealed_hashes != dict(source_hashes):
        raise RetentionGateError("source hashes differ from the sealed receipt")
    return evidence


def _verify_metrics(metrics, promoted, root):
    """Re-check sealed output digests before any scratch bytes are removed."""
    outputs = metrics.get("outputs") if isinstance(metrics, dict) else None
    if not isinstance(outputs, dict):
        raise RetentionGateError("sealed metrics carry no per-output digests")
    checked = 0
    for source, target in promoted:
        logical = logical_name(target.name)
        record = outputs.get(logical) or outputs.get(target.name)
        if not isinstance(record, dict) or not record.get("sha256"):
            continue  # not a scored output; promotion alone preserves it
        if content_sha256(target) != record["sha256"]:
            raise RetentionGateError(f"retained output changed: {target.name}")
        checked += 1
    return checked


def terminal_retire(arm, *, evidence_path, container_dead, source_hashes=None,
                    archive_scratch=False):
    """Common fail-closed terminal scratch retirement policy.

    Deletion happens only after the container is observed dead, terminal
    evidence is sealed and hashed on disk, source hashes match that receipt,
    and every scored retained file still matches its sealed digest. A failure
    receipt is sufficient evidence for a failed arm: its logs and final data
    are preserved while disposable scratch and visuals are still reclaimed.
    No full scratch archive is created unless a caller explicitly opts in.
    """
    arm = Path(arm)
    if arm.is_symlink() or not arm.is_dir():
        raise RetentionGateError(f"unsafe benchmark output: {arm}")
    dead = container_dead() if callable(container_dead) else container_dead
    if dead is not True:
        raise RetentionGateError("container has not terminated")
    evidence = _load_sealed_evidence(evidence_path, source_hashes)
    root = arm.resolve()
    evidence_path = _assert_inside(evidence_path, root)
    report = {"scratch_present": (arm / "scratch").exists(),
              "retired": False, "promoted": [], "verified_outputs": 0,
              "removed_images": 0, "archived": False}
    if not report["scratch_present"]:
        visuals = remove_visuals(arm)
        report.update(visuals)
        return report
    promoted = []
    try:
        promoted = promote_finals(arm)
        if "metrics" in evidence:
            report["verified_outputs"] = _verify_metrics(
                evidence["metrics"], promoted, root)
        if archive_scratch:
            archive = arm / "scratch.tar.gz"
            _assert_inside(archive, root)
            shutil.make_archive(str(archive)[:-7], "gzip", arm / "scratch")
            report["archived"] = True
        report["retired"] = _discard_scratch(arm)
    except Exception:
        # Never leave a half-promoted arm: put final files back in scratch.
        # Digest verification decompresses finals, so a corrupt or truncated
        # compressed table can raise a codec error (LZMAError, zlib.error,
        # EOFError) that is not an OSError/ValueError. Rollback must cover any
        # failure after promotion; the original exception is re-raised so the
        # caller still sees the exact diagnostic.
        for source, target in reversed(promoted):
            if target.exists() and not source.exists() and not target.is_symlink():
                os.replace(target, source)
        raise
    report["promoted"] = [target.name for _, target in promoted]
    report.update(remove_visuals(arm))
    return report


def _candidate_arms(root):
    """Only the known run/sample/assembler hierarchy; never project code."""
    root = Path(root)
    if not (root / "results.jsonl").is_file() or root.is_symlink():
        return
    for run in root.iterdir():
        if not run.is_dir() or run.is_symlink():
            continue
        if not re.fullmatch(r"[0-9]+-[0-9]+", run.name):
            continue
        for sample in run.iterdir():
            if not sample.is_dir() or sample.is_symlink():
                continue
            for arm in sample.iterdir():
                if (arm.name in ARM_NAMES and arm.is_dir()
                        and not arm.is_symlink()
                        and (arm / "scratch").is_dir()):
                    yield arm


def result_roots(workspace):
    """Discover only result directories with a JSONL evidence manifest."""
    workspace = Path(workspace)
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("workspace is not a normal directory")
    for entry in workspace.iterdir():
        if not entry.is_dir() or entry.is_symlink():
            continue
        if not entry.name.startswith(("ivanka-", "micall-")):
            continue
        if (entry / "results.jsonl").is_file():
            yield entry
        for nested in entry.iterdir():
            if (nested.is_dir() and not nested.is_symlink()
                    and (nested / "results.jsonl").is_file()):
                yield nested


def clean_workspace(workspace, apply=False):
    """Conservative discovery, aggressive removal *inside* verified arms."""
    roots = list(result_roots(workspace))
    arms = [arm for root in roots for arm in _candidate_arms(root)]
    report = {"workspace": str(Path(workspace).resolve()),
              "mode": "apply" if apply else "dry_run",
              "results_roots": len(roots), "scratch_directories": len(arms),
              "retired": 0, "errors": [], "promoted_files": 0,
              "retired_results_roots": []}
    for arm in arms:
        if not apply:
            continue
        try:
            result = retain_arm(arm)
            report["retired"] += int(result["removed"])
            report["promoted_files"] += len(result["promoted"])
            report["retired_results_roots"].append(str(arm))
        except (OSError, ValueError) as exc:
            report["errors"].append(f"{arm}: {type(exc).__name__}: {exc}")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--apply", action="store_true",
                        help="Actually promote terminal files and remove scratch")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = clean_workspace(args.workspace, args.apply)
    compact = {key: value for key, value in report.items()
               if key != "retired_results_roots"}
    print(json.dumps(compact, sort_keys=True))
    if args.report:
        with args.report.open("x") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
