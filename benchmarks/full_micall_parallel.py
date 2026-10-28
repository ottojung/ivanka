#!/usr/bin/env python3
"""Parallel, independently isolated MiCall samples under ONE global timeout.

The parent is only orchestration. Every worker executes the *real* MiCall
pipeline with the same pinned checkout, paths, and per-sample reporting.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from full_micall import ROOT, RESULTS, manifest

children: set[subprocess.Popen] = set()

def stop(signum, frame):
    for child in list(children):
        if child.poll() is None:
            child.terminate()
    raise KeyboardInterrupt(f"signal {signum}")

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=("iva","riva","both"), default="riva")
    p.add_argument("--iva-mode", choices=("cached","run"), default="cached")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--riva", default=str(ROOT / "target/release/riva"))
    p.add_argument("--sample", action="append")
    args=p.parse_args()
    if not 1 <= args.jobs <= 16:
        raise SystemExit("--jobs must be between 1 and 16")
    rows=[x for x in manifest() if not args.sample or x["sample"] in args.sample]
    if not rows:
        raise SystemExit("No matching samples")
    run_id=f"{int(time.time())}-{os.getpid()}"
    run_dir=RESULTS / "invocations" / run_id
    run_dir.mkdir(parents=True,exist_ok=True)
    t0=time.monotonic()

    def run_sample(sample):
        command=[sys.executable, str(ROOT / "benchmarks/full_micall.py"),
                 "--mode", args.mode, "--iva-mode", args.iva_mode,
                 "--riva", args.riva, "--sample", sample]
        out=run_dir / f"{sample}.log"
        with out.open("w") as output:
            child=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT)
            children.add(child)
            try:
                status=child.wait()
            finally:
                children.discard(child)
        return {"sample":sample,"exit_code":status,"log":str(out)}

    report={"run_id":run_id,"mode":args.mode,"iva_mode":args.iva_mode,
            "jobs":args.jobs,"samples":[r["sample"] for r in rows],
            "started_at":time.time(),"results":[]}
    results=run_dir / "summary.json"
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures={pool.submit(run_sample,row["sample"]):row["sample"] for row in rows}
            for future in as_completed(futures):
                row=future.result()
                report["results"].append(row)
                report["elapsed_seconds"]=round(time.monotonic()-t0,2)
                results.write_text(json.dumps(report,indent=2)+"\n")
                print(f"{row['sample']}: {'PASS' if row['exit_code']==0 else 'FAIL'} after {report['elapsed_seconds']}s",flush=True)
    except BaseException:
        for child in list(children):
            if child.poll() is None:
                child.terminate()
        raise
    report["completed_at"]=time.time()
    report["elapsed_seconds"]=round(time.monotonic()-t0,2)
    report["all_ok"]=len(report["results"])==len(rows) and all(
        r["exit_code"]==0 for r in report["results"])
    results.write_text(json.dumps(report,indent=2)+"\n")
    print(f"Full MiCall run: {len(rows)-sum(r['exit_code']!=0 for r in report['results'])}/{len(rows)} successful, wall={report['elapsed_seconds']}s",flush=True)
    return 0 if report["all_ok"] else 1

if __name__=="__main__":
    raise SystemExit(main())
