"""Independently authenticated one-time IVA controls shared by real arms."""
import json
from pathlib import Path

from .real_resume import authentic_arm, digest, row_hash, verify_collection

SCHEMA="ivanka.expanded.single-iva-controls.v1"


def control_cache(root, sample):
    base=Path(root)/"iva-baselines"/sample
    if not sample or Path(sample).name!=sample:
        raise ValueError("bad shared-control sample identity")
    return base


def build(root, expected_samples, images):
    """Bind every cached control to the completed, immutable Ivanka+IVA run."""
    root=Path(root).resolve()
    first=root/"ivanka"
    original=verify_collection(first,expected_samples,images,"ivanka",
                               root/"run_manifest.json")
    if set(original)!=expected_samples:
        raise ValueError("cannot share incomplete original IVA controls")
    rows={}
    for sample,row in sorted(original.items()):
        if (row.get("status")!="finished" or
                row.get("iva",{}).get("exit_code")!=0 or
                row.get("iva",{}).get("metrics",{}).get("num_final_max_conseqs",0)<1):
            raise ValueError("original IVA control did not complete: "+sample)
        authentic_arm(row["iva"],images["iva"],first)
        folder=control_cache(root,sample)
        file=folder/"baseline.json"
        copied=folder/"conseq.csv"
        stored=json.loads(file.read_text())
        arm=stored["iva"]
        original_arm=row["iva"]
        without=lambda a:{k:v for k,v in a.items()
                          if k not in ("artifact_dir","source_artifact_dir")}
        if (stored["provenance"]!=row["provenance"]
                or without(arm)!=without(original_arm)
                or arm.get("source_artifact_dir")!=original_arm["artifact_dir"]
                or arm.get("artifact_dir")!=str(folder.resolve())
                or digest(copied)!=
                original_arm["metrics"]["outputs"]["conseq.csv"]["sha256"]):
            raise ValueError("shared IVA cache not created by original control")
        rows[sample]={"original_row_sha256":row_hash(row),
                      "baseline_sha256":digest(file),
                      "consensus_sha256":digest(copied)}
    return {"schema":SCHEMA,"control_image_id":images["iva"],
            "source_run_manifest_sha256":digest(root/"run_manifest.json"),
            "source_results_sha256":digest(first/"results.jsonl"),
            "source_checkpoints_sha256":digest(first/"checkpoints.json"),
            "samples":rows}


def certify(root, expected_samples, images):
    """Atomically publish a stable source witness; reject edits on every rerun."""
    root=Path(root)
    proof=build(root,expected_samples,images)
    path=root/"shared-iva-controls.json"
    if path.exists():
        if json.loads(path.read_text())!=proof:
            raise ValueError("prior shared IVA proof changed")
    else:
        temporary=root/"shared-iva-controls.partial"
        temporary.write_text(json.dumps(proof,sort_keys=True,indent=2)+"\n")
        temporary.replace(path)
    return path


def load(root, manifest, expected_samples, images):
    root=Path(root).resolve()
    path=Path(manifest).resolve(strict=True)
    if path!=root/"shared-iva-controls.json":
        raise ValueError("shared IVA proof path is not from this frozen run")
    if json.loads(path.read_text())!=build(root,expected_samples,images):
        raise ValueError("shared IVA proof no longer matches original results")
    controls={}
    for sample in expected_samples:
        cache=control_cache(root,sample)
        controls[sample]=json.loads((cache/"baseline.json").read_text())["iva"]
    return controls
