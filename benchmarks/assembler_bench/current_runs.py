"""Generic current-run reports: one data model for counters, charts and Ψ."""
import hashlib
import json
from pathlib import Path

from benchmarks.expanded.adapters import ASSEMBLERS
from benchmarks.expanded.micall_dominant import SCORE_ORIGIN
from .hxb2_preview import COHORT_SHA, sha
from .current_inputs import PROGRESS_SCHEMA, physical, synthetic
from .public_dominance import enrich
from .current_mapping import catalog, missing_arm
from .public_metrics import SCHEMA as METRIC_SCHEMA

SCHEMA="ivanka.assembler-bench.public.v1"


def fork_provenance(attestation,images):
    proof=json.loads(Path(attestation).read_text())
    source=proof.get("images",{})
    if (proof.get("schema")!="ivanka.assembler-bench.minimal-fork-images.v1"
            or set(source)!=set(images)
            or any(entry.get("image_sha256")!=images[name]
                   for name,entry in source.items())):
        raise ValueError("seven source images differ from frozen attestation")
    return {"status":"verified",
            "message":"Exact commits and immutable MiCall images; unmeasured results are never inferred.",
            "attestation_sha256":sha(attestation),
            "attestation_schema":proof["schema"],
            "baseline_commit":proof["baseline_commit"],
            "images":{name:{k:entry[k] for k in
                       ("source_branch","source_commit","source_url","image_sha256")}
                      for name,entry in source.items()}}


def observed(sample,tool):
    return sample["score"][tool] is not None or tool in sample["failures"]


def progress(rows,tools,expected):
    return {tool:{"expected":expected,
                  "finished":sum(observed(row,tool) for row in rows),
                  "failed":sum(tool in row["failures"] for row in rows)}
            for tool in tools}


def status(row,tools):
    if row["failures"]:
        row["outcome"]="failure"
        return
    if all(row["score"][tool] is not None for tool in tools):
        row["outcome"]="success"
        row["floor_ok"]=row["score"]["ivanka"]>=.9*max(
            row["score"][tool] for tool in tools if tool!="ivanka")
    else:
        row["outcome"]="incomplete"


def make_run(cohort,rows,expected,images,provenance,source_sha,when):
    ordered=sorted(rows,key=lambda item:item["alias"])
    tools=list(ASSEMBLERS)
    for row in ordered:
        status(row,tools)
    counts=progress(ordered,tools,expected)
    return {"schema":SCHEMA,
            "progress_schema":PROGRESS_SCHEMA,
            "id":f"current-{cohort}-micall-{when}",
            "title":{"real":"Current · physical MiCall",
                     "synthetic":"Current · HXB2 synthetic MiCall",
                     "combined":"Current · combined MiCall"}[cohort],
            "cohort":cohort,"date":when,"status":"incomplete",
            "expanded_status":"incomplete","eligible_for_expanded":False,
            "hxb2_truth_verified":cohort=="synthetic",
            "expected_sample_count":expected,"sample_count":len(ordered),
            "tools":tools,"images":images,"samples":ordered,
            "source_manifest_sha256":source_sha,
            "micall_fork_provenance":provenance,
            "source_commit":provenance["images"]["iva"]["source_commit"],
            "tool_progress":counts,"psi":{},
            "score_origin":SCORE_ORIGIN,
            "status_reason":"Independent source-verified MiCall final MAX "
                "local-alignment and in-container runtime measurements.",
            **({"cohort_manifest_sha256":COHORT_SHA}
               if cohort=="synthetic" else {})}


def combine(synthetic_run,real_run,images,provenance,when):
    rows=[]
    for prefix,run in (("S",synthetic_run),("R",real_run)):
        for item in run["samples"]:
            row={**item,"alias":prefix+"-"+item["alias"],
                 "family":item.get("family","physical")}
            rows.append(row)
    source=hashlib.sha256(json.dumps(
        [synthetic_run["source_manifest_sha256"],
         real_run["source_manifest_sha256"]]).encode()).hexdigest()
    result=make_run("combined",rows,598,images,provenance,source,when)
    result["cohorts"]={"synthetic":synthetic_run["sample_count"],
                       "real":real_run["sample_count"]}
    result["source_runs"]=[synthetic_run["id"],real_run["id"]]
    return result


def current(synthetic_root,real_root,physical_data,runner,attestation,images,when,physical_witness,physical_attestation):
    sy,sproof=synthetic(synthetic_root,images,attestation,runner)
    re,rproof=physical(real_root,physical_data,images,attestation,runner,physical_witness,physical_attestation)
    proof=fork_provenance(attestation,images)
    syn=make_run("synthetic",list(sy.values()),400,images,proof,sproof,when)
    real=make_run("real",list(re.values()),198,images,proof,rproof,when)
    combined=combine(syn,real,images,proof,when)
    public={"schema":SCHEMA,"title":"Ivanka Assembler Bench",
            "expanded_qualification":"incomplete",
            "runs":[syn,real,combined]}
    return enrich(public)


def blank_mapping(run):
    return {"schema":METRIC_SCHEMA,"run_id":run["id"],"sample_alias":None,
            "status":"INCOMPLETE","cases_measured":0,
            "expected_cases":run["expected_sample_count"],
            "cohort":"Source-attested MiCall benchmark",
            "note":"No complete seven-arm mapping sample; individual verified diagnostics are in the current runs.",
            "metric_catalog":catalog(),
            "tools":{name:missing_arm() for name in run["tools"]}}


def write(site,public,attestation):
    site=Path(site)
    data=site/"data"
    (data/"live-fork-attestation.json").write_bytes(Path(attestation).read_bytes())
    mapping=blank_mapping(public["runs"][0])
    (data/"mapping-diagnostics.json").write_text(json.dumps(mapping,sort_keys=True,indent=2)+"\n")
    (data/"runs.json").write_text(json.dumps(public,sort_keys=True,indent=2)+"\n")
    print("CURRENT_RUNS_UPDATED",[(r["cohort"],r["sample_count"],
          {k:v["finished"] for k,v in r["tool_progress"].items()})
          for r in public["runs"]],flush=True)
