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
                    raise ValueError("old verified arm failure disappeared")


def update(site,synth,physical,data,runner,attestation,images,physical_witness,physical_attestation,*,migrate=False,include_workload=False,cohort_order=("real","synthetic")):
    site=Path(site)
    when=frozen_date(synth)
    generated=current(synth,physical,data,runner,attestation,images,when,physical_witness,physical_attestation)
    if include_workload:
        generated["workload"]=worker_snapshot(synth,physical,images,
                                             order=cohort_order)
    target=site/"data/runs.json"
    old=json.loads(target.read_text())
    before=all(run.get("progress_schema")==PROGRESS_SCHEMA
               for run in old["runs"])
    if before:
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
    args=parser.parse_args()
    images=json.loads(Path(args.images).read_text())
    update(args.site,args.synthetic,args.real,args.real_data,args.runner,
           args.attestation,images,args.physical_witness,args.physical_attestation,
           migrate=args.migrate,include_workload=args.with_activity,
           cohort_order=tuple(args.cohort_order.split(",")))


if __name__=="__main__":
    main()
