"""Record exact source/parent/evidence identity before a 198-case run."""
import json
from pathlib import Path

from benchmarks.expanded.comparators_first_synthetic import atomic
from benchmarks.expanded.real_resume import digest


def require(root, parent, images, attestation):
    here = Path(__file__).resolve()
    files = [here, *[here.with_name(name) for name in (
        "__main__.py", "attempt.py", "environment.py",
        "gate.py", "replay.py", "runner.py", "schedule.py")],
        here.parents[1] / "real_recovery/proof/arm.py",
        here.parents[1] / "real_recovery/proof/record.py"]
    value = {"schema": "ivanka.expanded.physical-ivanka-50m.v1",
             "samples": 198, "timeout_seconds": 3000, "workers": 2,
             "ivanka_image_id": images["ivanka"], "parent": parent,
             "attestation_sha256": digest(attestation),
             "sources": {str(p.relative_to(here.parents[1])): digest(p)
                         for p in files}}
    target = root / "run_manifest.json"
    if target.exists():
        if json.loads(target.read_text()) != value:
            raise ValueError("physical Ivanka source/parent/image changed")
    else:
        root.mkdir(parents=True, exist_ok=True)
        atomic(target, value)
    return value
