"""Read-only recovery of complete, authentic physical MiCall sample attempts.

A source attempt remains immutable; resumed attempts use new directories.
"""
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "ivanka.expanded.real_sample_recovery.v1"

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024*1024), b""):
            h.update(data)
    return h.hexdigest()

def row_hash(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()

def authentic_arm(value, expected_image, attempt):
    if (not isinstance(value, dict) or value.get("image_id") != expected_image
            or value.get("exit_code") != 0
            or value.get("timing_origin") != "micall_in_container_monotonic_v1"
            or not isinstance(value.get("seconds"), (int,float))
            or not math.isfinite(value["seconds"]) or value["seconds"] <= 0
            or value["seconds"] > 1800
            or not isinstance(value.get("container_wall_seconds"),(int,float))
            or value["container_wall_seconds"] <= 0
            or value["container_wall_seconds"] > 1800):
        raise ValueError("incompatible original MiCall image/exit/timing")
    folder=Path(value.get("artifact_dir", "")).resolve()
    if not folder.is_relative_to(Path(attempt).resolve()) or not folder.is_dir():
        raise ValueError("MiCall artifacts outside original attempt directory")
    outputs=value.get("metrics",{}).get("outputs",{})
    if not isinstance(outputs,dict) or len(outputs) < 10:
        raise ValueError("missing MiCall output inventory")
    for filename,proof in outputs.items():
        if "/" in filename or filename.startswith(".") or not isinstance(proof,dict):
            raise ValueError("malformed MiCall output inventory")
        files=(folder/filename,folder/"scratch"/filename)
        found=next((file for file in files if file.is_file()),None)
        if proof.get("exists") is True:
            if found is None or digest(found)!=proof.get("sha256"):
                raise ValueError("retained MiCall output differs from original hash")
        elif proof!={"exists":False} or found is not None:
            raise ValueError("changed presence of original MiCall output")
    log=folder/"podman.stderr.log"
    with log.open("rb") as stream:
        stream.seek(0,2)
        stream.seek(max(0,stream.tell()-4096))
        if b"micall.process_run(): Done." not in stream.read():
            raise ValueError("missing original MiCall completion witness")
    from benchmarks.container_completion import verified_internal_seconds
    actual=verified_internal_seconds(
        folder/"micall_internal_timing.json",value["container_wall_seconds"])
    if abs(actual-value["seconds"])>1e-9:
        raise ValueError("modified in-container timing evidence")

def authenticate(row, sample, images, name, attempt, shared_controls=None):
    if row.get("sample")!=sample or not isinstance(row.get("invocation"),str):
        raise ValueError("sample identity or invocation changed")
    source=row.get("provenance",{})
    if (not isinstance(source,dict)
            or source.get("iva_image_id")!=images["iva"]
            or source.get("all_projects") is not True
            or len(source.get("fastq_sha256",[]))!=2
            or not all(isinstance(x,str) and len(x)==64 for x in
                       source["fastq_sha256"])):
        raise ValueError("not an original paired-read MiCall provenance")
    if shared_controls is not None:
        if (row.get("iva_baseline_reused") is not True or
                row.get("iva")!=shared_controls.get(sample)):
            raise ValueError("sample reused a different or unauthenticated IVA control")
    elif row.get("iva_baseline_reused") is True:
        raise ValueError("IVA control reuse requires original source proof")
    if row.get("status")=="finished" and "best_contig_acceptance" in row:
        if shared_controls is None:
            authentic_arm(row.get("iva"),images["iva"],attempt)
        authentic_arm(row.get("ivanka"),images[name],attempt)
        score=row["best_contig_acceptance"]
        if (score.get("reference_count")!=33
                or score.get("reference_panel_sha256")
                !="018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"):
            raise ValueError("unexpected scoring panel")
        return
    # Failed/error cases are preserved, not silently transformed into wins.
    if row.get("failed") is not True:
        raise ValueError("unverifiable unscored success")
    for arm in ("iva","ivanka"):
        present=row.get(arm)
        if isinstance(present,dict) and present.get("image_id") not in (
                None,images["iva" if arm=="iva" else name]):
            raise ValueError("failed case used a different image")

def read_attempt(path, expected_samples, images, name, shared_controls=None):
    source=Path(path)/"results.jsonl"
    if not source.is_file():
        return {},None
    before=digest(source)
    records={}
    lines=source.read_bytes().splitlines(keepends=True)
    for number,raw in enumerate(lines,1):
        try:
            record=json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            if number==len(lines) and not raw.endswith(b"\n"):
                break
            raise ValueError("invalid nonterminal MiCall JSONL line") from exc
        if not isinstance(record,dict) or record.get("sample") not in expected_samples:
            raise ValueError("unknown sample in original MiCall attempt")
        sample=record["sample"]
        if record.get("status")=="started":
            continue
        if sample in records:
            raise ValueError("duplicate original terminal sample")
        authenticate(record,sample,images,name,path,shared_controls)
        records[sample]=record
    if digest(source)!=before:
        raise ValueError("MiCall attempt changed during verification")
    return records,before

def collect(tool_dir, expected_samples, images, name, shared_controls=None):
    records={}
    witnesses={}
    for folder in sorted(Path(tool_dir).glob("attempt-*")):
        if not folder.is_dir():
            continue
        found,checksum=read_attempt(folder,expected_samples,images,name,
                                    shared_controls)
        witnesses[folder.name]={"sha256":checksum,
                                 "samples":sorted(found)}
        for sample,record in found.items():
            if sample in records:
                raise ValueError("competing terminal results: "+sample)
            records[sample]=record
    return records,witnesses

def commit(tool_dir,records,witnesses,source_manifest):
    root=Path(tool_dir)
    journal=root/"results.jsonl"
    raw="".join(json.dumps(record,sort_keys=True)+"\n"
                for _,record in sorted(records.items()))
    temporary=root/"results.jsonl.partial"
    temporary.write_text(raw)
    temporary.replace(journal)
    proof={"schema":SCHEMA,"run_manifest_sha256":digest(source_manifest),
           "results_sha256":digest(journal),
           "records":{name:row_hash(record) for name,record in records.items()},
           "attempts":witnesses}
    temporary=root/"checkpoints.json.partial"
    temporary.write_text(json.dumps(proof,indent=2,sort_keys=True)+"\n")
    temporary.replace(root/"checkpoints.json")
    return proof

def verify_collection(tool_dir, expected_samples, images, name, source_manifest,
                      allow_additional=False, shared_controls=None):
    """Reject edited checkpoints; optionally discover completed new-attempt rows.

    A process can die after MiCall writes a terminal row but before the outer
    supervisor updates its checkpoint. Such honest new rows remain recoverable.
    """
    root=Path(tool_dir)
    proof=json.loads((root/"checkpoints.json").read_text())
    records,witnesses=collect(root,expected_samples,images,name,shared_controls)
    old_attempts=proof.get("attempts",{})
    old_rows=proof.get("records",{})
    if (proof.get("schema")!=SCHEMA
            or proof.get("run_manifest_sha256")!=digest(source_manifest)
            or (not allow_additional and old_attempts!=witnesses)
            or (not allow_additional and old_rows!={key:row_hash(value)
                                                   for key,value in records.items()})
            or any(witnesses.get(key)!=value for key,value in old_attempts.items())
            or any(key not in records or row_hash(records[key])!=value
                   for key,value in old_rows.items())):
        raise ValueError("real benchmark checkpoint evidence changed")
    actual=[json.loads(line) for line in (root/"results.jsonl").read_text().splitlines()]
    original=[record for key,record in sorted(records.items()) if key in old_rows]
    completed=[record for _,record in sorted(records.items())]
    if digest(root/"results.jsonl")==proof.get("results_sha256"):
        if actual!=original:
            raise ValueError("published real tool rows differ from original records")
    elif not allow_additional or actual!=completed:
        raise ValueError("real result journal changed without authentic new rows")
    return records
