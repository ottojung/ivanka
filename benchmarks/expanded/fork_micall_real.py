"""Fresh source-verified 198-real MiCall A/B comparisons against all competitors.

A development sample/tool subset is explicitly diagnostic, never qualifying.
Historical patched-image results and replay logic remain untouched.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from benchmarks.fork_micall_binding import VARIABLES
from .adapters import ASSEMBLERS
from .fork_micall_synthetic import checked_images
from .real_matrix import MANIFEST

SCHEMA = "ivanka.expanded.fork_micall_real.v1"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_real(data, sample):
    root = Path(data)
    manifest_file = root / "manifest.tsv"
    if digest(manifest_file) != MANIFEST:
        raise ValueError("real 198 cohort has changed from frozen input manifest")
    with manifest_file.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != 198 or len({row["sample"] for row in rows}) != 198:
        raise ValueError("not the original unique 198 physical samples")
    if sample is not None and sample not in {
            row["sample"] for row in rows}:
        raise ValueError("development sample absent from frozen real cohort")
    return MANIFEST


def command(name, *, jobs, sample=None):
    """Use original MiCall read-level pipeline and 33-reference MAX scorer."""
    args = [sys.executable,
            str(Path(__file__).resolve().parents[1] / "podman_full_micall.py"),
            "--mode", "both", "--jobs", str(jobs), "--parallel-arms",
            "--all-projects", "--timeout-per-arm", "1800",
            "--sample-time-limit", "1800", "--diagnostic-90-floor"]
    if name != "ivanka":
        args.extend(["--candidate-assembler", name])
    if sample is not None:
        args.extend(["--sample", sample])
    return args


def source_manifest(data, images, attestation_file, base, sample, selected):
    root = Path(__file__).resolve()
    source = [root, root.parents[1]/"podman_full_micall.py",
              root.parents[1]/"fork_micall_binding.py",
              root.with_name("real_matrix.py")]
    return {
        "schema": SCHEMA,
        "qualified": False, "status": "ATTEMPTED_NOT_QUALIFIED",
        "expected_samples": 198, "selected_sample": sample,
        "selected_tools": selected, "images": images,
        "base_image_sha256": base,
        "real_manifest_sha256": validate_real(data, sample),
        "fork_attestation_sha256": digest(attestation_file),
        "source_files_sha256": {path.name: digest(path) for path in source},
    }


def run(data, output, images, fork, base, attestation_file, *,
        jobs=10, sample=None, selected=None):
    if jobs not in range(1, 11):
        raise ValueError("real MiCall worker count must be 1..10")
    if selected is None:
        selected = tuple(tool for tool in ASSEMBLERS if tool != "iva")
    if (not selected or len(selected) != len(set(selected))
            or set(selected) - (set(ASSEMBLERS) - {"iva"})):
        raise ValueError("unknown or duplicate candidate tool")
    checked_images(images, attestation_file, fork, base)
    pinned = source_manifest(
        data, images, attestation_file, base, sample, list(selected))
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root/"run_manifest.json").write_text(
        json.dumps(pinned, sort_keys=True, indent=2) + "\n")
    recorded = {}
    for name in selected:
        candidate = root / name
        candidate.mkdir()
        env = os.environ.copy()
        env.update({
            "IVANKA_DATA": str(Path(data).resolve()),
            "IVANKA_PODMAN_RESULTS": str(candidate),
            "IVANKA_IVA_IMAGE": images["iva"],
            "IVANKA_IVANKA_IMAGE": images[name],
            "IVANKA_PODMAN_LIFECYCLE": "detached",
            VARIABLES[0]: str(Path(attestation_file).resolve()),
            VARIABLES[1]: str(Path(fork).resolve()),
            VARIABLES[2]: str(
                (root / "source_verified_images.json").resolve()),
            VARIABLES[3]: base,
        })
        image_map = root / "source_verified_images.json"
        if not image_map.is_file():
            image_map.write_text(json.dumps(images,sort_keys=True,indent=2)+"\n")
        argv = command(name,jobs=jobs,sample=sample)
        with (candidate/"runner.log").open("x") as stdout:
            result = subprocess.run(argv, env=env,
                                    cwd=Path(__file__).resolve().parents[2],
                                    check=False, stdout=stdout,
                                    stderr=subprocess.STDOUT)
        recorded[name] = {
            "exit_code": result.returncode,
            "image_id": images[name],
            "results_jsonl": str(candidate/"results.jsonl"),
            "results_sha256": digest(candidate/"results.jsonl")
            if (candidate/"results.jsonl").is_file() else None,
        }
        (root/"execution_manifest.json").write_text(
            json.dumps(recorded,sort_keys=True,indent=2)+"\n")
        print("FORK_MiCall_REAL_TOOL",name,"exit",result.returncode,
              "result_exists",(candidate/"results.jsonl").is_file(),flush=True)
    can_join = sample is None and set(selected) == set(ASSEMBLERS)-{"iva"}
    status = {
        "schema": SCHEMA, "status": "ATTEMPTED_NOT_QUALIFIED",
        "all_six_candidate_runs_attempted": can_join,
        "source_manifest_sha256": digest(root/"run_manifest.json"),
        "execution_manifest_sha256": digest(root/"execution_manifest.json"),
        "tools": recorded,
    }
    (root/"attempt_summary.json").write_text(
        json.dumps(status,sort_keys=True,indent=2)+"\n")
    return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--attestation", required=True, type=Path)
    parser.add_argument("--fork", required=True, type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--jobs", type=int, default=10)
    parser.add_argument("--sample", help="development case only; never qualifies")
    parser.add_argument("--tools", nargs="+",
                        help="development candidate subset, default all six")
    args=parser.parse_args()
    result=run(args.data,args.out,json.loads(args.images.read_text()),
               args.fork,args.base,args.attestation,
               jobs=args.jobs,sample=args.sample,selected=args.tools)
    print("FORK_SOURCE_VERIFIED_REAL_ATTEMPTED",result["status"])
    print("NOT QUALIFIED: join six complete physical-198 comparisons "
          "and 400-HXB2 full cohort with strict independent seven-way PSI gate.")


if __name__=="__main__":
    main()
