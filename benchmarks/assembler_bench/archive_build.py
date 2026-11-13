"""Produce stable, privacy-safe views from immutable retained MiCall outputs."""
import argparse
import json
from pathlib import Path

from .archive_sources import image_evidence
from .archive_real import recover as physical
from .archive_synthetic import recover as synthetic
from .psi_matrix import matrix
from .public_dominance import rows_for

SCHEMA="ivanka.assembler-bench.execution-history.v1"
SOURCES=(
    ("prior", "ivanka-fork39c-seven-way-hxb2-400-20261113",
     "ivanka-fork39c-real198-full-20261113",
     "ivanka-fork39c-seven-source-attestation-20261113.json"),
    ("dedicated", "ivanka-dedicated-hxb2-400-full-20261113",
     "ivanka-dedicated-real198-full-20261113",
     "ivanka-dedicated-seven-independent-attestation-20261113.json"),
)


def collect(workspace, synthetic_data, real_data, cache_directory):
    root=Path(workspace)
    all_runs=[]
    for group,syn,real,proof in SOURCES:
        source=root/proof
        att=json.loads(source.read_text())
        synthetic_root,real_root=root/syn,root/real
        for path in (synthetic_root/"run_manifest.json",
                     real_root/"run_manifest.json"):
            meta=json.loads(path.read_text())
            if not meta.get("images"):
                raise ValueError("missing pinned historical image identities")
            from .archive_sources import digest
            if meta.get("fork_attestation_sha256") != digest(source):
                raise ValueError("physical/synthetic attestation differs")
        syn_m=json.loads((synthetic_root/"run_manifest.json").read_text())
        real_m=json.loads((real_root/"run_manifest.json").read_text())
        s_proof=image_evidence(syn_m,att,source)
        r_proof=image_evidence(real_m,att,source)
        all_runs.append(synthetic(
            synthetic_root,synthetic_data,s_proof,
            "hxb2-"+group+"-retained",
            "HXB2 synthetic · "+group+" MiCall build",
            cache_directory))
        for candidate in ("ivanka","haploflow"):
            if not (real_root/candidate/"results.jsonl").is_file():
                continue
            all_runs.append(physical(
                real_root,real_data,r_proof,candidate,
                "real-"+group+"-"+candidate+"-retained",
                "Physical samples · "+group+" "+candidate+" comparison"))
    for run in all_runs:
        run["dominance_matrix"] = matrix(
            rows_for(run), run["tools"],
            expected=run["expected_sample_count"], eligible=False)
    return {"schema":SCHEMA, "runs":all_runs}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,required=True)
    parser.add_argument("--synthetic",type=Path,required=True)
    parser.add_argument("--real",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--cache",type=Path,required=True)
    args=parser.parse_args()
    data=collect(args.workspace,args.synthetic,args.real,args.cache)
    with args.output.open("x") as handle:
        json.dump(data,handle,sort_keys=True,separators=(",",":"))
        handle.write("\n")
    print("ARCHIVED_COMPLETE_EXECUTIONS",
          [(r["id"],r["sample_count"]) for r in data["runs"]])


if __name__=="__main__":
    main()
