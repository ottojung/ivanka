"""Six immutable physical MiCall assembler arms, with Ivanka deliberately deferred.

Output and timestamps are per arm. No reference ever selects assembler contigs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv
import hashlib
import json
from pathlib import Path
import secrets

from .comparators_first_synthetic import TOOLS,BASE,atomic
from .fork_micall_synthetic import checked_images
from .micall_lock import exclusive_lock
from .physical_inputs import attest,hash_pair,sample_paths
from .real_matrix import MANIFEST,PANEL
from .real_resume import authentic_arm,digest

SCHEMA="ivanka.expanded.comparators_first_real.v1"


def rows(data):
    root=Path(data).resolve()
    with (root/"manifest.tsv").open(newline="") as stream:
        records=list(csv.DictReader(stream,delimiter="\t"))
    if len(records)!=198 or len({row["sample"] for row in records})!=198:
        raise ValueError("real cohort missing source-attested physical cases")
    for row in records:
        pair=sample_paths(root,row["sample"])
        hashes=[hash_pair(path)[1] for path in pair]
        row["input_sha256"]=hashlib.sha256(
            "".join(hashes).encode()).hexdigest()
    return records


def sources():
    here=Path(__file__).resolve()
    related=(here,here.with_name("comparators_first_synthetic.py"),
             here.with_name("physical_inputs.py"),
             here.with_name("real_resume.py"),
             here.with_name("micall_lock.py"),
             here.parents[1]/"podman_full_micall.py",
             here.parents[1]/"reference_panel.py",
             here.parents[1]/"project_references.py",
             here.parents[1]/"inside_container_timing.py")
    return {x.name:digest(x) for x in related}


def manifest(data,images,attestation_file,panel_hash):
    if panel_hash!=PANEL or digest(Path(data)/"manifest.tsv")!=MANIFEST:
        raise ValueError("original physical panel/manifest changed")
    return {"schema":SCHEMA,"status":"COMPARATORS_FIRST_UNQUALIFIED",
            "expected_samples":198,"source_manifest_sha256":MANIFEST,
            "reference_panel_sha256":panel_hash,
            "images":{name:images[name] for name in TOOLS},
            "original_seven_attestation_sha256":digest(attestation_file),
            "source_files_sha256":sources(),"ivanka_deferred":True}


def row_path(folder,sample):
    key=hashlib.sha256(sample.encode()).hexdigest()
    return folder/"checkpoints"/(key+".json")


def verify(record,row,tool,image,panel,pmm):
    if (record.get("sample")!=row["sample"]
            or record.get("input_sha256")!=row["input_sha256"]
            or record.get("tool")!=tool or record.get("image_id")!=image
            or record.get("reference_panel_sha256")!=PANEL
            or record.get("status")!="finished"
            or type(record.get("failed")) is not bool):
        raise ValueError("physical comparator result identity changed")
    arm=record.get("arm")
    if not isinstance(arm,dict) or arm.get("image_id")!=image:
        raise ValueError("physical comparator arm wrong image")
    if not record["failed"]:
        authentic_arm(arm,image,Path(pmm.RESULTS))
        if arm.get("exit_code")!=0 or not isinstance(record.get("measurement"),dict):
            raise ValueError("physical comparator completion changed")
        measurement=record["measurement"]
        if (measurement.get("seconds")!=arm.get("seconds")
                or measurement.get("score")!=float(
                    pmm.best_panel_alignment(
                        pmm.final_max_sequences(arm["artifact_dir"]),panel)["score"])):
            raise ValueError("physical comparator panel scoring changed")
    elif record.get("measurement") is not None:
        raise ValueError("failed physical arm cannot invent measurements")
    return record


def execute(row,tool,images,reference,panel,pmm,out):
    sample=row["sample"]
    target=row_path(out/tool,sample)
    target.parent.mkdir(exist_ok=True,parents=True)
    invocation=(tool+"-"+hashlib.sha256(sample.encode()).hexdigest()[:12]+
                "-"+secrets.token_hex(5))
    arm_name="iva" if tool=="iva" else "ivanka"
    try:
        arm=pmm.run_arm(row,arm_name,images[tool],
                        reference if row.get("project")=="NFLHIVDNA" else None,
                        1800,invocation,True)
        if arm.get("exit_code")!=0:
            raise ValueError("MiCall arm nonzero exit: "+str(arm.get("exit_code")))
        best=pmm.best_panel_alignment(
            pmm.final_max_sequences(arm["artifact_dir"]),panel)
        if arm.get("seconds") is None:
            raise ValueError("MiCall successful arm missing monotonic timer")
        value={"score":float(best["score"]),"seconds":arm["seconds"]}
        failed=False
        reason=None
    except Exception as exc:
        if "arm" not in locals():
            arm={"image_id":images[tool],"exit_code":1,
                 "error":f"{type(exc).__name__}: {exc}"}
        value=None
        failed=True
        reason=f"{type(exc).__name__}: {exc}"
    record={"sample":sample,"tool":tool,"image_id":images[tool],
            "input_sha256":row["input_sha256"],
            "reference_panel_sha256":PANEL,
            "status":"finished","failed":failed,"arm":arm,
            "measurement":value,"error":reason}
    atomic(target,record)
    print("COMPARATOR_REAL",tool,hashlib.sha256(sample.encode()).hexdigest()[:8],
          "success" if not failed else "failed",flush=True)
    return record


def replay(folder,items,tool,image,panel,pmm):
    recovered={}
    for row in items:
        path=row_path(folder,row["sample"])
        if path.is_file():
            record=json.loads(path.read_text())
            recovered[row["sample"]]=verify(record,row,tool,image,panel,pmm)
    journal=folder/"results.jsonl"
    if journal.is_file():
        old=[]
        for line in journal.read_bytes().splitlines(keepends=True):
            if not line.endswith(b"\n"):
                break
            if line.strip():
                old.append(json.loads(line))
        if len({r["sample"] for r in old})!=len(old):
            raise ValueError("duplicate physical per-tool journal")
        if any(recovered.get(record["sample"])!=record for record in old):
            raise ValueError("physical journal differs from verified checkpoints")
    journal.parent.mkdir(exist_ok=True,parents=True)
    temporary=journal.with_suffix(".recovered.partial")
    with temporary.open("x") as stream:
        for _,record in sorted(recovered.items()):
            stream.write(json.dumps(record,sort_keys=True)+"\n")
    temporary.replace(journal)
    return recovered


def run(data,out,images,fork,base,attestation_file,jobs=10):
    if jobs<1 or jobs>10 or base!=BASE:
        raise ValueError("real comparator concurrency/base invalid")
    out=Path(out).resolve()
    with exclusive_lock(out):
        checked_images(images,attestation_file,fork,base)
        attest(data)
        items=rows(data)
        import podman_full_micall as pmm
        from project_references import final_max_sequences
        from reference_panel import best_panel_alignment,build_reference_panel,panel_sha256
        from Bio import SeqIO
        pmm.DATA=Path(data).resolve()
        pmm.RESULTS=out/"artifacts"
        pmm.final_max_sequences=final_max_sequences
        pmm.best_panel_alignment=best_panel_alignment
        hxb2=next(SeqIO.parse(str(Path(data)/"hxb2.fasta"),"fasta")).seq
        projects,_=pmm.load_micall_projects(images["iva"])
        panel=build_reference_panel(projects,hxb2)
        frozen=manifest(data,images,attestation_file,panel_sha256(panel))
        path=out/"run_manifest.json"
        if path.is_file():
            if json.loads(path.read_text())!=frozen:
                raise ValueError("real comparator frozen runner/images changed")
        else:
            out.mkdir(parents=True,exist_ok=True)
            atomic(path,frozen)
        pmm.RESULTS.mkdir(exist_ok=True)
        for tool in TOOLS:
            folder=out/tool
            (folder/"checkpoints").mkdir(exist_ok=True,parents=True)
            prior=replay(folder,items,tool,images[tool],panel,pmm)
            missing=[item for item in items if item["sample"] not in prior]
            with (folder/"results.jsonl").open("a",buffering=1) as stream:
                with ThreadPoolExecutor(max_workers=jobs) as pool:
                    futures=[pool.submit(execute,item,tool,images,hxb2,
                                         panel,pmm,out) for item in missing]
                    for future in as_completed(futures):
                        record=future.result()
                        stream.write(json.dumps(record,sort_keys=True)+"\n")
            completed=replay(folder,items,tool,images[tool],panel,pmm)
            if len(completed)!=198:
                raise ValueError("physical comparator stage incomplete: "+tool)
            print("COMPARATOR_REAL_TOOL_COMPLETE",tool,len(completed),flush=True)
        summary={"schema":SCHEMA,"samples":198,"tools":list(TOOLS),
                 "ivanka_deferred":True,
                 "manifest_sha256":digest(path)}
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
    print("SIX_COMPARATORS_PHYSICAL_DONE",result,flush=True)


if __name__=="__main__":
    main()
