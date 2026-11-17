"""Run six immutable non-Ivanka MiCall images before any Ivanka requalification.

Every arm is checkpointed separately. A crashed/restarted service never
replays a verified terminal arm; incomplete attempts are archived.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
import math
from pathlib import Path
import shutil

from .fork_micall_synthetic import checked_images
from .hxb2_cohort import attestation
from .micall_checkpoint import digest,identity,write_case
from .micall_lock import exclusive_lock
from .micall_synthetic import attempt
from .run_synthetic import cohort_rows

SCHEMA="ivanka.expanded.comparators_first_synthetic.v1"
TOOLS=("iva","haploflow","megahit","abyss","spades","velvet")
BASE="8458f9e5d34c39a6694b1fb6a40e055d7ce89553"


def atomic(path,record):
    temporary=path.with_suffix(path.suffix+".partial")
    temporary.write_text(json.dumps(record,sort_keys=True,indent=2)+"\n")
    temporary.replace(path)


def source_manifest(data,proof,images,attestation_file):
    root=Path(__file__).resolve()
    other=(root.with_name("micall_synthetic.py"),
           root.with_name("micall_dominant.py"),
           root.with_name("micall_checkpoint.py"),
           root.with_name("micall_lock.py"),
           root.with_name("run_synthetic.py"))
    return {"schema":SCHEMA,"status":"COMPARATORS_FIRST_UNQUALIFIED",
            "expected":400,"cohort_sha256":digest(Path(data)/"cohort.json"),
            "truth_proof":proof,"images":{x:images[x] for x in TOOLS},
            "original_seven_image_attestation":digest(attestation_file),
            "sources_sha256":{x.name:digest(x) for x in (root,*other)},
            "ivanka_deferred":True}


def verify_arm(path,tool,image):
    source=path/"execution.json"
    if not source.is_file():
        return None
    value=json.loads(source.read_text())
    if (value.get("sha256")!=image
            or value.get("status") not in ("success","failed")
            or value.get("score_origin")!="micall_final_max_reference_panel_v1"
            or value.get("timing_origin")!="micall_in_container_monotonic_v1"
            or value.get("argv",[]).count(image)!=1
            or value.get("argv",[])[-1]!="--all_projects"):
        raise ValueError("modified or ineligible six-arm MiCall evidence: "+tool)
    if value["status"]=="success":
        metrics=value.get("final_dominant",{})
        target=path/metrics.get("source_output","nonexistent")
        if (value.get("exit_code")!=0 or not target.is_file()
                or digest(target)!=metrics.get("conseq_csv_sha256")
                or not isinstance(value.get("seconds"),(int,float))
                or not math.isfinite(value["seconds"])
                or not 0<value["seconds"]<=1800
                or not isinstance(value.get("score"),(int,float))
                or not math.isfinite(value["score"])
                or value["score"]<0):
            raise ValueError("synthetic comparator completion evidence changed")
    return value


def prepare(folder,tools,images):
    results={}
    for name in tools:
        target=folder/name
        result=verify_arm(target,name,images[name])
        if result is None and target.exists():
            archive=folder/"_interrupted"
            archive.mkdir(exist_ok=True)
            for i in range(1,1000):
                destination=archive/(name+f"-{i:03d}")
                if not destination.exists():
                    target.rename(destination)
                    break
            else:
                raise ValueError("too many interrupted comparator attempts")
        if result is not None:
            results[name]=result
    return results


def run_case(row,root,images,proof):
    sample,source,manifest=row
    folder=root/sample
    folder.mkdir(exist_ok=True)
    fields=identity(sample,manifest,proof)
    old=folder/"matrix.json"
    if old.exists():
        record=json.loads(old.read_text())
        if ({key:record.get(key) for key in fields}!=fields
                or set(record.get("results",{}))!=set(TOOLS)):
            raise ValueError("modified completed six-tool case")
        if record["results"]!=prepare(folder,TOOLS,images):
            raise ValueError("completed six-tool evidence differs")
        return record
    results=prepare(folder,TOOLS,images)
    for tool in TOOLS:
        if tool in results:
            continue
        result=attempt((source,manifest),folder/tool,tool,images[tool],1800)
        results[tool]=verify_arm(folder/tool,tool,images[tool])
        if result!=results[tool]:
            raise ValueError("new comparator execution was modified")
        if result["status"]=="success":
            scratch=folder/tool/"scratch"
            source_file=result["final_dominant"]["source_output"]
            if (not source_file.startswith("scratch/") and
                    scratch.is_dir() and not scratch.is_symlink()):
                shutil.rmtree(scratch)
    record={**fields,"execution_order":list(TOOLS),"results":results,
            "ivanka_deferred":True}
    write_case(folder,record)
    return record


def rehydrate(root,cohort,images,proof):
    recovered={}
    for row in cohort:
        sample=row[0]
        if not (root/sample/"matrix.json").is_file():
            continue
        recovered[sample]=run_case(row,root,images,proof)
    journal=root/"results.jsonl"
    if journal.exists():
        history=journal.read_bytes().splitlines(keepends=True)
        historic=[json.loads(x) for x in history if x.endswith(b"\n")
                  and x.strip()]
        if len([x for x in history if x and not x.endswith(b"\n")])>1:
            raise ValueError("multiple torn comparator journal rows")
        if (len(historic)!=len({x["id"] for x in historic})
                or any(recovered.get(x["id"])!=x for x in historic)):
            raise ValueError("old comparator journal differs from immutable cases")
    temporary=root/"results.recovered.partial"
    with temporary.open("x") as stream:
        for _,record in sorted(recovered.items()):
            stream.write(json.dumps(record,sort_keys=True)+"\n")
    temporary.replace(journal)
    return recovered


def run(data,out,images,fork,base,attestation_file,jobs=10):
    if jobs<1 or jobs>10 or base!=BASE:
        raise ValueError("unexpected concurrency or MiCall base")
    out=Path(out).resolve()
    with exclusive_lock(out):
        checked_images(images,attestation_file,fork,base)
        proof=attestation(data,expected=400)
        cohort=list(cohort_rows(data))
        if len(cohort)!=400:
            raise ValueError("synthetic cohort is not the original 400")
        manifest=source_manifest(data,proof,images,attestation_file)
        frozen=out/"run_manifest.json"
        if frozen.exists():
            if json.loads(frozen.read_text())!=manifest:
                raise ValueError("source or six comparator image identity changed")
        else:
            out.mkdir(parents=True,exist_ok=True)
            atomic(frozen,manifest)
        recovered=rehydrate(out,cohort,images,proof)
        journal=out/"results.jsonl"
        with journal.open("a",buffering=1) as log:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                futures=[pool.submit(run_case,row,out,images,proof)
                         for row in cohort if row[0] not in recovered]
                for future in as_completed(futures):
                    record=future.result()
                    log.write(json.dumps(record,sort_keys=True)+"\n")
                    print("COMPARATOR_SYNTHETIC",record["id"],
                          len(record["results"]),"/6",flush=True)
        final=rehydrate(out,cohort,images,proof)
        if len(final)!=400:
            raise ValueError("incomplete comparator synthetic cohort")
        summary={"schema":SCHEMA,"ivanka_deferred":True,
                 "sample_count":len(final),"arms":6*len(final),
                 "results_sha256":digest(journal),
                 "run_manifest_sha256":digest(frozen)}
        atomic(out/"attempt_summary.json",summary)
        return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ("data","out","images","fork","base","attestation"):
        parser.add_argument("--"+flag,required=True)
    parser.add_argument("--jobs",type=int,default=10)
    args=parser.parse_args()
    images=json.loads(Path(args.images).read_text())
    result=run(args.data,args.out,images,args.fork,args.base,
               args.attestation,args.jobs)
    print("SIX_COMPARATORS_SYNTHETIC_DONE",result,flush=True)


if __name__=="__main__":
    main()
