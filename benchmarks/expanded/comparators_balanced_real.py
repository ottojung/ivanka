"""Balanced physical MiCall schedule over the original, still-frozen six-arm run.

Scientific inputs, MiCall invocation, scoring, original checkpoints, and their
source attestations are unchanged. Only work ordering is different.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path

from .balanced_dispatch import BalancedQueue, drive, clear_stale_recovery
from .comparators_first_real import (
    BASE, SCHEMA, TOOLS, atomic, execute, manifest,
    replay, rows, verify,
)
from .comparators_first_synthetic import atomic as write_atomic
from .fork_micall_synthetic import checked_images
from .micall_lock import exclusive_lock
from .physical_inputs import attest
from .real_resume import digest


def receipt(out):
    home=Path(__file__).resolve()
    path=out/"scheduler_receipt.json"
    value={"schema":"ivanka.expanded.balanced-dispatch.v1",
           "frozen_run_manifest_sha256":digest(out/"run_manifest.json"),
           "dispatch_sha256":digest(home.with_name("balanced_dispatch.py")),
           "physical_scheduler_sha256":digest(home),
           "cohort":"real","max_concurrency":10,
           "selection":"least-completed-plus-inflight"}
    if path.exists():
        if json.loads(path.read_text())!=value:
            raise ValueError("frozen balanced physical scheduling source changed")
    else:
        write_atomic(path,value)


def run(data,out,images,fork,base,attestation_file,jobs=10):
    if not 1<=jobs<=10 or base!=BASE:
        raise ValueError("physical MiCall comparator concurrency/base invalid")
    out=Path(out).resolve()
    with exclusive_lock(out):
        checked_images(images,attestation_file,fork,base)
        attest(data)
        cases=rows(data)
        by_name={row["sample"]:row for row in cases}
        import podman_full_micall as pmm
        from Bio import SeqIO
        from project_references import final_max_sequences
        from reference_panel import (
            best_panel_alignment,build_reference_panel,panel_sha256,
        )
        pmm.DATA=Path(data).resolve()
        pmm.RESULTS=out/"artifacts"
        pmm.final_max_sequences=final_max_sequences
        pmm.best_panel_alignment=best_panel_alignment
        hxb2=next(SeqIO.parse(str(Path(data)/"hxb2.fasta"),"fasta")).seq
        projects,_=pmm.load_micall_projects(images["iva"])
        panel=build_reference_panel(projects,hxb2)
        expected=manifest(data,images,attestation_file,panel_sha256(panel))
        frozen=out/"run_manifest.json"
        if not frozen.exists() or json.loads(frozen.read_text())!=expected:
            raise ValueError("original frozen physical run manifest changed")
        receipt(out)
        pmm.RESULTS.mkdir(exist_ok=True)
        completed={}
        for tool in TOOLS:
            folder=out/tool
            (folder/"checkpoints").mkdir(parents=True,exist_ok=True)
            clear_stale_recovery(folder/"results.recovered.partial")
            completed[tool]=replay(folder,cases,tool,images[tool],panel,pmm)
        queue=BalancedQueue(TOOLS,cases,
                            {name:records.keys() for name,records
                             in completed.items()},
                            lambda row:row["sample"])
        print("BALANCED_REAL_RECOVERED",queue.report(),flush=True)
        with ExitStack() as stack:
            journals={tool:stack.enter_context(
                (out/tool/"results.jsonl").open("a",buffering=1))
                for tool in TOOLS}

            def perform(tool,row):
                return execute(row,tool,images,hxb2,panel,pmm,out)

            def save(tool,key,record):
                verify(record,by_name[key],tool,images[tool],panel,pmm)
                journals[tool].write(json.dumps(record,sort_keys=True)+"\n")
                print("BALANCED_REAL_RESULT",tool,queue.report()[tool],
                      flush=True)

            counts=drive(queue,jobs,perform,save)
        for tool in TOOLS:
            verified=replay(out/tool,cases,tool,images[tool],panel,pmm)
            if len(verified)!=198:
                raise ValueError("physical comparator stage incomplete: "+tool)
            print("COMPARATOR_REAL_TOOL_COMPLETE",tool,len(verified),flush=True)
        summary={"schema":SCHEMA,"samples":198,"tools":list(TOOLS),
                 "ivanka_deferred":True,
                 "manifest_sha256":digest(frozen)}
        atomic(out/"attempt_summary.json",summary)
        print("BALANCED_REAL_FINISHED",counts,flush=True)
        return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for option in ("data","out","images","fork","base","attestation"):
        parser.add_argument("--"+option,required=True)
    parser.add_argument("--jobs",type=int,default=10)
    args=parser.parse_args()
    images=json.loads(Path(args.images).read_text())
    result=run(args.data,args.out,images,args.fork,
               args.base,args.attestation,args.jobs)
    print("SIX_COMPARATORS_PHYSICAL_DONE",result,flush=True)


if __name__=="__main__":
    main()
