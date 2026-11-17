"""Host-only, fail-closed admission for a single expensive 198+400 rerun.

This NEVER invokes MiCall or starts a benchmark. A successful assessment
only means technical preparation passed; the owner must authorize the run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from benchmarks.assembler_bench.exact_cache import append
from benchmarks.assembler_bench.minimal_image_attestation import verify as verify_minimal
from .hxb2_cohort import attestation
from .micall_checkpoint import existing_case, identity
from .physical_inputs import attest as physical_attestation
from .real_resume import verify_collection
from .real_shared_controls import load as shared_iva_load
from .real_progress_bridge import verify_physical_smoke
from .run_synthetic import cohort_rows

SCHEMA="ivanka.expanded.restart_preflight.v1"
BASE="8458f9e5d34c39a6694b1fb6a40e055d7ce89553"
MIN_FREE_BYTES=60*1024**3
PODMAN_CONF="/workspace/ivanka-podman-overlay-20261103/storage.conf"
PODMAN_STORE="/workspace/ivanka-podman-overlay-20261103/store"


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda:source.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def git_master(root):
    return subprocess.check_output(
        ["git","-C",str(root),"ls-remote","origin","refs/heads/master"],
        text=True,timeout=30).split()[0]


def ensure_runner_source():
    """Freeze the full external runner, not merely the seven images."""
    repo=Path(__file__).resolve().parents[2]
    def git(*args):
        return subprocess.check_output(
            ["git","-C",str(repo),*args],text=True,timeout=30).strip()
    if git("status","--porcelain"):
        raise ValueError("benchmark runner has uncommitted changes")
    branch=git("branch","--show-current")
    commit=git("rev-parse","HEAD")
    if not branch or len(commit)!=40:
        raise ValueError("benchmark runner requires an exact committed branch")
    remote=git("ls-remote","origin",f"refs/heads/{branch}").split()
    if not remote or remote[0]!=commit:
        raise ValueError("benchmark runner branch commit is not published")
    paths=("benchmarks/expanded/fork_micall_real.py",
           "benchmarks/expanded/fork_micall_synthetic.py",
           "benchmarks/expanded/real_resume.py",
           "benchmarks/expanded/real_shared_controls.py",
           "benchmarks/expanded/real_matrix.py",
           "benchmarks/expanded/restart_preflight.py",
           "benchmarks/podman_full_micall.py",
           "benchmarks/fork_micall_binding.py",
           "benchmarks/assembler_bench/minimal_image_attestation.py")
    return {"repository":"https://github.com/ottojung/ivanka",
            "branch":branch,"commit":commit,
            "files_sha256":{path:sha(repo/path) for path in paths}}


def ensure_podman_store():
    import os
    if os.environ.get("CONTAINERS_STORAGE_CONF")!=PODMAN_CONF:
        raise ValueError("benchmark Podman storage configuration differs")
    graph=subprocess.check_output(
        ["podman","info","--format","{{.Store.GraphRoot}}"],
        text=True,timeout=30).strip()
    if graph!=PODMAN_STORE:
        raise ValueError("benchmark Podman image store changed")
    return {"config":PODMAN_CONF,"graphroot":graph}


def ensure_images(images, attestation_file, sources, baseline):
    witness=json.loads(Path(attestation_file).read_text())
    if verify_minimal(images,sources,baseline)!=witness:
        raise ValueError("live source/image verification differs from pinned proof")
    if witness.get("schema")!="ivanka.assembler-bench.minimal-fork-images.v1":
        raise ValueError("current rerun requires external minimal-image attestation")
    if len({v["source_commit"] for v in witness["images"].values()})!=7:
        raise ValueError("seven distinct assembler source commits required")
    return {"attestation_sha256":sha(attestation_file),
            "images":images,"baseline_commit":baseline,
            "source_commits":{name:x["source_commit"]
                              for name,x in witness["images"].items()}}


def ensure_synthetic_smoke(folder, input_root, images, truth):
    root=Path(folder)
    frozen=json.loads((root/"run_manifest.json").read_text())
    summary=json.loads((root/"attempt_summary.json").read_text())
    rows=[json.loads(line) for line in (root/"results.jsonl").read_text().splitlines()]
    expected={row[0]:row for row in cohort_rows(input_root)}
    if (len(rows)!=1 or frozen.get("limit")!=1 or
            frozen.get("images")!=images or
            frozen.get("truth_proof")!=truth or
            summary.get("cases_attempted")!=1 or
            summary.get("failed_arms")!=0 or
            summary.get("result_sha256")!=sha(root/"results.jsonl")):
        raise ValueError("seven-arm synthetic smoke is incomplete or source-unpinned")
    row=rows[0]
    if row["id"] not in expected:
        raise ValueError("synthetic smoke sample not in frozen cohort")
    case=expected[row["id"]]
    actual=existing_case(root/row["id"],identity(row["id"],case[2],truth),images)
    if actual!=row or any(arm["status"]!="success" for arm in row["results"].values()):
        raise ValueError("synthetic smoke fails independent MiCall evidence check")
    return {"case_id":row["id"],"seven_successful_arms":True,
            "result_sha256":sha(root/"results.jsonl")}


def ensure_targeted_smoke(folder, input_root, images, truth):
    root=Path(folder)
    frozen=json.loads((root/"run_manifest.json").read_text())
    ids=frozen.get("sample_ids",[])
    if (not frozen.get("diagnostic_only") or frozen.get("not_qualifying") is not True
            or frozen.get("images")!=images or len(ids)<3 or len(set(ids))!=len(ids)
            or frozen.get("cohort_sha256")!=truth["cohort_sha256"]):
        raise ValueError("adversarial synthetic smoke is not properly source pinned")
    rows=[json.loads(line) for line in (root/"results.jsonl").read_text().splitlines()]
    if [r["id"] for r in rows]!=list(ids):
        raise ValueError("adversarial synthetic smoke is unfinished")
    sources={row[0]:row for row in cohort_rows(input_root)}
    for row in rows:
        case=sources[row["id"]]
        actual=existing_case(root/row["id"],identity(row["id"],case[2],truth),images)
        if actual!=row or any(x["status"]!="success" for x in row["results"].values()):
            raise ValueError("adversarial MiCall integration failed")
    return {"cases":ids,"result_sha256":sha(root/"results.jsonl"),
            "arms_successful":len(rows)*7}


def ensure_shared_iva_smoke(folder, images):
    """Verify only one genuine IVA control is used by two independent tools."""
    root=Path(folder)
    pinned=json.loads((root/"run_manifest.json").read_text())
    sample=pinned.get("selected_sample")
    if (pinned.get("schema")!="ivanka.expanded.fork_micall_real.v2"
            or not isinstance(sample,str)
            or set(pinned.get("selected_tools",[]))!={"ivanka","spades"}
            or pinned.get("images")!=images
            or pinned.get("control_policy")!="one_attested_iva_run_per_sample"):
        raise ValueError("shared IVA pilot has no frozen two-tool source witness")
    controls=shared_iva_load(
        root,root/"shared-iva-controls.json",{sample},images)
    original=verify_collection(root/"ivanka",{sample},images,
                               "ivanka",root/"run_manifest.json")
    candidate=verify_collection(
        root/"spades",{sample},images,"spades",root/"run_manifest.json",
        shared_controls=controls)
    if (set(original)!={sample} or set(candidate)!={sample}
            or original[sample].get("iva_baseline_reused") is True
            or candidate[sample].get("iva_baseline_reused") is not True
            or candidate[sample]["iva"]["seconds"]!=original[sample]["iva"]["seconds"]
            or candidate[sample]["iva"]["image_id"]!=images["iva"]
            or candidate[sample]["ivanka"]["image_id"]!=images["spades"]
            or candidate[sample]["ivanka"]["exit_code"]!=0):
        raise ValueError("shared IVA pilot does not reuse original control exactly")
    return {"sample":sample,"shared_control_verified":True,
            "fresh_iva_runs":1,"candidate_only_runs":1,
            "control_manifest_sha256":sha(root/"shared-iva-controls.json")}


def ensure_exact_smoke(cache_syn, cache_real, synth_smoke, real_smoke, images):
    source=json.loads((Path(synth_smoke)/"clonal-s000"/"matrix.json").read_text())
    sample=source["id"]
    for tool,record in source["results"].items():
        expected=record["final_dominant"]["conseq_csv_sha256"]
        values,profile=append({},cache_syn,"synthetic",sample,tool,
                              expected,images[tool])
        if len(values)<30 or not profile or len(profile["full_span"])<1:
            raise ValueError("synthetic exact coverage missing for "+tool)
    physical=verify_physical_smoke(real_smoke,images)
    sample=physical["sample"]
    file=Path(real_smoke)/"ivanka"/"results.jsonl"
    row=json.loads(file.read_text().strip())
    for arm,tool in (("iva","iva"),("ivanka","ivanka")):
        record=row[arm]
        expected=record["metrics"]["outputs"]["conseq.csv"]["sha256"]
        values,profile=append({},cache_real,"real",sample,arm,
                              expected,images[tool],candidate="ivanka")
        if len(values)<30 or not profile or len(profile["full_span"])<1:
            raise ValueError("physical exact coverage missing for "+tool)
    return {"synthetic_arms":7,"physical_arms":2,
            "metrics_per_arm_at_least":30}


def assess(*,root,images,sources,attestation_file,real_data,
           synthetic_data,synthetic_smoke,targeted_smoke,real_smoke,
           shared_iva_smoke,exact_synthetic,exact_real,baseline=BASE,
           min_free_bytes=MIN_FREE_BYTES):
    report={"schema":SCHEMA,"status":"BLOCKED","benchmark_started":False,
            "requires_owner_authorization":True,"blockers":[],
            "checks":{}}
    def check(name,action):
        try:
            report["checks"][name]=action()
        except Exception as error:
            report["blockers"].append(
                f"{name}: {type(error).__name__}: {error}")
    check("runner_source_integrity",ensure_runner_source)
    check("podman_store_integrity",ensure_podman_store)
    check("image_integrity",lambda:ensure_images(
          images,attestation_file,sources,baseline))
    check("physical_input_integrity",lambda:physical_attestation(real_data))
    check("synthetic_input_integrity",lambda:attestation(synthetic_data,expected=400))
    if "synthetic_input_integrity" in report["checks"]:
        truth=report["checks"]["synthetic_input_integrity"]
        check("synthetic_seven_arm_smoke",lambda:ensure_synthetic_smoke(
              synthetic_smoke,synthetic_data,images,truth))
        check("adversarial_synthetic_smoke",lambda:ensure_targeted_smoke(
              targeted_smoke,synthetic_data,images,truth))
    check("real_six_pair_smoke",lambda:verify_physical_smoke(real_smoke,images))
    check("shared_iva_control_reuse",lambda:ensure_shared_iva_smoke(
          shared_iva_smoke,images))
    if "real_six_pair_smoke" in report["checks"]:
        check("exact_coverage_sidecars",lambda:ensure_exact_smoke(
              exact_synthetic,exact_real,synthetic_smoke,real_smoke,images))
    free=shutil.disk_usage(root).free
    report["checks"]["free_workspace_bytes"]=free
    report["checks"]["minimum_free_bytes"]=min_free_bytes
    if free<min_free_bytes:
        report["blockers"].append(
            "storage: insufficient free workspace for a reliable 598-case run")
    check("fork_master",lambda:git_master(next(iter(sources.values()))))
    if report["checks"].get("fork_master")!=baseline:
        report["blockers"].append(
            "baseline: fork master has not been fast-forwarded to frozen clinical MiCall")
    if not report["blockers"]:
        report["status"]="TECHNICALLY_READY_PENDING_OWNER_AUTHORIZATION"
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("root","images","sources","attestation","real","synthetic",
                 "synthetic-smoke","targeted-smoke","real-smoke","shared-iva-smoke",
                 "exact-synthetic",
                 "exact-real","output"):
        parser.add_argument("--"+name,required=True)
    args=parser.parse_args()
    report=assess(
        root=Path(args.root),
        images=json.loads(Path(args.images).read_text()),
        sources=json.loads(Path(args.sources).read_text()),
        attestation_file=Path(args.attestation),real_data=Path(args.real),
        synthetic_data=Path(args.synthetic),
        synthetic_smoke=Path(args.synthetic_smoke),
        targeted_smoke=Path(args.targeted_smoke),
        real_smoke=Path(args.real_smoke),
        shared_iva_smoke=Path(args.shared_iva_smoke),
        exact_synthetic=Path(args.exact_synthetic),
        exact_real=Path(args.exact_real))
    destination=Path(args.output)
    with destination.open("x") as target:
        json.dump(report,target,sort_keys=True,indent=2)
        target.write("\n")
    print("RESTART_PREFLIGHT",report["status"],
          len(report["blockers"]),"blockers",flush=True)
    for item in report["blockers"]:
        print("BLOCKER",item,flush=True)
    return 0 if not report["blockers"] else 2

if __name__=="__main__":
    raise SystemExit(main())
