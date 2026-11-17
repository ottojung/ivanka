"""Resumable, source-attested 198-real MiCall comparisons for seven assemblers.

Each attempt is immutable. Only independently authenticated terminal sample
records can be recovered; incomplete samples are rerun in a new attempt.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

from benchmarks.fork_micall_binding import VARIABLES, SHARED_CONTROL_MANIFEST
from .adapters import ASSEMBLERS
from .fork_micall_synthetic import checked_images
from .micall_lock import exclusive_lock
from .real_matrix import MANIFEST
from .real_resume import collect, commit, digest, verify_collection
from .real_shared_controls import certify, load

SCHEMA = "ivanka.expanded.fork_micall_real.v2"


def validate_real(data, sample):
    root = Path(data)
    manifest_file = root / "manifest.tsv"
    if digest(manifest_file) != MANIFEST:
        raise ValueError("real 198 cohort has changed from frozen input manifest")
    with manifest_file.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != 198 or len({row["sample"] for row in rows}) != 198:
        raise ValueError("not the original unique 198 physical samples")
    if sample is not None and sample not in {row["sample"] for row in rows}:
        raise ValueError("development sample absent from frozen real cohort")
    return MANIFEST


def command(name, *, jobs, sample=None, samples=None, shared=False):
    """Use unmodified clinical MiCall, original reads, and 33-reference scorer."""
    args = [sys.executable,
            str(Path(__file__).resolve().parents[1] / "podman_full_micall.py"),
            "--mode", "ivanka" if shared else "both", "--jobs", str(jobs),
            "--all-projects", "--timeout-per-arm", "1800",
            "--sample-time-limit", "1800", "--diagnostic-90-floor"]
    if not shared:
        args.append("--parallel-arms")
    if name != "ivanka":
        args.extend(["--candidate-assembler", name])
    selected = [sample] if sample is not None else (samples or [])
    for name in selected:
        args.extend(["--sample", name])
    return args


def source_manifest(data, images, attestation_file, base, sample, selected):
    root = Path(__file__).resolve()
    source = [root, root.with_name("real_resume.py"),
              root.with_name("real_shared_controls.py"),
              root.with_name("micall_lock.py"),
              root.parents[1] / "podman_full_micall.py",
              root.parents[1] / "fork_micall_binding.py",
              root.with_name("real_matrix.py"),
              root.parents[1] / "assembler_bench/image_source_attestation.py",
              root.parents[1] / "assembler_bench/dedicated_image_attestation.py",
              root.parents[1] / "assembler_bench/fork_image_attestation.py",
              root.parents[1] / "assembler_bench/minimal_image_attestation.py"]
    return {
        "schema": SCHEMA, "qualified": False, "status": "ATTEMPTED_NOT_QUALIFIED",
        "expected_samples": 198, "selected_sample": sample,
        "control_policy": "one_attested_iva_run_per_sample",
        "selected_tools": selected, "images": images,
        "frozen_baseline_identity": base,
        "real_manifest_sha256": validate_real(data, sample),
        "fork_attestation_sha256": digest(attestation_file),
        "source_files_sha256": {path.name: digest(path) for path in source},
    }


def samples_in_cohort(data, sample):
    with (Path(data)/"manifest.tsv").open(newline="") as stream:
        names = [row["sample"] for row in csv.DictReader(stream, delimiter="\t")]
    return {sample} if sample is not None else set(names)


def environment(data, output, images, fork, base, attestation_file):
    result = os.environ.copy()
    result.update({
        "IVANKA_DATA": str(Path(data).resolve()),
        "IVANKA_IVA_IMAGE": images["iva"],
        "IVANKA_IVA_BASELINE_CACHE": str((output / "iva-baselines").resolve()),
        "IVANKA_PODMAN_LIFECYCLE": "detached",
        VARIABLES[0]: str(Path(attestation_file).resolve()),
        VARIABLES[1]: str(Path(fork).resolve()),
        VARIABLES[2]: str((output / "source_verified_images.json").resolve()),
        VARIABLES[3]: base,
    })
    return result


def write_json(path, value):
    temporary = Path(str(path) + ".partial")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)


def one_tool(name, root, sample_ids, jobs, images, env, pinned,
             shared_controls=None, control_manifest=None):
    folder = root / name
    folder.mkdir(exist_ok=True)
    existing = folder / "checkpoints.json"
    if existing.exists():
        verify_collection(folder, sample_ids, images, name, root/"run_manifest.json",
                          allow_additional=True,shared_controls=shared_controls)
    records, witnesses = collect(folder, sample_ids, images, name,
                                shared_controls)
    missing = sorted(sample_ids-set(records))
    exit_code = None
    if missing:
        index = next((i for i in range(1000)
                      if not (folder/f"attempt-{i:03d}").exists()), None)
        if index is None:
            raise ValueError("too many interrupted attempts")
        attempt = folder / f"attempt-{index:03d}"
        attempt.mkdir()
        # ALWAYS enumerate the exact remaining sample IDs. Omitting --sample
        # would silently expand a one-case smoke into the entire 198 cohort.
        args = command(name, jobs=jobs, samples=missing,
                       shared=shared_controls is not None)
        on_cli = [args[i + 1] for i, arg in enumerate(args[:-1])
                  if arg == "--sample"]
        if len(on_cli) != len(missing) or set(on_cli) != set(missing):
            raise ValueError("MiCall subprocess sample scope differs from pending set")
        scoped = env | {"IVANKA_IVANKA_IMAGE": images[name],
                        "IVANKA_PODMAN_RESULTS": str(attempt)}
        if control_manifest is not None:
            scoped[SHARED_CONTROL_MANIFEST]=str(control_manifest)
        with (attempt/"runner.log").open("x") as log:
            execution = subprocess.run(
                args, env=scoped, cwd=Path(__file__).resolve().parents[2],
                stdout=log, stderr=subprocess.STDOUT, check=False)
        exit_code = execution.returncode
        records,witnesses = collect(folder,sample_ids,images,name,
                                   shared_controls)
    proof = commit(folder,records,witnesses,root/"run_manifest.json")
    status = {"exit_code":exit_code, "image_id":images[name],
              "results_jsonl":str(folder/"results.jsonl"),
              "results_sha256":proof["results_sha256"],
              "checkpoint_manifest":str(folder/"checkpoints.json"),
              "source_manifest":str(root/"run_manifest.json"),
              "images":images,
              "control_manifest":str(control_manifest) if control_manifest else None,
              "shared_iva_control":shared_controls is not None,
              "sample_count":len(records),
              "missing_samples":len(sample_ids-set(records)),
              "failed_terminal_samples":sum(
                  record.get("failed") is True for record in records.values()),
              "complete":len(records)==len(sample_ids)}
    print("FORK_MiCall_REAL_TOOL",name,"complete",status["sample_count"],
          "of",len(sample_ids),"failed",status["failed_terminal_samples"],
          flush=True)
    return status


def run(data, output, images, fork, base, attestation_file, *,
        jobs=10, sample=None, selected=None, resume=False):
    if jobs not in range(1,11):
        raise ValueError("real MiCall worker count must be 1..10")
    if selected is None:
        selected = tuple(tool for tool in ASSEMBLERS if tool!="iva")
    if (not selected or len(selected)!=len(set(selected))
            or set(selected)-(set(ASSEMBLERS)-{"iva"})):
        raise ValueError("unknown or duplicate candidate tool")
    root = Path(output).resolve()
    with exclusive_lock(root):
        return _run(data, root, images, fork, base, attestation_file,
                    jobs=jobs,sample=sample,selected=selected,resume=resume)


def _run(data, root, images, fork, base, attestation_file, *,
         jobs, sample, selected, resume):
    checked_images(images, attestation_file, fork, base)
    pinned = source_manifest(data,images,attestation_file,base,sample,list(selected))
    sample_ids = samples_in_cohort(data, sample)
    manifest = root / "run_manifest.json"
    if resume:
        if not manifest.is_file() or json.loads(manifest.read_text())!=pinned:
            raise ValueError("resumed real run source/runner/image manifest differs")
        if json.loads((root/"source_verified_images.json").read_text())!=images:
            raise ValueError("resumed seven-image map differs")
    else:
        root.mkdir(parents=True,exist_ok=False)
        write_json(manifest,pinned)
        write_json(root/"source_verified_images.json",images)
    env=environment(data,root,images,fork,base,attestation_file)
    recorded={}
    ordered=sorted(selected,key=lambda name:name!="ivanka")
    sharing="ivanka" in ordered and len(ordered)>1
    control_path=None
    controls=None
    for name in ordered:
        if name!="ivanka" and sharing:
            if control_path is None:
                control_path=certify(root,sample_ids,images)
            controls=load(root,control_path,sample_ids,images)
        recorded[name]=one_tool(
            name,root,sample_ids,min(jobs,5) if name=="ivanka" else jobs,
            images,env,pinned,shared_controls=controls if name!="ivanka" else None,
            control_manifest=control_path if name!="ivanka" else None)
        write_json(root/"execution_manifest.json",recorded)
    full = (sample is None and set(selected)==set(ASSEMBLERS)-{"iva"}
            and all(v["complete"] for v in recorded.values()))
    summary = {"schema":SCHEMA,"status":"ATTEMPTED_NOT_QUALIFIED",
               "all_six_candidate_runs_attempted":full,
               "source_manifest_sha256":digest(manifest),
               "execution_manifest_sha256":digest(root/"execution_manifest.json"),
               "tools":recorded}
    write_json(root/"attempt_summary.json",summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ("data","out","images","attestation","fork","base"):
        parser.add_argument("--"+flag,required=True)
    parser.add_argument("--jobs",type=int,default=10)
    parser.add_argument("--sample",help="unqualified development case only")
    parser.add_argument("--tools",nargs="+",help="unqualified candidate subset")
    parser.add_argument("--resume",action="store_true")
    args=parser.parse_args()
    result=run(args.data,args.out,json.loads(Path(args.images).read_text()),
               args.fork,args.base,args.attestation,
               jobs=args.jobs,sample=args.sample,selected=args.tools,
               resume=args.resume)
    print("FORK_SOURCE_VERIFIED_REAL_ATTEMPTED",result["status"])
    print("NOT QUALIFIED: join 198 real + 400 HXB2 and independently prove PSI.")


if __name__=="__main__":
    main()
