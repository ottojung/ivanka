"""Build the exact MiCall reference panel and immutable source inputs."""
from pathlib import Path

from Bio import SeqIO
from benchmarks.expanded.comparators_first_real import rows, PANEL
from benchmarks.expanded.physical_inputs import attest
from benchmarks.expanded.fork_micall_synthetic import checked_images
from project_references import final_max_sequences
from reference_panel import (
    best_panel_alignment, build_reference_panel, panel_sha256)


def prepare(data, out, images, attestation, fork, base):
    checked_images(images, attestation, fork, base)
    attest(data)
    cases = rows(data)
    import podman_full_micall as pmm
    pmm.DATA = Path(data).resolve()
    pmm.RESULTS = Path(out).resolve() / "artifacts"
    pmm.best_panel_alignment = best_panel_alignment
    pmm.final_max_sequences = final_max_sequences
    hxb2 = next(SeqIO.parse(str(Path(data) / "hxb2.fasta"), "fasta")).seq
    projects, _ = pmm.load_micall_projects(images["iva"])
    panel = build_reference_panel(projects, hxb2)
    if panel_sha256(panel) != PANEL:
        raise ValueError("physical scoring panel changed")
    pmm.RESULTS.mkdir(exist_ok=True, parents=True)
    return cases, hxb2, panel, pmm
