"""Externally verify a precisely scoped six-comparator physical smoke."""
import hashlib
import json
from pathlib import Path

from .adapters import ASSEMBLERS
from .real_resume import verify_collection

SCHEMA="ivanka.expanded.fork_micall_real.v2"

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_physical_smoke(directory,images):
    root=Path(directory)
    if (root/"INVALID_SCOPE.json").exists():
        raise ValueError("real smoke is explicitly invalidated")
    manifest=root/"run_manifest.json"
    source=json.loads(manifest.read_text())
    expected=set(ASSEMBLERS)-{"iva"}
    sample=source.get("selected_sample")
    if (source.get("schema")!=SCHEMA or source.get("images")!=images
            or set(source.get("selected_tools",[]))!=expected
            or not isinstance(sample,str) or not sample):
        raise ValueError("real smoke did not run precisely one chosen sample")
    execution=json.loads((root/"execution_manifest.json").read_text())
    summary=json.loads((root/"attempt_summary.json").read_text())
    if set(execution)!=expected or set(summary.get("tools",{}))!=expected:
        raise ValueError("real smoke missing a comparator")
    fingerprints=set()
    for name in sorted(expected):
        item=execution[name]
        folder=root/name
        records=verify_collection(folder,{sample},images,name,manifest)
        if (len(records)!=1 or records[sample]["status"]!="finished"
                or not item.get("complete") or item.get("sample_count")!=1
                or item.get("image_id")!=images[name]
                or item.get("results_sha256")!=file_hash(folder/"results.jsonl")):
            raise ValueError(f"{name}: incomplete or changed real smoke")
        row=records[sample]
        for arm,image_name in (("iva","iva"),("ivanka",name)):
            if (row[arm]["image_id"]!=images[image_name]
                    or row[arm].get("exit_code")!=0
                    or not row.get("best_contig_acceptance")):
                raise ValueError(f"{name}: real MiCall smoke arm failed")
        fingerprints.add(tuple(row["provenance"]["fastq_sha256"]))
    if len(fingerprints)!=1:
        raise ValueError("real smoke compares different original paired reads")
    return {"sample":sample,"comparisons":len(expected),
            "successful_micall_arms":2*len(expected),
            "source_manifest_sha256":file_hash(manifest),
            "result_manifest_sha256":file_hash(root/"execution_manifest.json")}
