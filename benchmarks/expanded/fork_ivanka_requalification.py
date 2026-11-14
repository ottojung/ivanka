"""Recompute one changed Ivanka MiCall arm without rerunning six unchanged rivals."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess

from .fork_micall_synthetic import checked_images
from .hxb2_cohort import attestation
from .micall_checkpoint import digest, identity, preserve_interrupted
from .micall_lock import exclusive_lock
from .micall_synthetic import attempt
from .micall_dominant import SCORE_ORIGIN
from .micall_synthetic_constants import TIMING_ORIGIN
from .run_synthetic import cohort_rows

SCHEMA = "ivanka.expanded.fork_ivanka_requalification.v1"


def source_manifest(data, proof, images, attestation_file, binary_commit,
                    limit, only_v2_low_depth=False):
    root = Path(__file__).resolve()
    source = (root, root.with_name("fork_micall_synthetic.py"),
              root.with_name("micall_synthetic.py"),
              root.with_name("micall_checkpoint.py"),
              root.with_name("micall_dominant.py"),
              root.with_name("score.py"),
              root.parents[1] / "reference_panel.py",
              root.parents[1] / "project_references.py",
              root.parents[1] / "podman_detached_lifecycle.py",
              root.parents[1] / "inside_container_timing.py")
    if only_v2_low_depth:
        source += (root.with_name("v2_lowdepth_probe.py"),
                   root.with_name("hxb2_lowdepth_v2.py"),
                   root.with_name("hxb2_cohort.py"))
    expected = 16 if only_v2_low_depth else 400
    return {"schema": SCHEMA, "qualified": False, "expected": expected,
            "limit": limit, "selected_assembler": "ivanka",
            "case_subset": ("hxb2_v2_low_depth_16" if only_v2_low_depth
                            else None),
            "cohort_sha256": digest(Path(data) / "cohort.json"),
            "truth_proof": proof, "images": images,
            "ivanka_source_commit": binary_commit,
            "fork_attestation_sha256": digest(attestation_file),
            "source_sha256": {p.name: digest(p) for p in source}}


def check_arm(folder, fields, image):
    file = folder / "case.json"
    if not file.is_file():
        return None
    row = json.loads(file.read_text())
    if any(row.get(key) != value for key, value in fields.items()):
        raise ValueError("recovered case identity differs")
    arm = row.get("ivanka")
    if not isinstance(arm, dict) or arm.get("sha256") != image:
        raise ValueError("recovered Ivanka image changed")
    if (arm.get("score_origin") != SCORE_ORIGIN
            or arm.get("timing_origin") != TIMING_ORIGIN
            or arm.get("status") not in ("success", "failed")
            or json.loads((folder/"ivanka/execution.json").read_text()) != arm):
        raise ValueError("recovered arm execution changed")
    if arm["status"] == "success":
        final = arm.get("final_dominant") or {}
        output = final.get("source_output")
        if (arm.get("exit_code") != 0 or not output
                or digest(folder/"ivanka"/output)
                != final.get("conseq_csv_sha256")):
            raise ValueError("recovered MiCall final MAX evidence altered")
    return row


def execute(case, destination, image, proof, timeout):
    name, source, manifest = case
    destination.mkdir(exist_ok=False)
    arm = attempt((source, manifest), destination/"ivanka",
                  "ivanka", image, timeout)
    row = {**identity(name, manifest, proof), "ivanka": arm}
    out = destination/"case.json"
    pending = out.with_suffix(".json.pending")
    with pending.open("x") as stream:
        json.dump(row, stream, sort_keys=True)
        stream.write("\n")
    pending.replace(out)
    return row


def reassemble(root, cases, image, proof):
    recovered = []
    for name, _, manifest in cases:
        fields = identity(name, manifest, proof)
        row = check_arm(root/name, fields, image)
        if row is not None:
            recovered.append(row)
        else:
            preserve_interrupted(root, name)
    return recovered


def cleanup(root, row, image, proof):
    folder = Path(root)/row["id"]
    fields = {key: row[key] for key in
              ("id", "cohort", "family", "input_sha256", "truth_validation")}
    if check_arm(folder, fields, image) != row or row["truth_validation"] != proof:
        raise ValueError("cannot reclaim unverifiable case")
    scratch = folder/"ivanka/scratch"
    if row["ivanka"]["status"] == "success" and scratch.exists():
        if not scratch.is_dir() or scratch.is_symlink():
            raise ValueError("MiCall scratch is not a real directory")
        import shutil
        shutil.rmtree(scratch)


def select_cases(cases, proof, only_v2_low_depth):
    if not only_v2_low_depth:
        return cases
    if proof.get("schema") != "ivanka.hxb2_truth_validation.v2":
        raise ValueError("the low-depth-only probe requires attested v2 truth")
    from .v2_lowdepth_probe import only_changed
    return only_changed(cases)


def run(data, destination, images, source_roots, base, att_file,
        binary_commit, *, jobs=2, timeout=1800, limit=None, resume=False,
        only_v2_low_depth=False):
    if jobs not in range(1, 5) or timeout not in range(1, 1801):
        raise ValueError("jobs must be 1..4; timeout 1..1800")
    if limit is not None and limit not in range(1, 401):
        raise ValueError("limited diagnostic cases must be 1..400")
    if only_v2_low_depth and limit is not None:
        raise ValueError("v2 low-depth probe must select exactly all 16 cases")
    if only_v2_low_depth and timeout != 1800:
        raise ValueError("v2 low-depth probe requires the original 1800s limit")
    destination = Path(destination).resolve()
    with exclusive_lock(destination):
        evidence = checked_images(images, att_file, source_roots, base)
        if evidence["images"]["ivanka"]["image_sha256"] != images["ivanka"]:
            raise ValueError("verified Ivanka image differs")
        label = subprocess.check_output(["podman", "image", "inspect",
            "--format", '{{index .Config.Labels "org.ottojung.ivanka.source-commit"}}',
            images["ivanka"]], text=True, timeout=60).strip()
        if label != binary_commit:
            raise ValueError("Ivanka Rust source commit differs from OCI executable")
        proof = attestation(data, expected=400)
        cases = list(cohort_rows(data))
        if len(cases) != 400:
            raise ValueError("invalid HXB2 cohort size")
        cases = select_cases(cases, proof, only_v2_low_depth)
        if limit is not None:
            cases = cases[:limit]
        frozen = source_manifest(data, proof, images, att_file,
                                 binary_commit, limit, only_v2_low_depth)
        manifest_path = destination/"run_manifest.json"
        if resume:
            if not manifest_path.is_file() or json.loads(
                    manifest_path.read_text()) != frozen:
                raise ValueError("resume requires the same frozen source and images")
        else:
            destination.mkdir(exist_ok=False)
            manifest_path.write_text(json.dumps(frozen, sort_keys=True, indent=2)+"\n")
        prior = destination/"results.jsonl"
        recovered = reassemble(destination, cases, images["ivanka"], proof) if resume else []
        done = {row["id"] for row in recovered}
        if resume:
            with (destination/"resume_history.jsonl").open("a") as stream:
                stream.write(json.dumps({
                    "previous_sha256": digest(prior) if prior.is_file() else None,
                    "source_manifest_sha256": digest(manifest_path),
                    "recovered": len(recovered)}, sort_keys=True)+"\n")
            temp = destination/"results.recovered.partial"
            with temp.open("x") as stream:
                for row in sorted(recovered, key=lambda x:x["id"]):
                    stream.write(json.dumps(row, sort_keys=True)+"\n")
            temp.replace(prior)
        with prior.open("a" if resume else "x", buffering=1) as stream:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                futures = [pool.submit(execute, case, destination/case[0],
                                       images["ivanka"], proof, timeout)
                           for case in cases if case[0] not in done]
                for f in as_completed(futures):
                    row = f.result()
                    stream.write(json.dumps(row, sort_keys=True)+"\n")
                    cleanup(destination, row, images["ivanka"], proof)
                    print("IVANKA_SOURCE_REQUALIFICATION", row["id"],
                          row["ivanka"]["status"], flush=True)
        return len(done) + len(futures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "out", "images", "attestation", "fork"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--binary-commit", required=True)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only-v2-low-depth", action="store_true",
                        help="source-attested 16 new v2 cases, not a full qualification")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    images = json.loads(args.images.read_text())
    print("IVANKA_SINGLE_ARM_ATTEMPTS", run(args.data, args.out, images,
        args.fork, args.base, args.attestation, args.binary_commit,
        jobs=args.jobs, timeout=args.timeout, limit=args.limit,
        resume=args.resume, only_v2_low_depth=args.only_v2_low_depth))


if __name__ == "__main__":
    main()
