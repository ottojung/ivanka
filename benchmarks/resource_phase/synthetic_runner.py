"""Resume frozen 400-case cohort with five 5-GiB workers and 50m per arm."""
import json
from pathlib import Path

from benchmarks.expanded.comparators_first_synthetic import (
    BASE, SCHEMA, TOOLS, atomic, source_manifest)
from benchmarks.expanded.fork_micall_synthetic import checked_images
from benchmarks.expanded.hxb2_cohort import attestation
from benchmarks.expanded.micall_checkpoint import digest
from benchmarks.expanded.micall_lock import exclusive_lock
from benchmarks.expanded.run_synthetic import cohort_rows

from .synthetic_arm import install
from .synthetic_batch import dispatch
from .synthetic_journal import rehydrate
from .synthetic_policy import receipt
from .synthetic_replay import prepare, write_completed


def run(data, out, images, fork, base, attestation_file, jobs=5):
    if not 1 <= jobs <= 5 or base != BASE:
        raise ValueError("invalid source base or resource-policy concurrency")
    out = Path(out).resolve()
    with exclusive_lock(out):
        checked_images(images, attestation_file, fork, base)
        proof = attestation(data, expected=400)
        cohort = list(cohort_rows(data))
        if len(cohort) != 400:
            raise ValueError("synthetic cohort changed")
        expected = source_manifest(data, proof, images, attestation_file)
        frozen = out / "run_manifest.json"
        if not frozen.is_file() or json.loads(frozen.read_text()) != expected:
            raise ValueError("frozen original synthetic manifest mismatch")
        receipt(out)
        recovered = rehydrate(out, cohort, images, proof)
        results = {}
        for row in cohort:
            key = row[0]
            results[key] = (dict(recovered[key]["results"]) if key in recovered
                            else prepare(out / key, images))
            if len(results[key]) == len(TOOLS) and key not in recovered:
                write_completed(out / key, row, proof, results[key])
        rehydrate(out, cohort, images, proof)
        install()
        counts = dispatch(out, cohort, images, proof, results, jobs)
        complete = rehydrate(out, cohort, images, proof)
        if len(complete) != 400:
            raise ValueError("resource phase synthetic cohort incomplete")
        summary = {"schema": SCHEMA, "ivanka_deferred": True,
                   "sample_count": 400, "arms": 2400,
                   "results_sha256": digest(out / "results.jsonl"),
                   "run_manifest_sha256": digest(frozen)}
        atomic(out / "attempt_summary.json", summary)
        print("RESOURCE_SYNTHETIC_FINISHED", counts, flush=True)
        return summary
