"""After the original physical phase, retry only timeouts and SIGKILLs."""
import json
from pathlib import Path

from Bio import SeqIO
from benchmarks.expanded.comparators_first_real import (
    BASE, TOOLS, manifest, rows)
from benchmarks.expanded.comparators_first_synthetic import atomic
from benchmarks.expanded.fork_micall_synthetic import checked_images
from benchmarks.expanded.micall_lock import exclusive_lock
from benchmarks.expanded.physical_inputs import attest
from project_references import final_max_sequences
from reference_panel import (
    best_panel_alignment, build_reference_panel, panel_sha256)
from .eligibility import selected
from .evidence import originals
from .policy import receipt
from .schedule import dispatch


def run(data, out, original, images, fork, base, attestation, jobs=4):
    if not 1 <= jobs <= 4 or base != BASE:
        raise ValueError("physical retry resources outside approved limits")
    out, original = Path(out).resolve(), Path(original).resolve()
    with exclusive_lock(out):
        checked_images(images, attestation, fork, base)
        attest(data)
        cases = rows(data)
        import podman_full_micall as pmm
        pmm.DATA = Path(data).resolve()
        pmm.RESULTS = original / "artifacts"
        pmm.best_panel_alignment = best_panel_alignment
        pmm.final_max_sequences = final_max_sequences
        hxb2 = next(SeqIO.parse(str(Path(data) / "hxb2.fasta"), "fasta")).seq
        projects, _ = pmm.load_micall_projects(images["iva"])
        panel = build_reference_panel(projects, hxb2)
        if json.loads((original / "run_manifest.json").read_text()) != manifest(
                data, images, attestation, panel_sha256(panel)):
            raise ValueError("original physical manifest/source changed")
        existing = originals(original, cases, images, panel, pmm)
        eligible = {tool: {key for key, record in existing[tool].items()
                           if selected(record)} for tool in TOOLS}
        out.mkdir(parents=True, exist_ok=True)
        receipt(out, original, eligible)
        pmm.RESULTS = out / "artifacts"
        pmm.RESULTS.mkdir(exist_ok=True)
        counts = dispatch(out, original, cases, eligible, images,
                          hxb2, panel, pmm, jobs)
        summary = {"schema": "ivanka.expanded.physical-resource-retry.v1",
                   "original": str(original), "timeout_seconds": 3000,
                   "eligible": {name: len(ids) for name, ids in eligible.items()},
                   "finished": True, "ivanka_deferred": True}
        atomic(out / "attempt_summary.json", summary)
        print("RESOURCE_PHYSICAL_FINISHED", counts, flush=True)
        return summary
