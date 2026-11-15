"""Independent read-pinned 32-case mixed-strain Ivanka diagnostic.

This does not qualify the seven-arm benchmark or substitute stored scores.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from benchmarks.expanded.hxb2_cohort import attestation
from benchmarks.expanded.micall_synthetic import attempt
from benchmarks.expanded.run_synthetic import cohort_rows

DATA = Path("/workspace/ivanka-hxb2-depth10000-400-v2-20261114")
CHECKOUT = Path("/workspace/ivanka-coherent-mixed-risk-20261115")
COHERENT = Path("/workspace/ivanka-coherent-path-selection-20261115")
FORK = Path("/workspace/micall-dedicated-ivanka-coherent-20261115")
PILOT = Path("/workspace/ivanka-coherent-selection-pilot-20261115/full-micall")
IVANKA_COMMIT = "d3a6a1412c67670ecbff8db44b8906256800c239"
FORK_COMMIT = "739f16e146bdf6c99946aadeacc7e31c94d44c8e"
COMMON_COMMIT = "74f60e7be6248bdf5019498276036a0ebd339006"
IMAGE = "df930f78de3d824e4f9a7e253f285ba3707e5e7adb3a3dd1d390cdfc5d67febe"
BASE = "4a4aa1b92e48a7fdcb7fef2b886d62c0aa4603ff2a58659c7d32932d5fdeea93"
FAMILIES = ("minority_30pct", "equal_strains")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def output(command):
    return subprocess.check_output(command, text=True).strip()


def commit(path):
    if output(["git", "-C", str(path), "status", "--porcelain"]):
        raise ValueError(f"dirty pinned source: {path}")
    return output(["git", "-C", str(path), "rev-parse", "HEAD"])


def inputs():
    cases = [case for case in cohort_rows(DATA) if case[2]["family"] in FAMILIES]
    if len(cases) != 32:
        raise ValueError("expected all 32 HXB2 mixed-strain identities")
    expected = {f"{family}-s{i:03d}" for family in FAMILIES for i in range(16)}
    if {case[0] for case in cases} != expected:
        raise ValueError("mixed HXB2 identity mismatch")
    return sorted(cases)


def freeze():
    os.environ["CONTAINERS_STORAGE_CONF"] = (
        "/workspace/ivanka-podman-overlay-20261103/storage.conf")
    pilot = json.loads((PILOT / "run_manifest.json").read_text())
    if (pilot["rust_commit"] != IVANKA_COMMIT
            or pilot["fork_commit"] != FORK_COMMIT
            or pilot["ivanka_image_id"] != IMAGE
            or pilot["common_image"] != BASE
            or pilot["common_commit"] != COMMON_COMMIT
            or pilot["release_qualified"] is not False):
        raise ValueError("original source attestation changed")
    if commit(COHERENT) != IVANKA_COMMIT or commit(FORK) != FORK_COMMIT:
        raise ValueError("benchmark or fork source checkout changed")
    image = json.loads(output(["podman", "image", "inspect", "--format",
                               "{{json .Config.Labels}}", IMAGE]))
    labels = {
        "org.opencontainers.image.revision": FORK_COMMIT,
        "org.opencontainers.image.source": "https://github.com/ottojung/MiCall",
        "org.ottojung.ivanka.source-commit": IVANKA_COMMIT,
        "org.ottojung.micall.common-base": BASE,
        "org.ottojung.micall.common-baseline-commit": COMMON_COMMIT,
        "org.ottojung.micall.assembler": "ivanka",
        "org.ottojung.micall.source-branch":
            "bench/assembler-ivanka-coherent-20261115",
    }
    if any(image.get(k) != v for k, v in labels.items()):
        raise ValueError("container labels do not match source pins")
    proof = attestation(DATA, expected=400)
    cases = inputs()
    originals = [
        {"id": name, "manifest_sha256": sha(folder / "manifest.json"),
         "read1_sha256": sha(folder / "reads/R1.fastq.gz"),
         "read2_sha256": sha(folder / "reads/R2.fastq.gz")}
        for name, folder, _ in cases
    ]
    return {
        "schema": "ivanka.experimental.coherent_mixed32.v1",
        "qualified": False, "release_qualified": False,
        "status": "SOURCE_ATTESTED_DIAGNOSTIC_ONLY",
        "benchmark_runner_commit": commit(CHECKOUT),
        "runner_sha256": sha(__file__),
        "native_source_commit": IVANKA_COMMIT,
        "fork_source_commit": FORK_COMMIT,
        "common_micall_commit": COMMON_COMMIT,
        "image_sha256": IMAGE, "common_image_sha256": BASE,
        "source_pilot_manifest_sha256": sha(PILOT / "run_manifest.json"),
        "cohort_sha256": sha(DATA / "cohort.json"),
        "truth_validation": proof, "cases": originals,
        "max_seconds": 1800,
    }


def run(root):
    frozen = freeze()
    if root.exists():
        stored = json.loads((root / "run_manifest.json").read_text())
        if stored != frozen:
            raise ValueError("resume requires identical source and inputs")
    else:
        root.mkdir()
        (root / "run_manifest.json").write_text(
            json.dumps(frozen, indent=2, sort_keys=True) + "\n")
    originals = {x["id"]: x for x in frozen["cases"]}
    journal = root / "results.jsonl"
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()
            ] if journal.exists() else []
    if len({x["id"] for x in rows}) != len(rows):
        raise ValueError("duplicate case in original evidence journal")
    for item in rows:
        name = item["id"]
        if (name not in originals or item["image_sha256"] != IMAGE
                or item["ivanka"] != json.loads(
                    (root / name / "ivanka/execution.json").read_text())):
            raise ValueError("previous source-pinned result changed")
    done = {x["id"] for x in rows}
    for name, folder, meta in inputs():
        if name in done:
            continue
        if shutil.disk_usage("/workspace").free < 8 * 1024**3:
            raise ValueError("disk guard: <8 GiB free")
        original = originals[name]
        if any([
            sha(folder / "manifest.json") != original["manifest_sha256"],
            sha(folder / "reads/R1.fastq.gz") != original["read1_sha256"],
            sha(folder / "reads/R2.fastq.gz") != original["read2_sha256"],
        ]):
            raise ValueError("original paired read input changed")
        case = root / name
        if case.exists():
            raise ValueError(f"interrupted unjournaled case requires audit: {name}")
        case.mkdir()
        print("MIXED32_PINNED_CASE_START", name, flush=True)
        result = attempt((folder, meta), case / "ivanka", "ivanka", IMAGE, 1800)
        row = {"id": name, "image_sha256": IMAGE, "ivanka": result}
        with journal.open("a") as file:
            file.write(json.dumps(row, sort_keys=True) + "\n")
            file.flush()
            os.fsync(file.fileno())
        print("MIXED32_PINNED_CASE_RESULT", name, result["status"],
              result.get("score"), flush=True)
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    if len(rows) != 32:
        raise ValueError("incomplete mixed-strain risk screen")
    complete = {
        "schema": frozen["schema"], "qualified": False,
        "status": "ATTEMPTED_NOT_SEVEN_WAY_QUALIFIED",
        "cases_attempted": 32, "failed_arms": sum(
            x["ivanka"]["status"] != "success" for x in rows),
        "run_manifest_sha256": sha(root / "run_manifest.json"),
        "results_sha256": sha(journal),
    }
    target = root / "attempt-finished.json"
    if target.exists():
        if json.loads(target.read_text()) != complete:
            raise ValueError("source-pinned completion differs")
    else:
        target.write_text(json.dumps(complete, indent=2, sort_keys=True)+"\n")
    print("MIXED32_COMPLETE_NOT_QUALIFIED", complete, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.out)


if __name__ == "__main__":
    main()
