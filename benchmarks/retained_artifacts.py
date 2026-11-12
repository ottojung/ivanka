"""Retire MiCall scratch after retaining final data and computed measurements.

MiCall's --keep_scratch is necessary to expose some final files, but its
large intermediate SAM/FASTQ/remapping files are not benchmark evidence.
Move terminal data out of scratch *after* the container and score extraction.
Never delete the arm's results, timing, logs, or independent JSONL report.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

# Intermediate read-level tables are large, regenerable and NOT final metrics.
INTERMEDIATE_CSV = {
    "aligned.csv", "unstitched_aligned.csv",
    "remap.csv", "unstitched_remap.csv",
}
FINAL_EXTENSIONS = {".csv", ".fasta", ".fa", ".json", ".svg"}
PRESERVED_SUBDIRS = {"coverage_maps", "resistance_reports"}
ARM_NAMES = {"iva", "ivanka", "haploflow", "megahit",
             "abyss", "spades", "velvet"}


def _hash(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _retained(name):
    if (name in INTERMEDIATE_CSV or name in {"temp.fasta", "temp.fa"}
            or re.fullmatch(r"nuc_read_counts[^/]*\.csv", name)):
        return False
    return Path(name).suffix.lower() in FINAL_EXTENSIONS


def _safe_existing(dst, src):
    if dst.is_symlink() or (dst.exists() and dst.is_dir()):
        raise ValueError(f"refusing to replace nonregular retained artifact: {dst}")
    if dst.exists() and _hash(dst) != _hash(src):
        raise ValueError(f"conflicting final artifact: {dst}")


def retain_arm(arm):
    """Promote terminal products before recursively removing scratch.

    This is idempotent; it never follows symlinks out of the arm. An existing
    conflicting final file is retained separately, never overwritten.
    """
    arm = Path(arm)
    scratch = arm / "scratch"
    if not scratch.exists() and not scratch.is_symlink():
        return {"scratch_present": False, "removed": False,
                "promoted": [], "bytes_before": 0}
    if arm.is_symlink() or scratch.is_symlink() or not scratch.is_dir():
        raise ValueError(f"unsafe benchmark scratch: {scratch}")
    chosen = []
    for item in sorted(scratch.iterdir()):
        if item.is_symlink():
            continue  # unlink during rmtree; never follow it
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
    # All destinations are checked before removing any scratch evidence.
    promoted = []
    for source, target in chosen:
        if target.exists():
            continue
        os.replace(source, target)
        promoted.append(target.name)
    # All scientific CSVs and terminal genome FASTAs are outside scratch.
    # Remaining scratch is transient mapping, temporary FASTQ and indexes.
    shutil.rmtree(scratch)
    return {"scratch_present": True, "removed": True,
            "promoted": promoted}


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
