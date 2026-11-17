"""Observe running MiCall images without inventing execution from missing data."""
import json
from pathlib import Path
import subprocess

SCHEMA="ivanka.assembler-bench.live-worker-activity.v1"
COHORTS=("real","synthetic")


def selected(root):
    source=Path(root)/"run_manifest.json"
    if not source.is_file():
        return set()
    value=json.loads(source.read_text())
    images=value.get("images")
    if not isinstance(images,dict):
        raise ValueError("invalid source-attested runner images")
    return set(images)


def running(images):
    try:
        result=subprocess.run(["podman","ps","--format",
            "{{.Names}}\t{{.ImageID}}"],check=True,
            capture_output=True,text=True,timeout=20)
    except (OSError,subprocess.SubprocessError):
        return None
    found={cohort:set() for cohort in COHORTS}
    for line in result.stdout.splitlines():
        parts=line.split("\t")
        if len(parts)!=2:
            raise ValueError("unrecognized running Podman container record")
        name,image=parts
        if not name.startswith("ivanka-bench-"):
            continue
        prefix=image.removeprefix("sha256:")
        matches=[key for key,value in images.items()
                 if value.startswith(prefix) and len(prefix)>=12]
        if len(matches)!=1:
            raise ValueError("running benchmark image differs from frozen images")
        if name.startswith("ivanka-bench-synth-"):
            cohort="synthetic"
        elif (name.startswith("ivanka-bench-iva-")
                or name.startswith("ivanka-bench-ivanka-")):
            cohort="real"
        else:
            raise ValueError("unknown benchmark container execution cohort")
        found[cohort].add(matches[0])
    return {cohort:sorted(names) for cohort,names in found.items()}


def snapshot(synthetic,physical,images,order=COHORTS):
    if set(order)!=set(COHORTS) or len(order)!=len(COHORTS):
        raise ValueError("unknown cohort execution priority")
    planned=selected(synthetic)|selected(physical)
    if planned-set(images):
        raise ValueError("running workload and frozen sources differ")
    activity=running(images)
    return {"schema":SCHEMA,"status":"observed" if activity is not None
            else "unavailable","order":list(order),
            "running":activity if activity is not None else
                {cohort:[] for cohort in COHORTS},
            "deferred":sorted(set(images)-planned)}


def validate(record,report):
    if record is None:
        return
    expected={"schema","status","order","running","deferred"}
    tools=set(report["runs"][0]["tools"])
    if (set(record)!=expected or record["schema"]!=SCHEMA
            or record["status"] not in ("observed","unavailable")
            or set(record["order"])!=set(COHORTS)
            or len(record["order"])!=len(COHORTS)
            or set(record["running"])!=set(COHORTS)
            or not isinstance(record["deferred"],list)
            or len(set(record["deferred"]))!=len(record["deferred"])
            or set(record["deferred"])-tools):
        raise ValueError("invalid current MiCall worker activity")
    for cohort in COHORTS:
        names=record["running"][cohort]
        if (not isinstance(names,list) or len(set(names))!=len(names)
                or set(names)-tools or set(names)&set(record["deferred"])):
            raise ValueError("unknown or deferred assembler shown running")
    if record["status"]=="unavailable" and any(
            record["running"][cohort] for cohort in COHORTS):
        raise ValueError("cannot claim running tools without observation")
