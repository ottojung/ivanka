#!/usr/bin/env python3
"""Real end-to-end comparison using two containers of the same MiCall build.

Runs MiCall's public CLI; no direct Python monkeypatch or recreated mapping.
All clinical input and results must remain outside this public repository.
"""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from Bio import SeqIO
from Bio.Align import PairwiseAligner
from reference_catalog import load_micall_projects

DATA = Path(os.environ.get("IVANKA_DATA", "/workspace/denovo-example-io-1"))
RESULTS = Path(os.environ.get("IVANKA_PODMAN_RESULTS", "/workspace/ivanka-podman-results"))
IVA_IMAGE = os.environ.get("IVANKA_IVA_IMAGE", "localhost/ivanka-micall-iva:base")
IVANKA_IMAGE = os.environ.get("IVANKA_IVANKA_IMAGE", "localhost/ivanka-micall-ivanka:seeded")
OUTPUT_NAMES = ("conseq.csv", "conseq_all.csv", "contigs.csv", "unstitched_contigs.csv",
                "stitched_contigs.csv", "genome_coverage.csv", "genome_concordance.csv",
                "remap_counts.csv", "coverage_summary.csv", "concordance.csv",
                "nuc.csv", "amino.csv", "insertions.csv", "coverage_scores.csv")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def image_id(ref):
    return subprocess.check_output(["podman", "image", "inspect",
                                    "--format", "{{.Id}}", ref], text=True).strip()


def image_layers(ref):
    raw = subprocess.check_output(
        ["podman", "image", "inspect", "--format", "{{json .RootFS.Layers}}", ref],
        text=True).strip()
    return json.loads(raw)


def verify_identical_micall_base(iva_image, ivanka_image):
    """Compare immutable container layer digests, not mutable image tags."""
    baseline = image_layers(iva_image)
    experiment = image_layers(ivanka_image)
    if not baseline or experiment[:len(baseline)] != baseline:
        raise ValueError("Ivanka image does not derive from the selected IVA MiCall base image")


def verify_ivanka_image_binding(image):
    """Fail closed if MiCall is not actually invoking the proposed assembler."""
    code = """
import ast
import importlib.util
from pathlib import Path
spec = importlib.util.find_spec("micall.core.denovo")
assert spec is not None and spec.origin is not None
module = ast.parse(Path(spec.origin).read_text())
functions = [node for node in module.body
             if isinstance(node, ast.FunctionDef) and node.name == "run_subprocess"]
assert len(functions) == 1
commands = [node.value for node in ast.walk(functions[0])
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "command"
                    for target in node.targets)]
assert len(commands) == 1 and isinstance(commands[0], ast.List)
assert commands[0].elts and isinstance(commands[0].elts[0], ast.Constant)
assert commands[0].elts[0].value == "ivanka", "MiCall assembler command does not invoke Ivanka"
"""
    try:
        subprocess.run(["podman", "run", "--rm", "--pull=never",
                        "--entrypoint", "/opt/venv/bin/python", image, "-c", code],
                       check=True, capture_output=True, text=True, timeout=120)
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError("Ivanka image failed executable-binding verification") from exc


def score_outputs(folder, reference):
    """Inspect the final MiCall products without materializing whole CSVs in RAM."""
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.end_gap_score = -1
    scores = []
    lengths = []
    result = {}
    depth = {"positions":0,"covered_positions":0,"positions_ge_10":0,
             "positions_ge_100":0,"sum_depth":0.0,"maximum_depth":0.0}
    unique_covered=set()
    unique_ge_10=set()
    unique_ge_100=set()
    for basename in OUTPUT_NAMES:
        matches = [path for path in (folder / basename, folder / "scratch" / basename)
                   if path.is_file()]
        if not matches:
            result[basename] = {"exists": False}
            continue
        file = matches[0]  # Final collated MiCall output has priority.
        rowcount=0
        with file.open(newline="") as f:
            reader=csv.DictReader(f)
            for row in reader:
                rowcount+=1
                if basename == "conseq.csv":
                    if row.get("consensus-percent-cutoff") != "MAX":
                        continue
                    seq = row.get("sequence","").upper()
                    if seq:
                        lengths.append(len(seq))
                        if reference is not None:
                            scores.append(float(aligner.score(reference,seq)))
                elif basename == "genome_coverage.csv":
                    value = row.get("coverage")
                    if value in (None,""):
                        continue
                    try:
                        coverage=float(value)
                    except ValueError:
                        continue
                    depth["positions"]+=1
                    depth["sum_depth"]+=coverage
                    depth["maximum_depth"]=max(depth["maximum_depth"],coverage)
                    if coverage > 0: depth["covered_positions"]+=1
                    if coverage >= 10: depth["positions_ge_10"]+=1
                    if coverage >= 100: depth["positions_ge_100"]+=1
                    # Rows are not unique genome coordinates: multiple
                    # contigs may cover the same HXB2 position. Report both.
                    ref=row.get("coordinates")
                    pos=row.get("refseq_nuc_pos")
                    if ref and pos:
                        coordinate=(ref,pos)
                        if coverage > 0: unique_covered.add(coordinate)
                        if coverage >= 10: unique_ge_10.add(coordinate)
                        if coverage >= 100: unique_ge_100.add(coordinate)
        result[basename]={"exists":True,"rows":rowcount,"sha256":sha(file)}
    return {"best_hxb2_final_max_conseq_score": max(scores,default=None),
            "num_final_max_conseqs":len(lengths),
            "final_max_conseq_lengths":sorted(lengths,reverse=True),
            "coverage_depth": {
                "positions":depth["positions"],
                "covered_positions":depth["covered_positions"],
                "positions_ge_10":depth["positions_ge_10"],
                "positions_ge_100":depth["positions_ge_100"],
                "mean_depth":(depth["sum_depth"]/depth["positions"]
                              if depth["positions"] else None),
                "maximum_depth":depth["maximum_depth"],
                "unique_reference_positions_covered":len(unique_covered),
                "unique_reference_positions_ge_10":len(unique_ge_10),
                "unique_reference_positions_ge_100":len(unique_ge_100),
            },
            "outputs":result}

def compare_outputs(iva, ivanka):
    """Report downstream MiCall differences without assuming only one contig."""
    left, right = iva["outputs"], ivanka["outputs"]
    results = {}
    for filename in sorted(set(left) | set(right)):
        a = left.get(filename, {})
        b = right.get(filename, {})
        results[filename] = {
            "both_present": a.get("exists", False) and b.get("exists", False),
            "same_sha256": (a.get("sha256") == b.get("sha256")
                            if a.get("sha256") and b.get("sha256") else None),
            "iva_rows": a.get("rows"),
            "ivanka_rows": b.get("rows"),
            "row_delta": (b["rows"] - a["rows"]
                          if "rows" in a and "rows" in b else None),
        }
    return results


def best_consensus_acceptance(iva_score, ivanka_score):
    """A single good final MiCall MAX consensus is sufficient.

    Non-positive baselines use absolute comparison rather than a relative
    threshold, which would be meaningless for negative alignment scores.
    """
    threshold = (0.95*iva_score if iva_score > 0 else iva_score) if iva_score is not None else None
    return {
        "iva_score": iva_score,
        "ivanka_score": ivanka_score,
        "threshold": threshold,
        "pass": threshold is not None and ivanka_score is not None and ivanka_score >= threshold,
    }


QUALIFICATION_MAX_SECONDS = 1200
QUALIFY_SAMPLE_COUNT = 18
ORIGINAL_COHORT_SIZE = 20
IVA_INELIGIBLE_COUNT = 2


def qualification_within_cap(configured_limit, elapsed):
    """Require each sample to finish within the 20-minute cap.

    A separate IVA-only control preparation is never an alpha qualification.
    """
    return (isinstance(configured_limit, (int,float)) and
            isinstance(elapsed, (int,float)) and
            0 < configured_limit <= QUALIFICATION_MAX_SECONDS and
            0 <= elapsed <= configured_limit)


def verify_iva_eligibility(manifest_sha, eligible_names):
    """Require independently recorded IVA-only exclusions, never Ivanka-based culling.

    The private evidence file records the original frozen cohort and two
    successful, zero-MAX IVA controls independently repeated with and
    without the MiCall all-projects mode.
    """
    path = DATA / "iva_eligibility_evidence.json"
    try:
        info = json.loads(path.read_text())
        excluded = info["excluded"]
        valid = (
            info["source_count"] == ORIGINAL_COHORT_SIZE
            and info["eligible_count"] == QUALIFY_SAMPLE_COUNT
            and info["excluded_count"] == IVA_INELIGIBLE_COUNT
            and info["eligible_manifest_sha256"] == manifest_sha
            and len(excluded) == IVA_INELIGIBLE_COUNT
            and len({entry["sample"] for entry in excluded}) == IVA_INELIGIBLE_COUNT
            and not ({entry["sample"] for entry in excluded} & set(eligible_names))
            and all(
                entry[mode]["iva_exit"] == 0 and entry[mode]["iva_max"] == 0
                for entry in excluded
                for mode in ("all_projects", "without_all_projects")
            )
            and isinstance(info["source_manifest_sha256"], str)
            and len(info["source_manifest_sha256"]) == 64
        )
        if not valid:
            raise ValueError("IVA eligibility evidence is inconsistent with the frozen cohort")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Missing or invalid pinned IVA eligibility evidence") from exc
    return {
        "source_manifest_sha256": info["source_manifest_sha256"],
        "iva_ineligible_excluded": IVA_INELIGIBLE_COUNT,
        "iva_eligibility_evidence_sha256": sha(path),
    }


def project_aware_acceptance(iva_dir, ivanka_dir):
    """Score real final MiCall Ivanka consensus against final IVA consensus."""
    def sequences(directory):
        path=next((p for p in (directory/"conseq.csv", directory/"scratch"/"conseq.csv")
                   if p.is_file()),None)
        if path is None:
            raise ValueError("Missing final conseq.csv")
        with path.open(newline="") as handle:
            reader=csv.DictReader(handle)
            return [row["sequence"].upper() for row in reader
                    if row.get("consensus-percent-cutoff")=="MAX" and row.get("sequence")]
    targets=sequences(iva_dir)
    candidates=sequences(ivanka_dir)
    if not targets or not candidates:
        raise ValueError("No final MAX MiCall consensus")
    maxlen=max(map(len,targets))
    aligner=PairwiseAligner()
    aligner.mode="global"
    aligner.match_score=1
    aligner.mismatch_score=-1
    aligner.open_gap_score=-2
    aligner.extend_gap_score=-1
    best=max(aligner.score(ref,seq) for ref in targets
             if len(ref)>=0.95*maxlen for seq in candidates)
    return {"method":"final_iva_max_consensus_global_alignment",
            "iva_score":float(maxlen),"ivanka_score":float(best),
            "threshold":0.95*maxlen,"pass":best>=0.95*maxlen,
            "iva_final_max_count":len(targets),
            "ivanka_final_max_count":len(candidates)}


def baseline_provenance(row, iva_image_id, hxb2_sha256, all_projects=False):
    sample = row["sample"]
    sample_dir = DATA / "samples" / sample
    fastqs = [sample_dir / f"{sample}_L001_R{i}_001.fastq.gz" for i in (1, 2)]
    return {
        "iva_image_id": iva_image_id,
        "hxb2_sha256": hxb2_sha256,
        "all_projects": bool(all_projects),
        "fastq_sha256": [sha(f) for f in fastqs],
        "micall_project_code": row.get("micall_project_code", "").strip(),
    }


def iva_baseline_path(sample):
    return RESULTS / "iva-baselines" / (sample + ".json")


def load_iva_baseline(sample, expected_provenance):
    path = iva_baseline_path(sample)
    if not path.is_file():
        raise ValueError("No verified IVA baseline for this sample: run --mode iva first")
    stored = json.loads(path.read_text())
    if stored["provenance"] != expected_provenance:
        raise ValueError("IVA baseline provenance differs from current MiCall image, FASTQs, or HXB2")
    arm = stored["iva"]
    if arm["exit_code"] != 0 or arm["metrics"]["num_final_max_conseqs"] <= 0:
        raise ValueError("The stored IVA baseline is not a completed scored MiCall run")
    return arm


def save_iva_baseline(sample, provenance, arm):
    if arm["exit_code"] != 0 or arm["metrics"]["num_final_max_conseqs"] <= 0:
        raise ValueError("Cannot cache an incomplete or unscored IVA baseline")
    path = iva_baseline_path(sample)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".new")
    temp.write_text(json.dumps({"provenance": provenance, "iva": arm}, sort_keys=True))
    temp.replace(path)


def run_arm(row, arm, image, reference, timeout, invocation, all_projects=False):
    name = row["sample"]
    folder = RESULTS / invocation / name / arm
    folder.mkdir(parents=True, exist_ok=True)
    source = DATA / "samples" / name
    fq = [source / f"{name}_L001_R{i}_001.fastq.gz" for i in (1, 2)]
    for file in fq:
        if not file.is_file():
            raise FileNotFoundError(file)
    badcycles = folder / "bad_cycles.csv"
    badcycles.write_text("tile,cycle\n")
    container_sample = "/bench/samples/" + name
    # The manifest project is a cohort label, NOT MiCall primer project_code.
    project = row.get("micall_project_code", "").strip()
    container_name = f"ivanka-bench-{arm}-{invocation}-{hashlib.sha256(name.encode()).hexdigest()[:8]}"
    command = [
        "podman", "run", "--rm", "--pull=never", "--name", container_name,
        # Podman enforces a container lifetime even when the supervising
        # Python process receives SIGKILL.
        "--timeout", str(max(1,int(timeout)-2)), "--stop-timeout", "2",
        "-v", f"{DATA.resolve()}:/bench:ro",
        "-v", f"{RESULTS.resolve()}:/results:rw",
        # PID 1 has its own deadline: an interrupted host-side benchmark
        # cannot leave a container running indefinitely.
        "--label", f"org.ottojung.ivanka.benchmark.invocation={invocation}",
        "--entrypoint", "/usr/bin/timeout", image,
        "--signal=TERM", "--kill-after=10s",
        f"{max(1,int(timeout)-15)}s", "micall",
        "analyze", "sample",
        f"{container_sample}/{fq[0].name}",
        f"{container_sample}/{fq[1].name}",
        f"/results/{invocation}/{name}/{arm}",
        "--denovo", "--keep_scratch",
        "--bad_cycles_csv", f"/results/{invocation}/{name}/{arm}/bad_cycles.csv",
    ]
    if project:
        command.extend(["--project_code", project])
    if all_projects:
        command.append("--all_projects")
    start = time.monotonic()
    with (folder / "podman.stdout.log").open("w") as stdout, \
         (folder / "podman.stderr.log").open("w") as stderr:
        try:
            p = subprocess.run(command, stdout=stdout, stderr=stderr,
                               timeout=timeout, check=False)
            exitcode = p.returncode
        except subprocess.TimeoutExpired:
            # Killing the CLI process need not kill its Podman container.
            subprocess.run(["podman", "rm", "--force", container_name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=30, check=False)
            exitcode = 124
    result = {
        "exit_code": exitcode, "seconds": round(time.monotonic()-start, 2),
        "image_id": image_id(image), "image": image,
        "artifact_dir": str(folder.resolve()),
        "metrics": score_outputs(folder, reference),
    }
    if exitcode:
        result["error"] = (folder / "podman.stderr.log").read_text()[-1200:]
    return result


def evaluate_sample(row, args, images, checked, pinned_iva_id,
                    hxb2_hash, reference, project_catalog, invocation, deadline=None,
                    reference_panel=None):
    """Run one sample through selected real MiCall image(s), with no shared scratch."""
    name = row["sample"]
    record={"sample":name,"invocation":invocation,
            "hxb2_sha256":hxb2_hash,"status":"started"}
    started=time.monotonic()
    deadline=started+getattr(args,"sample_time_limit",1200)
    failures=0
    try:
        if deadline-time.monotonic() <= 1:
            record["status"]="sample_timeout"
            record["error"]="No per-sample time budget before starting sample"
            record["failed"]=True
            return record
        provenance=baseline_provenance(row,pinned_iva_id,hxb2_hash,getattr(args,"all_projects",False))
        record["provenance"]=provenance
        reused_baseline=None
        if args.mode=="ivanka":
            try:
                reused_baseline=load_iva_baseline(name,provenance)
                record["iva_baseline_reused"]=True
            except (ValueError,OSError,KeyError) as exc:
                if not args.allow_missing_baseline:
                    raise
                # Useful to measure real Ivanka-MiCall runtime/output while
                # preparing costly IVA controls. Never mark it as accepted.
                record["baseline_error"]=str(exc)
        arms=[arm for arm in ("iva","ivanka") if arm in checked]
        def attempt(arm):
            remaining=deadline-time.monotonic()
            if remaining <= 1:
                return arm,{"exit_code":124,
                            "error":"Per-sample time limit exhausted before arm"}
            try:
                result=run_arm(row,arm,images[arm],
                               str(reference) if row.get("project")=="NFLHIVDNA" else None,
                               min(args.timeout_per_arm,max(1,int(remaining))),
                               invocation, getattr(args,"all_projects",False))
            except Exception as exc:
                result={"exit_code":1,"error":f"{type(exc).__name__}: {exc}"}
            return arm,result

        for arm in arms:
            print(f"{name}: {arm}",flush=True)
        if args.parallel_arms and len(arms)==2:
            with ThreadPoolExecutor(max_workers=2) as arm_executor:
                arm_jobs=[arm_executor.submit(attempt,arm) for arm in arms]
                results=[task.result() for task in as_completed(arm_jobs)]
        else:
            results=[attempt(arm) for arm in arms]
        for arm,result in results:
            record[arm]=result
            if result.get("exit_code"):
                failures+=1
                if result["exit_code"]==124:
                    record["status"]="sample_timeout"
        if "iva" in record and "metrics" in record["iva"]:
            try:
                save_iva_baseline(name,provenance,record["iva"])
            except ValueError as exc:
                record["baseline_error"]=str(exc)
                failures+=1
        baseline=record.get("iva",reused_baseline)
        if "ivanka" in checked:
            if ("ivanka" in record and "metrics" in record["ivanka"] and
                baseline and baseline.get("exit_code")==0 and "metrics" in baseline):
                if project_catalog is not None and getattr(args,"diagnose_project_reference",False):
                    try:
                        from project_references import aligned_to_project_reference
                        projects=project_catalog
                        ref_iva=Path(baseline.get("artifact_dir",str(RESULTS/invocation/name/"iva")))
                        ref_ivanka=Path(record["ivanka"].get("artifact_dir",str(RESULTS/invocation/name/"ivanka")))
                        record["project_reference_alignment"]=aligned_to_project_reference(
                            ref_iva,ref_ivanka,projects,row["micall_project_code"])
                    except (OSError,KeyError,ValueError) as exc:
                        record["project_reference_error"]=str(exc)
                        # Project-specific remap is diagnostic only; the panel is authoritative.
                from reference_panel import panel_acceptance
                iva_dir=Path(baseline.get("artifact_dir",str(RESULTS/invocation/name/"iva")))
                ivanka_dir=Path(record["ivanka"].get("artifact_dir",str(RESULTS/invocation/name/"ivanka")))
                record["best_contig_acceptance"]=panel_acceptance(
                    iva_dir,ivanka_dir,reference_panel)
                record["output_comparison"]=compare_outputs(
                    baseline["metrics"],record["ivanka"]["metrics"])
                iva_depth=baseline["metrics"].get("coverage_depth")
                ivanka_depth=record["ivanka"]["metrics"].get("coverage_depth")
                if iva_depth and ivanka_depth:
                    record["coverage_comparison"]={
                        "iva":iva_depth,
                        "ivanka":ivanka_depth,
                        "covered_position_delta":(
                            ivanka_depth["covered_positions"]-
                            iva_depth["covered_positions"]),
                        "ge_10_position_delta":(
                            ivanka_depth["positions_ge_10"]-
                            iva_depth["positions_ge_10"]),
                    }
                if not record["best_contig_acceptance"]["pass"]:
                    failures+=1
            else:
                record["evaluation_error"]="Missing valid IVA baseline or completed Ivanka MiCall outputs"
                failures+=1
    except Exception as exc:
        record["status"]="error"
        record["error"]=f"{type(exc).__name__}: {exc}"
        failures+=1
    if record["status"]=="started":
        record["status"]="finished"
    record["failed"]=bool(failures)
    record["total_seconds"]=round(time.monotonic()-started,2)
    record["sample_time_limit_seconds"]=getattr(args,"sample_time_limit",1200)
    if not qualification_within_cap(record["sample_time_limit_seconds"],
                                     record["total_seconds"]):
        record["status"]="sample_timeout"
        record["failed"]=True
    return record


def failure_category(record):
    if not record.get('failed'): return None
    if record.get('status')=='sample_timeout': return 'sample_timeout'
    iva=record.get('iva')
    if not isinstance(iva,dict): return 'missing_iva_baseline'
    if iva.get('exit_code')!=0: return 'iva_pipeline_error'
    if (iva.get('metrics',{}).get('num_final_max_conseqs') or 0)==0: return 'iva_no_final_max'
    ivanka=record.get('ivanka')
    if not isinstance(ivanka,dict): return 'missing_ivanka_run'
    if ivanka.get('exit_code')!=0: return 'ivanka_pipeline_error'
    if (ivanka.get('metrics',{}).get('num_final_max_conseqs') or 0)==0: return 'ivanka_no_final_max'
    if record.get('best_contig_acceptance',{}).get('pass') is False: return 'ivanka_below_noninferiority_threshold'
    return 'other_evaluation_error'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="append",
                        help="Run only a selected sample ID (repeatable)")
    parser.add_argument("--mode", choices=("both","iva","ivanka"), default="both")
    parser.add_argument("--jobs", type=int, default=1,
                        help="Independent sample pipelines to run concurrently")
    parser.add_argument("--parallel-arms", action="store_true",
                        help="Run IVA and Ivanka concurrently within each sample")
    parser.add_argument("--allow-missing-baseline", action="store_true",
                        help="Ivanka-only diagnostic: run full MiCall without control, never claim pass")
    parser.add_argument("--timeout-per-arm", type=int, default=1180,
                        help="Per-arm bound, further limited by the shared per-sample deadline")
    parser.add_argument("--sample-time-limit", type=int, default=1200,
                        help="Maximum elapsed seconds for EACH sample, including both MiCall arms and scoring")
    parser.add_argument("--qualify",action="store_true", help="Strict 18-sample IVA-eligible alpha run requiring pinned manifest and IVA eligibility evidence")
    parser.add_argument("--diagnose-project-reference",action="store_true",
                        help="Optional expensive legacy IVA-selected project reference diagnostic; not used for acceptance")
    parser.add_argument("--all-projects",action="store_true",
                        help="Symmetrically enable MiCall --all_projects for IVA and Ivanka; recorded in baseline provenance")
    parser.add_argument("--probe",action="store_true")
    args=parser.parse_args()
    if args.jobs<1 or not 1<=args.sample_time_limit<=1200 or args.timeout_per_arm<1:
        parser.error("jobs and arm timeout must be positive; sample limit must be 1..1200 seconds")
    images={"iva":IVA_IMAGE,"ivanka":IVANKA_IMAGE}
    checked={}
    for arm,img in images.items():
        if args.mode not in ("both",arm): continue
        checked[arm]=image_id(img)
    # Even Ivanka-only runs must verify the exact IVA image that produced the
    # baseline; image tags by themselves are not immutable.
    pinned_iva_id = checked.get("iva") or image_id(IVA_IMAGE)
    if "ivanka" in checked:
        verify_identical_micall_base(IVA_IMAGE, IVANKA_IMAGE)
        verify_ivanka_image_binding(IVANKA_IMAGE)
    with (DATA/"manifest.tsv").open(newline="") as manifest:
        rows=list(csv.DictReader(manifest,delimiter="\t"))
    manifest_sample_count=len(rows)
    names=[row["sample"] for row in rows]
    if len(set(names))!=len(names):
        raise ValueError("Duplicate sample identities in manifest")
    manifest_hash=sha(DATA/"manifest.tsv")
    if args.qualify:
        expected=os.environ.get("IVANKA_EXPECTED_MANIFEST_SHA256", "")
        if args.mode!="both" or args.sample is not None or manifest_sample_count!=QUALIFY_SAMPLE_COUNT:
            raise ValueError("Full alpha requires all 18 predeclared IVA-eligible samples in one both-arm invocation")
        if not expected or manifest_hash!=expected:
            raise ValueError("Qualification manifest SHA-256 missing or mismatched")
        eligibility = verify_iva_eligibility(manifest_hash, names)
    else:
        eligibility = {}
    rows=[row for row in rows if args.sample is None or row["sample"] in args.sample]
    if not rows: raise ValueError("No samples selected")
    with (DATA/"hxb2.fasta").open() as reference_file:
        hxb2=next(SeqIO.parse(reference_file,"fasta")).seq
    projects,catalog_hash=load_micall_projects(IVA_IMAGE)
    from reference_panel import build_reference_panel,panel_sha256
    references=build_reference_panel(projects,hxb2)
    reference_panel_hash=panel_sha256(references)
    if args.probe:
        print(json.dumps({"images":checked,"sample_count":len(rows),
                          "hxb2_sha256":sha(DATA/"hxb2.fasta"),
                          "project_reference_catalog_sha256":catalog_hash,
                          "reference_panel_sha256":reference_panel_hash,
                          "reference_panel_count":len(references)},indent=2))
        return 0
    RESULTS.mkdir(parents=True,exist_ok=True)
    invocation=str(int(time.time()))+"-"+str(os.getpid())
    hxb2_hash=sha(DATA/"hxb2.fasta")
    path=RESULTS/"results.jsonl"
    failed=0
    completed_records=[]
    benchmark_start=time.monotonic()
    with path.open("a",buffering=1) as out:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures={}
            for row in rows:
                out.write(json.dumps({"sample":row["sample"],
                                      "invocation":invocation,"status":"started"})+"\n")
                task=executor.submit(evaluate_sample,row,args,images,checked,
                                     pinned_iva_id,hxb2_hash,hxb2,projects,invocation,reference_panel=references)
                futures[task]=row["sample"]
            for task in as_completed(futures):
                name=futures[task]
                try:
                    record=task.result()
                except Exception as exc:
                    record={"sample":name,"invocation":invocation,"status":"error",
                            "error":f"{type(exc).__name__}: {exc}","failed":True}
                out.write(json.dumps(record,sort_keys=True)+"\n")
                completed_records.append(record)
                if record["failed"]:
                    failed+=1
                print(name,record["status"],"fail" if record["failed"] else "ok",
                      record.get("best_contig_acceptance",{}),flush=True)
    accepted=sum(r.get("best_contig_acceptance",{}).get("pass") is True
                 for r in completed_records)
    finished_names=[r.get("sample") for r in completed_records]
    both_arms_complete=all(
        r.get("status")=="finished" and
        r.get("iva",{}).get("exit_code")==0 and
        r.get("ivanka",{}).get("exit_code")==0 and
        "metrics" in r.get("iva",{}) and "metrics" in r.get("ivanka",{})
        for r in completed_records)
    full_scope=(args.qualify and len(rows)==QUALIFY_SAMPLE_COUNT and
                len(completed_records)==QUALIFY_SAMPLE_COUNT and
                len(set(finished_names))==QUALIFY_SAMPLE_COUNT and
                set(finished_names)==set(names) and
                both_arms_complete and
                all("best_contig_acceptance" in r for r in completed_records))
    global_seconds=time.monotonic()-benchmark_start
    max_sample_seconds=max((r["total_seconds"] for r in completed_records
                            if isinstance(r.get("total_seconds"), (int,float))), default=None)
    per_sample_timing_complete=all(
        isinstance(r.get("total_seconds"),(int,float)) for r in completed_records)
    complete_noninferiority=(full_scope and per_sample_timing_complete and
                            qualification_within_cap(args.sample_time_limit,max_sample_seconds)
                            and accepted==manifest_sample_count and failed==0)
    # A wall-clock two-arm verdict requires IVA and Ivanka in one invocation.
    full_alpha_pass=(complete_noninferiority and args.mode=="both")
    cached_iva_comparison_pass=(complete_noninferiority and args.mode=="ivanka")
    reason_counts={}
    for record in completed_records:
        reason=failure_category(record)
        if reason is not None:
            reason_counts[reason]=reason_counts.get(reason,0)+1
    summary={
        "invocation":invocation,"mode":args.mode,"images":checked,
        "hxb2_sha256":hxb2_hash,"manifest_sha256":manifest_hash,
        "project_reference_catalog_sha256":catalog_hash,
        "qualification_requested":args.qualify,
        "all_projects":getattr(args,"all_projects",False),
        "manifest_sample_count":manifest_sample_count,
        "selected_samples":len(rows),"finished_samples":len(completed_records),
        "accepted_samples":accepted,
        "failed_samples":[r["sample"] for r in completed_records if r["failed"]],
        "failure_categories":reason_counts,
        "global_seconds":round(global_seconds,2),
        "sample_limit_seconds":args.sample_time_limit,
        "max_sample_seconds":(round(max_sample_seconds,2) if max_sample_seconds is not None else None),
        "reference_panel_sha256":reference_panel_hash,
        "reference_panel_count":len(references),
        **eligibility,
        "jobs":args.jobs,"parallel_arms":args.parallel_arms,
        "allow_missing_baseline":args.allow_missing_baseline,
        "full_alpha_pass":full_alpha_pass,
        "cached_iva_comparison_pass":cached_iva_comparison_pass,
        "note":"Full alpha requires all 18 IVA-eligible samples in one complete A/B run; EACH sample has its own 20-minute budget, with no whole-set deadline. Ivanka-only comparisons are reported separately."
    }
    (RESULTS/f"summary-{invocation}.json").write_text(
        json.dumps(summary,indent=2,sort_keys=True))
    print("FULL_ALPHA_PASS" if full_alpha_pass else "FULL_ALPHA_NOT_PASSED",
          f"{accepted}/{manifest_sample_count} full-pipeline comparisons",
          flush=True)
    return 1 if failed or (args.qualify and not full_alpha_pass) else 0

if __name__=="__main__":
    raise SystemExit(main())
