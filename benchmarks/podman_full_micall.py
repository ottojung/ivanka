#!/usr/bin/env python3
"""Real end-to-end comparison using two containers of the same MiCall build.

Runs MiCall's public CLI; no direct Python monkeypatch or recreated mapping.
All clinical input and results must remain outside this public repository.
"""
import argparse
import csv
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
RIVA_IMAGE = os.environ.get("RIVA_RIVA_IMAGE", "localhost/riva-micall-riva:alpha")
OUTPUT_NAMES = ("conseq.csv", "conseq_all.csv", "contigs.csv", "unstitched_contigs.csv",
                "stitched_contigs.csv", "genome_coverage.csv", "genome_concordance.csv",
                "remap_counts.csv", "coverage_summary.csv", "concordance.csv")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def image_id(ref):
    return subprocess.check_output(["podman", "image", "inspect",
                                    "--format", "{{.Id}}", ref], text=True).strip()


def score_outputs(folder, reference):
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.end_gap_score = -1
    scores = []
    result = {}
    for basename in OUTPUT_NAMES:
        matches = [path for path in (folder / basename, folder / "scratch" / basename)
                   if path.is_file()]
        if not matches:
            result[basename] = {"exists": False}
            continue
        file = matches[-1]
        with file.open(newline="") as f:
            rd = csv.DictReader(f)
            lines = list(rd)
        result[basename] = {"exists": True, "rows": len(lines), "sha256": sha(file)}
        if basename != "conseq.csv":
            continue
        for row in lines:
            if row.get("consensus-percent-cutoff") != "MAX":
                continue
            seq = row.get("sequence", "").upper()
            if not seq:
                continue
            scores.append(float(aligner.score(reference, seq)))
    return {"best_hxb2_final_max_conseq_score": max(scores, default=None),
            "num_final_max_conseqs": len(scores), "outputs": result}


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
        "--entrypoint", "micall", image,
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="append",
                        help="Run only a selected sample ID (repeatable)")
    parser.add_argument("--mode", choices=("both","iva","riva"), default="both")
    parser.add_argument("--timeout-per-arm", type=int, default=3600)
    parser.add_argument("--probe",action="store_true")
    args=parser.parse_args()
    images={"iva":IVA_IMAGE,"riva":RIVA_IMAGE}
    checked={}
    for arm,img in images.items():
        if args.mode not in ("both",arm): continue
        checked[arm]=image_id(img)
    rows=list(csv.DictReader((DATA/"manifest.tsv").open(),delimiter="\t"))
    rows=[row for row in rows if args.sample is None or row["sample"] in args.sample]
    if not rows: raise ValueError("No samples selected")
    hxb2=next(SeqIO.parse(DATA/"hxb2.fasta","fasta")).seq
    if args.probe:
        print(json.dumps({"images":checked,"sample_count":len(rows),
                          "hxb2_sha256":sha(DATA/"hxb2.fasta")},indent=2))
        return 0
    RESULTS.mkdir(parents=True,exist_ok=True)
    invocation=str(int(time.time()))+"-"+str(os.getpid())
    path=RESULTS/"results.jsonl"
    failed=0
    with path.open("a", buffering=1) as out:
        for row in rows:
            record={"sample":row["sample"],"invocation":invocation,
                    "hxb2_sha256":sha(DATA/"hxb2.fasta"),"status":"started"}
            out.write(json.dumps(record)+"\n")
            for arm in ("iva","riva"):
                if arm not in checked: continue
                print(f'{row["sample"]}: {arm}',flush=True)
                try:
                    record[arm]=run_arm(row,arm,images[arm],str(hxb2),
                                        args.timeout_per_arm, invocation)
                    if record[arm]["exit_code"]: failed+=1
                except Exception as exc:
                    record[arm]={"error":str(exc)}
                    failed+=1
            if all(arm in record and "metrics" in record[arm] for arm in ("iva","riva")):
                a=record["iva"]["metrics"]["best_hxb2_final_max_conseq_score"]
                b=record["riva"]["metrics"]["best_hxb2_final_max_conseq_score"]
                record["best_contig_acceptance"]={
                    "iva_score":a,"riva_score":b,
                    "pass": a is not None and b is not None and b >= 0.95*a}
                if not record["best_contig_acceptance"]["pass"]: failed+=1
            record["status"]="finished"
            out.write(json.dumps(record,sort_keys=True)+"\n")
    return 1 if failed else 0


if __name__=="__main__":
    raise SystemExit(main())
