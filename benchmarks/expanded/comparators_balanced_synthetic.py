"""Balance synthetic MiCall arms without replacing the original frozen runner.

Original hidden-truth inputs, MiCall commands, final scoring, and per-arm
execution.json files remain unchanged and independently verifiable.
"""
import argparse
import json
from pathlib import Path
import shutil

from .balanced_dispatch import BalancedQueue,drive,clear_stale_recovery
from .comparators_first_synthetic import (
    BASE,SCHEMA,TOOLS,atomic,prepare,rehydrate,source_manifest,verify_arm,
)
from .fork_micall_synthetic import checked_images
from .hxb2_cohort import attestation
from .micall_checkpoint import digest,identity,write_case
from .micall_lock import exclusive_lock
from .micall_synthetic import attempt
from .run_synthetic import cohort_rows


def receipt(out):
    here=Path(__file__).resolve()
    path=out/"scheduler_receipt.json"
    value={"schema":"ivanka.expanded.balanced-dispatch.v1",
           "frozen_run_manifest_sha256":digest(out/"run_manifest.json"),
           "dispatch_sha256":digest(here.with_name("balanced_dispatch.py")),
           "synthetic_scheduler_sha256":digest(here),
           "cohort":"synthetic","max_concurrency":10,
           "selection":"least-completed-plus-inflight"}
    if path.is_file():
        if json.loads(path.read_text())!=value:
            raise ValueError("frozen synthetic balanced scheduling source changed")
    else:
        atomic(path,value)


def final_record(row,proof,results):
    sample,_,manifest=row
    return {**identity(sample,manifest,proof),
            "execution_order":list(TOOLS),"results":dict(results),
            "ivanka_deferred":True}


def run(data,out,images,fork,base,attestation_file,jobs=10):
    if not 1<=jobs<=10 or base!=BASE:
        raise ValueError("synthetic MiCall comparator concurrency/base invalid")
    out=Path(out).resolve()
    with exclusive_lock(out):
        checked_images(images,attestation_file,fork,base)
        proof=attestation(data,expected=400)
        cohort=list(cohort_rows(data))
        if len(cohort)!=400:
            raise ValueError("synthetic cohort is not original 400")
        expected=source_manifest(data,proof,images,attestation_file)
        frozen=out/"run_manifest.json"
        if not frozen.exists() or json.loads(frozen.read_text())!=expected:
            raise ValueError("original frozen synthetic source/images changed")
        receipt(out)
        clear_stale_recovery(out/"results.recovered.partial")
        recovered=rehydrate(out,cohort,images,proof)
        results={}
        for row in cohort:
            sample=row[0]
            if sample in recovered:
                results[sample]=dict(recovered[sample]["results"])
                continue
            folder=out/sample
            found=prepare(folder,TOOLS,images)
            results[sample]=found
            if len(found)==len(TOOLS):
                folder.mkdir(exist_ok=True)
                write_case(folder,final_record(row,proof,found))
        # Incorporate complete arm sets recovered after an interrupted journal.
        recovered=rehydrate(out,cohort,images,proof)
        queue=BalancedQueue(
            TOOLS,cohort,
            {tool:{sample for sample,records in results.items()
                   if tool in records} for tool in TOOLS},
            lambda row:row[0])
        print("BALANCED_SYNTHETIC_RECOVERED",queue.report(),flush=True)
        with (out/"results.jsonl").open("a",buffering=1) as journal:
            def perform(tool,row):
                sample,source,manifest=row
                folder=out/sample
                folder.mkdir(exist_ok=True)
                record=attempt((source,manifest),folder/tool,
                               tool,images[tool],1800)
                verified=verify_arm(folder/tool,tool,images[tool])
                if record!=verified:
                    raise ValueError("new synthetic arm differs from its checkpoint")
                if record["status"]=="success":
                    scratch=folder/tool/"scratch"
                    filename=record["final_dominant"]["source_output"]
                    if (not filename.startswith("scratch/") and
                            scratch.is_dir() and not scratch.is_symlink()):
                        shutil.rmtree(scratch)
                return verified

            def save(tool,key,record):
                results[key][tool]=record
                if len(results[key])==len(TOOLS):
                    row=next(r for r in cohort if r[0]==key)
                    full=final_record(row,proof,results[key])
                    write_case(out/key,full)
                    journal.write(json.dumps(full,sort_keys=True)+"\n")
                    print("COMPARATOR_SYNTHETIC",key,"6 /6",flush=True)
                print("BALANCED_SYNTHETIC_RESULT",tool,queue.report()[tool],
                      flush=True)

            counts=drive(queue,jobs,perform,save)
        complete=rehydrate(out,cohort,images,proof)
        if len(complete)!=400:
            raise ValueError("synthetic six-assembler cohort still incomplete")
        summary={"schema":SCHEMA,"ivanka_deferred":True,
                 "sample_count":400,"arms":2400,
                 "results_sha256":digest(out/"results.jsonl"),
                 "run_manifest_sha256":digest(frozen)}
        atomic(out/"attempt_summary.json",summary)
        print("BALANCED_SYNTHETIC_FINISHED",counts,flush=True)
        return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("data","out","images","fork","base","attestation"):
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--jobs",type=int,default=10)
    args=parser.parse_args()
    images=json.loads(Path(args.images).read_text())
    result=run(args.data,args.out,images,fork=args.fork,
               base=args.base,attestation_file=args.attestation,
               jobs=args.jobs)
    print("SIX_COMPARATORS_SYNTHETIC_DONE",result,flush=True)


if __name__=="__main__":
    main()
