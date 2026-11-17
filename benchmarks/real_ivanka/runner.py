"""Reconstruct 198 physical Ivanka MiCall results without rerunning competitors."""
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


def run(data, out, original, retries, images, fork, base, attestation,
        jobs=2):
    if not 1 <= jobs <= 2 or base != BASE:
        raise ValueError("physical Ivanka CPU/RAM concurrency outside policy")
    out = Path(out).resolve()
    original, retries = Path(original).resolve(), Path(retries).resolve()
    prerequisites(original, retries, images)
    with exclusive_lock(out):
        parents = prerequisites(original, retries, images)
        cases, hxb2, panel, pmm = prepare(
            data, out, images, attestation, fork, base)
        require(out, parents, images, Path(attestation))
        completed = recover(out, cases, images["ivanka"], panel, pmm)
        dispatch(out, cases, completed, images["ivanka"],
                 hxb2, panel, pmm, jobs)
        records = recover(out, cases, images["ivanka"], panel, pmm)
        if len(records) != 198:
            raise ValueError("physical Ivanka cohort has missing evidence")
        summary = {
            "schema": "ivanka.expanded.physical-ivanka-50m.v1",
            "sample_count": 198, "successful": sum(not x["failed"]
                                                 for x in records.values()),
            "failed": sum(x["failed"] for x in records.values()),
            "status": "ATTEMPTED_NOT_QUALIFIED",
            "timeout_seconds": 3000,
            "run_manifest_sha256": digest(out / "run_manifest.json"),
            "results_sha256": digest(out / "ivanka/results.jsonl"),
        }
        atomic(out / "attempt_summary.json", summary)
        print("PHYSICAL_IVANKA_FINISHED", json.dumps(summary), flush=True)
        return summary
