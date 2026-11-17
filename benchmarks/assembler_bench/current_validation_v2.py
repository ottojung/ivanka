"""Validate cohort-agnostic active MiCall evidence without assuming seven complete arms."""
import math
import re

from benchmarks.expanded.adapters import ASSEMBLERS
from benchmarks.expanded.micall_dominant import SCORE_ORIGIN
from .current_inputs import PROGRESS_SCHEMA
from .public_case_metrics import validate_sample
from .hxb2_preview import COHORT_SHA
from .current_runs import observed

SAMPLE={"synthetic":re.compile(r"H[0-9]{3}"),
        "real":re.compile(r"R[0-9]{3}"),
        "combined":re.compile(r"[SR]-[HR][0-9]{3}")}
EXPECTED={"synthetic":400,"real":198,"combined":598}


def check_sample(row,run):
    tools=run["tools"]
    if (not isinstance(row,dict)
            or not SAMPLE[run["cohort"]].fullmatch(row.get("alias",""))
            or set(row.get("score",{}))!=set(tools)
            or set(row.get("seconds",{}))!=set(tools)
            or set(row.get("failures",[]))-set(tools)
            or len(row["failures"])!=len(set(row["failures"]))):
        raise ValueError("active case has wrong alias/assembler fields")
    validate_sample(row,tools)
    scores=row["score"]
    for tool in tools:
        a,b=scores[tool],row["seconds"][tool]
        if (a is None)!=(b is None):
            raise ValueError("active score and timer are not paired")
        if a is not None and (type(a) not in (int,float)
            or type(b) not in (int,float) or not math.isfinite(a)
            or not math.isfinite(b) or a<0 or not 0<b<=1800
            or tool in row["failures"]):
            raise ValueError("invalid real MiCall timer or alignment")
    complete=all(scores[tool] is not None for tool in tools)
    outcome=("failure" if row["failures"] else
             "success" if complete else "incomplete")
    floor=(scores["ivanka"] >= .9*max(scores[t] for t in tools if t!="ivanka")
           if complete else None)
    if row.get("outcome")!=outcome or row.get("floor_ok") is not floor:
        raise ValueError("active case claims unsupported success or alignment floor")


def check_run(run):
    cohort=run.get("cohort")
    if cohort not in EXPECTED:
        raise ValueError("active MiCall run has unexpected cohort")
    tools=run.get("tools")
    expected=EXPECTED[cohort]
    if (run.get("schema")!="ivanka.assembler-bench.public.v1"
            or run.get("progress_schema")!=PROGRESS_SCHEMA
            or run.get("status")!="incomplete"
            or run.get("expanded_status")!="incomplete"
            or run.get("eligible_for_expanded") is not False
            or run.get("score_origin")!=SCORE_ORIGIN
            or tools!=list(ASSEMBLERS)
            or set(run.get("images",{}))!=set(tools)
            or run.get("expected_sample_count")!=expected
            or run.get("psi")!={}
            or run.get("hxb2_truth_verified") is not (cohort=="synthetic")
            or cohort=="synthetic" and run.get("cohort_manifest_sha256")!=COHORT_SHA):
        raise ValueError("active MiCall cohort metadata/qualification invalid")
    rows=run.get("samples")
    if (not isinstance(rows,list) or len(rows)>expected
            or run.get("sample_count")!=len(rows)
            or len({r.get("alias") for r in rows})!=len(rows)
            or any(rows[i]["alias"]>=rows[i+1]["alias"]
                   for i in range(len(rows)-1))):
        raise ValueError("active sample count or sort order forged")
    for item in rows:
        check_sample(item,run)
    if cohort=="synthetic" and any(not re.fullmatch(
            "[a-z0-9_]+",row.get("family","")) for row in rows):
        raise ValueError("unknown biological synthetic sample family")
    actual={tool:{"expected":expected,
                  "finished":sum(observed(row,tool) for row in rows),
                  "failed":sum(tool in row["failures"] for row in rows)}
            for tool in tools}
    if run.get("tool_progress")!=actual:
        raise ValueError("active counter and per-sample records disagree")
    source=run.get("source_manifest_sha256")
    if (source is not None and not re.fullmatch("[0-9a-f]{64}",source)
            or source is None and rows):
        raise ValueError("active input source manifest is absent or invalid")
    return actual


def check_current(report):
    runs=report.get("runs",[])
    if (len(runs)!=3 or set(r.get("cohort") for r in runs)!=set(EXPECTED)
            or report.get("expanded_qualification")!="incomplete"):
        raise ValueError("current website lacks coherent three-cohort report")
    data={run["cohort"]:run for run in runs}
    for run in runs:
        check_run(run)
        if run["images"]!=data["synthetic"]["images"]:
            raise ValueError("mismatched source image identities across cohorts")
    combined=data["combined"]
    sy=data["synthetic"]
    re=data["real"]
    if (combined.get("cohorts")!={"synthetic":sy["sample_count"],
                                  "real":re["sample_count"]}
            or combined.get("source_runs")!=[sy["id"],re["id"]]):
        raise ValueError("combined view does not bind its two cohorts")
    for prefix,run in (("S",sy),("R",re)):
        originals={prefix+"-"+row["alias"]:row for row in run["samples"]}
        matched=[row for row in combined["samples"]
                 if row["alias"].startswith(prefix+"-")]
        if len(matched)!=len(originals):
            raise ValueError("combined current sample count differs")
        for row in matched:
            original=originals.get(row["alias"])
            if original is None or any(
                    row.get(k)!=original.get(k) for k in
                    ("score","seconds","failures","diagnostics",
                     "exact_profiles","floor_ok","outcome")):
                raise ValueError("combined source scientific values were changed")
    return True
