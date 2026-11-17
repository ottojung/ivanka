"""Transactional, monotone publication of current MiCall cohorts to ordinary UI."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import tempfile

from .current_inputs import PROGRESS_SCHEMA
from .current_runs import current,write
from .site_build import validate_public_site
from .workload_activity import snapshot as worker_snapshot


def frozen_date(root):
    manifest=Path(root)/"run_manifest.json"
    if not manifest.is_file():
        raise ValueError("cannot publish before the source run is frozen")
    return datetime.fromtimestamp(
        manifest.stat().st_mtime,timezone.utc).strftime("%Y-%m-%d")


def monotone(prior,current):
    old={run["cohort"]:run for run in prior["runs"]}
    new={run["cohort"]:run for run in current["runs"]}
    if set(old)!=set(new):
        raise ValueError("current cohort identities disappeared")
    for cohort,now in new.items():
        before=old[cohort]
        if (now["id"]!=before["id"] or now["images"]!=before["images"]
                or now["expected_sample_count"]!=before["expected_sample_count"]):
            raise ValueError("current MiCall source identity changed")
        for name in now["tools"]:
            if (now["tool_progress"][name]["finished"]<
                    before["tool_progress"][name]["finished"]):
                raise ValueError("live result count regressed")
        previous={row["alias"]:row for row in before["samples"]}
        observed={row["alias"]:row for row in now["samples"]}
        for alias,row in previous.items():
            newer=observed.get(alias)
            if newer is None:
                raise ValueError("verified case vanished")
            for tool in now["tools"]:
                if (row["score"][tool] is not None and
                        newer["score"][tool]!=row["score"][tool]):
                    raise ValueError("previously scored MiCall arm changed")
                if (row["seconds"][tool] is not None and
                        newer["seconds"][tool]!=row["seconds"][tool]):
                    raise ValueError("previously timed MiCall arm changed")
                if tool in row["failures"] and tool not in newer["failures"]:
                    proof=newer.get("recovery",{}).get(tool)
                    if (not isinstance(proof,dict)
                            or proof.get("timeout_seconds")!=3000
                            or proof.get("status")!="success"
                            or not isinstance(
                                proof.get("original_checkpoint_sha256"),str)
                            or not isinstance(
                                proof.get("retry_checkpoint_sha256"),str)):
                        raise ValueError("unverified old arm failure disappeared")


def update(site,synth,physical,data,runner,attestation,images,physical_witness,physical_attestation,*,migrate=False,include_workload=False,cohort_order=("real","synthetic"),resources=None,real_retries=None,synthetic_data=None,synthetic_runner=None):
    site=Path(site)
    when=frozen_date(synth)
    generated=current(synth,physical,data,runner,attestation,images,when,
                      physical_witness,physical_attestation,resources,real_retries,
                      synthetic_data=synthetic_data,synthetic_runner=synthetic_runner)
    if include_workload:
        generated["workload"]=worker_snapshot(synth,physical,images,
                                             order=cohort_order)
    target=site/"data/runs.json"
    old=json.loads(target.read_text())
    before=all(run.get("progress_schema")==PROGRESS_SCHEMA
               for run in old["runs"])
    old_synth = next((r for r in old["runs"]
                      if r.get("cohort") == "synthetic"), {})
    new_synth = next((r for r in generated["runs"]
                      if r.get("cohort") == "synthetic"), {})
    rollover = (migrate and old_synth.get("expected_sample_count") == 400
                and new_synth.get("expected_sample_count") == 464
                and new_synth.get("score_origin") ==
                    "micall_final_max_abundant_truths_balanced_v2"
                and new_synth.get("cohort_manifest_sha256") ==
                    "90990f6109553347d37f7754cde63398a4dce57c388f90c2ce4b648530bfdfe4")
    if rollover:
        # A source change invalidates synthetic scores, but does not erase
        # completed physical measurements or allow their replacement.
        physical_before = next(r for r in old["runs"]
                               if r.get("cohort") == "real")
        physical_new = next(r for r in generated["runs"]
                            if r.get("cohort") == "real")
        monotone({"runs":[physical_before]},
                 {"runs":[physical_new]})
    elif before:
        monotone(old,generated)
    elif not migrate:
        raise ValueError("old misleading current cohorts require explicit migration")
    elif any(r.get("progress_schema")==PROGRESS_SCHEMA for r in old["runs"]):
        raise ValueError("partially migrated current runs are unsafe")
    # Validation uses an entire identical site snapshot before touching Git.
    payload=json.dumps(generated,sort_keys=True,separators=(",",":"))
    same=(before and payload==json.dumps(
        {k:v for k,v in old.items() if k!="published_at"},
        sort_keys=True,separators=(",",":")))
    if same:
        print("CURRENT_RUNS_UNCHANGED",flush=True)
        return False
    generated["published_at"]=datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="active-bench-") as scratch:
        stage=Path(scratch)/"bench"
        shutil.copytree(site,stage)
        write(stage,generated,attestation)
        validate_public_site(stage)
        for name in ("runs.json","mapping-diagnostics.json",
                     "live-fork-attestation.json"):
            source=stage/"data"/name
            destination=site/"data"/name
            pending=destination.with_suffix(".json.pending")
            pending.write_bytes(source.read_bytes())
            pending.replace(destination)
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("site","synthetic","real","real-data","runner",
                 "attestation","images","physical-witness","physical-attestation"):
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--migrate",action="store_true")
    parser.add_argument("--with-activity",action="store_true")
    parser.add_argument("--cohort-order",default="real,synthetic")
    parser.add_argument("--resources",type=Path)
    parser.add_argument("--real-retries",type=Path)
    parser.add_argument("--synthetic-data",type=Path)
    parser.add_argument("--synthetic-runner",type=Path)
    args=parser.parse_args()
    images=json.loads(Path(args.images).read_text())
    update(args.site,args.synthetic,args.real,args.real_data,args.runner,
           args.attestation,images,args.physical_witness,args.physical_attestation,
           migrate=args.migrate,include_workload=args.with_activity,
           cohort_order=tuple(args.cohort_order.split(",")),
           resources=args.resources,real_retries=args.real_retries,
           synthetic_data=args.synthetic_data,
           synthetic_runner=args.synthetic_runner)


if __name__=="__main__":
    main()
