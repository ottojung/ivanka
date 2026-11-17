"""One canonical, source-attested 50m Ivanka arm for the frozen 198-case cohort."""
import importlib.util
import json
from pathlib import Path

from benchmarks.expanded.comparators_first_real import BASE, atomic
from benchmarks.expanded.micall_lock import exclusive_lock
from benchmarks.expanded.real_resume import digest
from .environment import prepare
from .gate import prerequisites
from .policy import require
from .replay import recover
from .schedule import dispatch

PRIORITY = Path("/workspace/ivanka-physical-priority-20261117"
                "/benchmarks/physical_ivanka_completion.py")
PRIORITY_SHA = "f4e8ca750a03a9cf02d916f41570412acdcd06480723521d38c8be10ada2675a"


def priority_module():
    if digest(PRIORITY) != PRIORITY_SHA:
        raise ValueError("physical-first completion verifier changed")
    spec = importlib.util.spec_from_file_location("physical_ivanka_completion",
                                                   PRIORITY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(data, original, retries, images, fork, base, attestation, jobs=2):
    if base != BASE or not 1 <= jobs <= 2:
        raise ValueError("canonical physical Ivanka requires <=2 MiCall workers")
    original = Path(original).resolve()
    verify = priority_module()
    with exclusive_lock(original):
        parent = prerequisites(original, retries, images)
        if verify.completed(original, images):
            print("CANONICAL_IVANKA_ALREADY_FINISHED", flush=True)
            return "ALREADY_COMPLETE"
        cases, hxb2, panel, pmm = prepare(
            data, original, images, attestation, fork, base)
        parent["physical_first_source_sha256"] = PRIORITY_SHA
        require(original / "ivanka", parent, images, Path(attestation))
        found = recover(original, cases, images["ivanka"], panel, pmm)
        dispatch(original, cases, found, images["ivanka"],
                 hxb2, panel, pmm, jobs)
        records = recover(original, cases, images["ivanka"], panel, pmm)
        if len(records) != 198:
            raise ValueError("canonical physical Ivanka missing verified cases")
        folder = original / "ivanka"
        proof = {
            "schema": verify.SCHEMA, "samples": 198, "terminal_count": 198,
            "successful": sum(not x["failed"] for x in records.values()),
            "failed": sum(x["failed"] for x in records.values()),
            "image_sha256": images["ivanka"],
            "original_manifest_sha256": digest(original / "run_manifest.json"),
            "journal_sha256": digest(folder / "results.jsonl"),
            "completion_source_sha256": PRIORITY_SHA,
            "resource_budget_seconds": 3000,
            "resource_policy_sha256": digest(folder / "run_manifest.json"),
            "recovery_dependency_sha256": parent["resource_summary_sha256"],
        }
        atomic(folder / "attempt_summary.json", proof)
        if not verify.completed(original, images):
            raise ValueError("physical-seven completion certificate failed")
        print("CANONICAL_PHYSICAL_SEVEN_COMPLETE",
              json.dumps(proof, sort_keys=True), flush=True)
        return "COMPLETE"
