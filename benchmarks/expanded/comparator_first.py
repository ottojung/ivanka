"""Complete the six fixed MiCall comparators before any new Ivanka cohort.

This is a source-attested independent diagnostic. It never launches Ivanka,
never suppresses failed samples, and never changes the frozen cohort.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from .hxb2_cohort import attestation
from .micall_checkpoint import digest, identity
from .micall_dominant import SCORE_ORIGIN
from .micall_lock import exclusive_lock
from .micall_synthetic import attempt
from .micall_synthetic_constants import TIMING_ORIGIN
from .micall_synthetic_scheduler import execute
from .run_synthetic import cohort_rows

TOOLS = ("iva", "haploflow", "megahit", "abyss", "spades", "velvet")
PATCH = "e18ebccf9e68d5ee9e01206e7b69045f2be672f3"
REPO = Path(__file__).resolve().parents[2]
SOURCE_FILES = (
    "benchmarks/expanded/comparator_first.py",
    "benchmarks/expanded/micall_synthetic.py",
    "benchmarks/expanded/micall_synthetic_scheduler.py",
    "benchmarks/expanded/micall_dominant.py",
    "benchmarks/expanded/micall_checkpoint.py",
    "benchmarks/expanded/hxb2_cohort.py",
    "benchmarks/expanded/micall_lock.py",
    "benchmarks/expanded/score.py",
    "benchmarks/inside_container_timing.py",
)


def git(path, *args):
    return subprocess.check_output(
        ["git", "-C", str(path), *args], text=True, timeout=80).strip()


def inspect(image, template):
    return subprocess.check_output(
        ["podman", "image", "inspect", "--format", template, image],
        text=True, timeout=80).strip()


def verify_build(build):
    if (build.get("schema") != "ivanka.comparator.stitched_count_images.v1"
            or build.get("qualified") is not False
            or build.get("patch_commit") != PATCH
            or any(set(build[key]) != set(TOOLS) for key in
                   ("images", "old_images", "branches", "commits"))):
        raise ValueError("wrong immutable comparator image manifest")
    original = Path("/workspace/micall-stitch-count-provenance-20261116")
    if git(original, "rev-parse", PATCH + ":micall") != build["source_tree"]:
        raise ValueError("patched MiCall source subtree changed")
    for name in TOOLS:
        branch = f"bench/assembler-{name}-stitched-counts-20261116"
        folder = Path(f"/workspace/micall-dedicated-{name}-stitched-counts-20261116")
        expected = build["commits"][name]
        if (build["branches"][name] != branch
                or git(folder, "rev-parse", "HEAD") != expected
                or git(folder, "branch", "--show-current") != branch
                or git(folder, "status", "--porcelain")
                or git(folder, "remote", "get-url", "origin")
                != "https://github.com/ottojung/MiCall.git"
                or git(folder, "rev-parse", "HEAD:micall") != build["source_tree"]
                or git(folder, "ls-remote", "--heads", "origin",
                       "refs/heads/" + branch).split()[0] != expected):
            raise ValueError(f"fork source drift: {name}")
        image, parent = build["images"][name], build["old_images"][name]
        if any(not re.fullmatch("[a-f0-9]{64}", sha) for sha in
               (image, parent)):
            raise ValueError(f"mutable image ref: {name}")
        if inspect(image, "{{.Id}}") != image:
            raise ValueError(f"missing immutable comparator image: {name}")
        layers = json.loads(inspect(image, "{{json .RootFS.Layers}}"))
        old_layers = json.loads(inspect(parent, "{{json .RootFS.Layers}}"))
        if layers[:len(old_layers)] != old_layers:
            raise ValueError(f"comparator image lost original tool base: {name}")
        labels = json.loads(inspect(image, "{{json .Config.Labels}}"))
        requirements = {
            "org.opencontainers.image.source": "https://github.com/ottojung/MiCall",
            "org.opencontainers.image.revision": expected,
            "org.ottojung.micall.assembler": name,
            "org.ottojung.micall.patched-source-commit": PATCH,
            "org.ottojung.micall.source-branch": branch,
            "org.ottojung.micall.previous-image-id": parent,
            "org.ottojung.micall.build-kind":
                "source-pinned-stitched-counts-comparator-diagnostic",
        }
        if any(labels.get(key) != value for key, value in requirements.items()):
            raise ValueError(f"incorrect assembler/source image label: {name}")


def manifest(data, images_file, jobs):
    build = json.loads(Path(images_file).read_text())
    verify_build(build)
    if git(REPO, "status", "--porcelain") or git(REPO, "remote", "get-url", "origin") != (
            "https://github.com/ottojung/ivanka.git"):
        raise ValueError("unverified or dirty benchmark source")
    if jobs not in range(1, 11):
        raise ValueError("comparator jobs must be between 1 and 10")
    truth = attestation(data, expected=400)
    cases = list(cohort_rows(data))
    if len(cases) != 400:
        raise ValueError("wrong immutable HXB2-v2 cohort count")
    return {
        "schema": "ivanka.comparator_first.stitched_counts_400.v1",
        "status": "DIAGNOSTIC_NOT_QUALIFIED",
        "qualified": False, "release_qualified": False,
        "tool_order": list(TOOLS), "expected_samples": 400,
        "expected_arms": 2400, "jobs": jobs, "timeout_per_arm": 1800,
        "source_commit": git(REPO, "rev-parse", "HEAD"),
        "benchmark_source_sha256": {file: digest(REPO / file)
                                    for file in SOURCE_FILES},
        "images": build["images"],
        "image_manifest_sha256": digest(images_file),
        "patched_micall_tree": build["source_tree"],
        "original_cohort_manifest_sha256": digest(Path(data) / "cohort.json"),
        "truth_validation": truth,
    }, cases


def verify_record(record, row, output, images):
    if (record.get("id") != row["id"]
            or record.get("family") != row["family"]
            or record.get("input_sha256") != row["input_sha256"]
            or record.get("truth_validation") != row["truth_validation"]):
        raise ValueError("cached original input/independent truth changed")
    name = record.get("assembler")
    if name not in TOOLS:
        raise ValueError("unknown, possibly Ivanka, assembler in comparator run")
    result = record.get("result")
    if (not isinstance(result, dict)
            or result.get("sha256") != images[name]
            or result.get("status") not in ("success", "failed")
            or result.get("score_origin") != SCORE_ORIGIN
            or result.get("timing_origin") != TIMING_ORIGIN):
        raise ValueError("invalid cached comparator execution")
    arm = output / row["id"] / name
    evidence = arm / "execution.json"
    if not evidence.is_file() or json.loads(evidence.read_text()) != result:
        raise ValueError("cached execution changed or disappeared")
    if result["status"] == "success":
        seconds = result.get("seconds")
        score = result.get("score")
        if (result.get("exit_code") != 0 or type(seconds) not in (float, int)
                or not math.isfinite(seconds) or seconds <= 0
                or type(score) not in (float, int) or not math.isfinite(score)):
            raise ValueError("invalid successful arm timing/score")
        final = result.get("final_dominant", {})
        filename = final.get("source_output")
        if (not filename or Path(filename).is_absolute()
                or ".." in Path(filename).parts
                or digest(arm / filename) != final.get("conseq_csv_sha256")):
            raise ValueError("cached final MiCall MAX evidence missing")
    return name


def history(output, cases, images):
    file = output / "results.jsonl"
    if not file.is_file():
        return {}
    raw = file.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("truncated checkpoint journal")
    proof = json.loads((output / "run_manifest.json").read_text())[
        "truth_validation"]
    cases_by_id = {identifier: identity(identifier, manifest, proof)
                   for identifier, _, manifest in cases}
    seen = {}
    for line in raw.splitlines():
        record = json.loads(line)
        if record.get("id") not in cases_by_id:
            raise ValueError("unknown physical/synthetic case in journal")
        name = verify_record(record, cases_by_id[record["id"]], output, images)
        key = (record["id"], name)
        if key in seen:
            raise ValueError("duplicate original comparator invocation")
        seen[key] = record
    return seen


def preserve_orphan(output, identifier, assembler):
    arm = output / identifier / assembler
    if not arm.exists():
        return
    if arm.is_symlink() or not arm.is_dir():
        raise ValueError("unexpected unjournaled arm")
    archive = output / "_interrupted"
    archive.mkdir(exist_ok=True)
    for counter in range(1, 1000):
        target = archive / f"{identifier}-{assembler}-{counter:03}"
        if not target.exists():
            arm.rename(target)
            return
    raise ValueError("exceeded safe interrupted attempt count")


def prune(record, output):
    if record["result"]["status"] != "success":
        return
    scratch = output / record["id"] / record["assembler"] / "scratch"
    if scratch.exists():
        if not scratch.is_dir() or scratch.is_symlink():
            raise ValueError("unexpected scratch type")
        shutil.rmtree(scratch)


def run(data, output, images_file, jobs):
    output = Path(output).resolve()
    with exclusive_lock(output):
        frozen, cases = manifest(data, images_file, jobs)
        file = output / "run_manifest.json"
        if file.exists():
            if json.loads(file.read_text()) != frozen:
                raise ValueError("refuse to resume changed source/image/cohort")
        else:
            if output.exists():
                raise ValueError("output exists without original attestation")
            output.mkdir()
            file.write_text(json.dumps(frozen, sort_keys=True, indent=2) + "\n")
        all_cases = [(identifier, folder, metadata,
                      identity(identifier, metadata, frozen["truth_validation"]))
                     for identifier, folder, metadata in cases]
        case_fields = {item[0]: item[3] for item in all_cases}
        source_cases = [(a, b, c) for a, b, c, _ in all_cases]
        old = history(output, source_cases, frozen["images"])
        for record in old.values():
            prune(record, output)
        pending = [(c, name) for name in TOOLS for c in all_cases
                   if (c[0], name) not in old]
        print("COMPARATOR_PRIORITIZED", "done", len(old),
              "pending", len(pending), "no_ivanka", flush=True)
        with (output / "results.jsonl").open("a", buffering=1) as journal:
            def worker(item):
                (identifier, folder, metadata, fields), name = item
                arm = output / identifier / name
                arm.parent.mkdir(exist_ok=True)
                preserve_orphan(output, identifier, name)
                result = attempt((folder, metadata), arm, name,
                                 frozen["images"][name], 1800)
                return {**fields, "assembler": name, "result": result}

            def commit(record):
                verify_record(record, case_fields[record["id"]],
                              output, frozen["images"])
                journal.write(json.dumps(record, sort_keys=True) + "\n")
                journal.flush()
                __import__("os").fsync(journal.fileno())
                prune(record, output)
                print("COMPARATOR_ARM", record["assembler"], record["id"],
                      record["result"]["status"], flush=True)

            with ThreadPoolExecutor(max_workers=jobs) as pool:
                execute(pool, pending, jobs, worker, commit,
                        lambda: shutil.disk_usage(output).free,
                        reserve_per_arm=512 * 1024**2)
        completed = history(output, source_cases, frozen["images"])
        if len(completed) != frozen["expected_arms"]:
            raise ValueError("incomplete comparator set")
        summary = {
            "schema": frozen["schema"], "qualified": False,
            "status": (
                f"ATTEMPTED_{frozen['expected_arms']}_NOT_RELEASE_QUALIFIED"),
            "cases": frozen["expected_samples"], "arms": len(completed),
            "failed_arms": sum(x["result"]["status"] != "success"
                               for x in completed.values()),
            "results_sha256": digest(output / "results.jsonl"),
            "run_manifest_sha256": digest(file),
        }
        marker = output / "attempt-finished.json"
        if marker.exists():
            if json.loads(marker.read_text()) != summary:
                raise ValueError("previous comparator completion differs")
        else:
            marker.write_text(json.dumps(summary, sort_keys=True, indent=2)+"\n")
        print("SIX_NON_IVANKA_COMPARATOR_COHORT_COMPLETE", summary, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=10)
    args = parser.parse_args()
    run(args.data, args.out, args.images, args.jobs)


if __name__ == "__main__":
    main()
