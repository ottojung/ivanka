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

DATA = Path(os.environ.get("RIVA_DATA", "/workspace/denovo-example-io-1"))
RESULTS = Path(os.environ.get("RIVA_PODMAN_RESULTS", "/workspace/riva-podman-results"))
IVA_IMAGE = os.environ.get("RIVA_IVA_IMAGE", "localhost/riva-micall-iva:base")
RIVA_IMAGE = os.environ.get("RIVA_RIVA_IMAGE", "localhost/riva-micall-riva:seeded")
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


def verify_identical_micall_base(iva_image, riva_image):
    """Compare immutable container layer digests, not mutable image tags."""
    baseline = image_layers(iva_image)
    experiment = image_layers(riva_image)
    if not baseline or experiment[:len(baseline)] != baseline:
        raise ValueError("Riva image does not derive from the selected IVA MiCall base image")


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
                        scores.append(float(aligner.score(reference,seq)))
                        lengths.append(len(seq))
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
        result[basename]={"exists":True,"rows":rowcount,"sha256":sha(file)}
    return {"best_hxb2_final_max_conseq_score": max(scores,default=None),
            "num_final_max_conseqs":len(scores),
            "final_max_conseq_lengths":sorted(lengths,reverse=True),
            "coverage_depth": {
                "positions":depth["positions"],
                "covered_positions":depth["covered_positions"],
                "positions_ge_10":depth["positions_ge_10"],
                "positions_ge_100":depth["positions_ge_100"],
                "mean_depth":(depth["sum_depth"]/depth["positions"]
                              if depth["positions"] else None),
                "maximum_depth":depth["maximum_depth"],
            },
            "outputs":result}

def compare_outputs(iva, riva):
    """Report downstream MiCall differences without assuming only one contig."""
    left, right = iva["outputs"], riva["outputs"]
    results = {}
    for filename in sorted(set(left) | set(right)):
        a = left.get(filename, {})
        b = right.get(filename, {})
        results[filename] = {
            "both_present": a.get("exists", False) and b.get("exists", False),
            "same_sha256": (a.get("sha256") == b.get("sha256")
                            if a.get("sha256") and b.get("sha256") else None),
            "iva_rows": a.get("rows"),
            "riva_rows": b.get("rows"),
            "row_delta": (b["rows"] - a["rows"]
                          if "rows" in a and "rows" in b else None),
        }
    return results


def best_consensus_acceptance(iva_score, riva_score):
    """A single good final MiCall MAX consensus is sufficient.

    Non-positive baselines use absolute comparison rather than a relative
    threshold, which would be meaningless for negative alignment scores.
    """
    threshold = (0.95*iva_score if iva_score > 0 else iva_score) if iva_score is not None else None
    return {
        "iva_score": iva_score,
        "riva_score": riva_score,
        "threshold": threshold,
        "pass": threshold is not None and riva_score is not None and riva_score >= threshold,
    }


def baseline_provenance(row, iva_image_id, hxb2_sha256):
    sample = row["sample"]
    sample_dir = DATA / "samples" / sample
    fastqs = [sample_dir / f"{sample}_L001_R{i}_001.fastq.gz" for i in (1, 2)]
    return {
        "iva_image_id": iva_image_id,
        "hxb2_sha256": hxb2_sha256,
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
    if arm["exit_code"] != 0 or arm["metrics"]["best_hxb2_final_max_conseq_score"] is None:
        raise ValueError("The stored IVA baseline is not a completed scored MiCall run")
    return arm


def save_iva_baseline(sample, provenance, arm):
    if arm["exit_code"] != 0 or arm["metrics"]["best_hxb2_final_max_conseq_score"] is None:
        raise ValueError("Cannot cache an incomplete or unscored IVA baseline")
    path = iva_baseline_path(sample)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".new")
    temp.write_text(json.dumps({"provenance": provenance, "iva": arm}, sort_keys=True))
    temp.replace(path)


def run_arm(row, arm, image, reference, timeout, invocation):
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
    container_name = f"riva-bench-{arm}-{invocation}-{hashlib.sha256(name.encode()).hexdigest()[:8]}"
    command = [
        "podman", "run", "--rm", "--pull=never", "--name", container_name,
        "-v", f"{DATA.resolve()}:/bench:ro",
        "-v", f"{RESULTS.resolve()}:/results:rw",
        # PID 1 has its own deadline: an interrupted host-side benchmark
        # cannot leave a container running indefinitely.
        "--label", f"org.ottojung.riva.benchmark.invocation={invocation}",
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
        "metrics": score_outputs(folder, reference),
    }
    if exitcode:
        result["error"] = (folder / "podman.stderr.log").read_text()[-1200:]
    return result


def evaluate_sample(row, args, images, checked, pinned_iva_id,
                    hxb2_hash, reference, invocation, deadline):
    """Run one sample through selected real MiCall image(s), with no shared scratch."""
    name = row["sample"]
    record={"sample":name,"invocation":invocation,
            "hxb2_sha256":hxb2_hash,"status":"started"}
    started=time.monotonic()
    failures=0
    try:
        if deadline-time.monotonic() <= 1:
            record["status"]="global_timeout"
            record["error"]="No global time budget before starting sample"
            record["failed"]=True
            return record
        provenance=baseline_provenance(row,pinned_iva_id,hxb2_hash)
        reused_baseline=None
        if args.mode=="riva":
            reused_baseline=load_iva_baseline(name,provenance)
            record["iva_baseline_reused"]=True
        for arm in ("iva","riva"):
            if arm not in checked:
                continue
            remaining=deadline-time.monotonic()
            if remaining <= 1:
                record["status"]="global_timeout"
                record["error"]="No global time budget for next assembler arm"
                failures+=1
                break
            print(f"{name}: {arm}",flush=True)
            try:
                result=run_arm(row,arm,images[arm],str(reference),
                               min(args.timeout_per_arm,max(1,int(remaining))),
                               invocation)
                record[arm]=result
                if result["exit_code"]:
                    failures+=1
            except Exception as exc:
                record[arm]={"error":f"{type(exc).__name__}: {exc}"}
                failures+=1
        if "iva" in record and "metrics" in record["iva"]:
            try:
                save_iva_baseline(name,provenance,record["iva"])
            except ValueError as exc:
                record["baseline_error"]=str(exc)
                failures+=1
        baseline=record.get("iva",reused_baseline)
        if "riva" in checked:
            if ("riva" in record and "metrics" in record["riva"] and
                baseline and baseline.get("exit_code")==0 and "metrics" in baseline):
                a=baseline["metrics"]["best_hxb2_final_max_conseq_score"]
                b=record["riva"]["metrics"]["best_hxb2_final_max_conseq_score"]
                record["best_contig_acceptance"]=best_consensus_acceptance(a,b)
                record["output_comparison"]=compare_outputs(
                    baseline["metrics"],record["riva"]["metrics"])
                iva_depth=baseline["metrics"].get("coverage_depth")
                riva_depth=record["riva"]["metrics"].get("coverage_depth")
                if iva_depth and riva_depth:
                    record["coverage_comparison"]={
                        "iva":iva_depth,
                        "riva":riva_depth,
                        "covered_position_delta":(
                            riva_depth["covered_positions"]-
                            iva_depth["covered_positions"]),
                        "ge_10_position_delta":(
                            riva_depth["positions_ge_10"]-
                            iva_depth["positions_ge_10"]),
                    }
                if not record["best_contig_acceptance"]["pass"]:
                    failures+=1
            else:
                record["evaluation_error"]="Missing valid IVA baseline or completed Riva MiCall outputs"
                failures+=1
    except Exception as exc:
        record["status"]="error"
        record["error"]=f"{type(exc).__name__}: {exc}"
        failures+=1
    if record["status"]=="started":
        record["status"]="finished"
    record["failed"]=bool(failures)
    record["total_seconds"]=round(time.monotonic()-started,2)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="append",
                        help="Run only a selected sample ID (repeatable)")
    parser.add_argument("--mode", choices=("both","iva","riva"), default="both")
    parser.add_argument("--jobs", type=int, default=1,
                        help="Independent sample pipelines to run concurrently")
    parser.add_argument("--timeout-per-arm", type=int, default=1170)
    parser.add_argument("--total-time-limit", type=int, default=1180,
                        help="Global seconds for all samples, default below 20-minute hard cap")
    parser.add_argument("--probe",action="store_true")
    args=parser.parse_args()
    if args.jobs<1 or args.total_time_limit<1 or args.timeout_per_arm<1:
        parser.error("jobs and both time limits must be positive")
    images={"iva":IVA_IMAGE,"riva":RIVA_IMAGE}
    checked={}
    for arm,img in images.items():
        if args.mode not in ("both",arm): continue
        checked[arm]=image_id(img)
    # Even Riva-only runs must verify the exact IVA image that produced the
    # baseline; image tags by themselves are not immutable.
    pinned_iva_id = checked.get("iva") or image_id(IVA_IMAGE)
    if "riva" in checked:
        verify_identical_micall_base(IVA_IMAGE, RIVA_IMAGE)
    with (DATA/"manifest.tsv").open(newline="") as manifest:
        rows=list(csv.DictReader(manifest,delimiter="\t"))
    manifest_sample_count=len(rows)
    rows=[row for row in rows if args.sample is None or row["sample"] in args.sample]
    if not rows: raise ValueError("No samples selected")
    with (DATA/"hxb2.fasta").open() as reference_file:
        hxb2=next(SeqIO.parse(reference_file,"fasta")).seq
    if args.probe:
        print(json.dumps({"images":checked,"sample_count":len(rows),
                          "hxb2_sha256":sha(DATA/"hxb2.fasta")},indent=2))
        return 0
    RESULTS.mkdir(parents=True,exist_ok=True)
    invocation=str(int(time.time()))+"-"+str(os.getpid())
    hxb2_hash=sha(DATA/"hxb2.fasta")
    path=RESULTS/"results.jsonl"
    failed=0
    completed_records=[]
    benchmark_start=time.monotonic()
    deadline=benchmark_start+args.total_time_limit
    with path.open("a",buffering=1) as out:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures={}
            for row in rows:
                out.write(json.dumps({"sample":row["sample"],
                                      "invocation":invocation,"status":"started"})+"\n")
                task=executor.submit(evaluate_sample,row,args,images,checked,
                                     pinned_iva_id,hxb2_hash,hxb2,invocation,deadline)
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
    full_scope=(args.sample is None and len(rows)==manifest_sample_count
                and manifest_sample_count==7)
    full_alpha_pass=(full_scope and args.mode in ("both","riva")
                     and accepted==manifest_sample_count and failed==0)
    summary={
        "invocation":invocation,"mode":args.mode,"images":checked,
        "hxb2_sha256":hxb2_hash,"manifest_sha256":sha(DATA/"manifest.tsv"),
        "manifest_sample_count":manifest_sample_count,
        "selected_samples":len(rows),"finished_samples":len(completed_records),
        "accepted_samples":accepted,
        "failed_samples":[r["sample"] for r in completed_records if r["failed"]],
        "global_seconds":round(time.monotonic()-benchmark_start,2),
        "global_limit_seconds":args.total_time_limit,
        "full_alpha_pass":full_alpha_pass,
        "note":"A subset or an IVA-only baseline run is never full alpha."
    }
    (RESULTS/f"summary-{invocation}.json").write_text(
        json.dumps(summary,indent=2,sort_keys=True))
    print("FULL_ALPHA_PASS" if full_alpha_pass else "FULL_ALPHA_NOT_PASSED",
          f"{accepted}/{manifest_sample_count} full-pipeline comparisons",
          flush=True)
    return 1 if failed else 0

if __name__=="__main__":
    raise SystemExit(main())
