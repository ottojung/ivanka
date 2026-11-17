"""Anonymized live counter publication for frozen six-assembler MiCall work."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

from .comparators_first_synthetic import SCHEMA as SYN_SCHEMA,TOOLS,verify_arm

SCHEMA="ivanka.assembler-bench.comparators-first-progress.v1"
SYN_EXPECTED=400
REAL_EXPECTED=198


def empty(expected):
    return {"expected":expected,"completed":0,"successful":0,
            "failed":0,"mean_alignment":None,"mean_seconds":None}


def count(records,expected):
    scores=[x["score"] for x in records if x["status"]=="success"]
    seconds=[x["seconds"] for x in records if x["status"]=="success"]
    return {"expected":expected,"completed":len(records),
            "successful":len(scores),"failed":len(records)-len(scores),
            "mean_alignment":round(sum(scores)/len(scores),3) if scores else None,
            "mean_seconds":round(sum(seconds)/len(seconds),3) if seconds else None}


def synthetic(root):
    root=Path(root)
    result={name:empty(SYN_EXPECTED) for name in TOOLS}
    manifest=root/"run_manifest.json"
    if not manifest.exists():
        return result
    info=json.loads(manifest.read_text())
    if (info.get("schema")!=SYN_SCHEMA or info.get("expected")!=400
            or set(info.get("images",{}))!=set(TOOLS)
            or info.get("ivanka_deferred") is not True):
        raise ValueError("comparator synthetic source phase not pinned")
    cases=[x for x in root.iterdir() if x.is_dir()
           and not x.name.startswith("_")]
    if len(cases)>400:
        raise ValueError("more synthetic cases than frozen cohort")
    for name in TOOLS:
        records=[]
        for case in cases:
            result=verify_arm(case/name,name,info["images"][name])
            if result is not None:
                records.append(result)
        result[name]=count(records,SYN_EXPECTED)
    return result


def real(root):
    """Counter path: one baseline and five independently verified candidates."""
    root=Path(root)
    result={name:empty(REAL_EXPECTED) for name in TOOLS}
    manifest=root/"run_manifest.json"
    if not manifest.exists():
        return result
    info=json.loads(manifest.read_text())
    if info.get("schema")!="ivanka.expanded.comparators_first_real.v1":
        raise ValueError("comparator real phase manifest does not match")
    for name in TOOLS:
        source=root/name/"results.jsonl"
        if not source.exists():
            continue
        records={}
        for raw in source.read_bytes().splitlines(keepends=True):
            if not raw.endswith(b"\n"):
                break
            record=json.loads(raw)
            if record.get("status")=="started":
                continue
            sample=record.get("sample")
            if sample in records:
                raise ValueError("duplicate real completion in published journal")
            records[sample]=record
        complete=list(records.values())
        measured=[]
        for row in complete:
            if row.get("status") not in ("finished","error","sample_timeout"):
                raise ValueError("unknown physical completion state")
            if row.get("status")=="finished" and row.get("failed") is False:
                measure=row.get("measurement")
                if measure is None:
                    raise ValueError("missing physical comparator measurement")
                measured.append(measure)
        result[name]=count(
            [dict(status="success",**r) for r in measured]+
            [dict(status="failed") for _ in range(len(complete)-len(measured))],
            REAL_EXPECTED)
    return result


def generate(synth,physical):
    syn=synthetic(synth)
    rea=real(physical)
    return {"schema":SCHEMA,"status":"comparator_phase_unqualified",
            "ivanka":"deliberately_deferred",
            "tools":{name:{"synthetic":syn[name],"real":rea[name]}
                     for name in TOOLS}}


def publish(synthetic_root,real_root,destination):
    new=generate(synthetic_root,real_root)
    path=Path(destination)
    if path.exists():
        prior=json.loads(path.read_text())
        original={k:v for k,v in prior.items() if k!="updated_utc"}
        if original==new:
            print("COMPARATOR_PUBLICATION_UNCHANGED",flush=True)
            return False
        for name in TOOLS:
            for cohort in ("real","synthetic"):
                if (new["tools"][name][cohort]["completed"]<
                        prior["tools"][name][cohort]["completed"]):
                    raise ValueError("comparator publication regressed")
    new["updated_utc"]=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    temporary=path.with_suffix(".json.partial")
    temporary.write_text(json.dumps(new,sort_keys=True,indent=2)+"\n")
    temporary.replace(path)
    print("COMPARATOR_PUBLICATION_UPDATED",
          [(name,new["tools"][name]["synthetic"]["completed"],
            new["tools"][name]["real"]["completed"]) for name in TOOLS],
          flush=True)
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic",required=True)
    parser.add_argument("--real",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    publish(args.synthetic,args.real,args.output)


if __name__=="__main__":
    main()
