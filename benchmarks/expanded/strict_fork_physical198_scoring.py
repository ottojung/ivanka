"""Recompute final-MAX scores from the immutable IVA image's reference panel."""
from pathlib import Path

from reference_catalog import load_micall_projects
from reference_panel import build_reference_panel, panel_acceptance, panel_sha256


def authenticate_scores(records, dataset, images, expected_panel):
    """Reject any journal score that disagrees with retained MiCall output."""
    from Bio import SeqIO
    projects, _ = load_micall_projects(images["iva"])
    with (Path(dataset) / "hxb2.fasta").open() as handle:
        sequences = list(SeqIO.parse(handle, "fasta"))
    if len(sequences) != 1:
        raise ValueError("HXB2 source must contain exactly one sequence")
    panel = build_reference_panel(projects, sequences[0].seq)
    if len(panel) != 33 or panel_sha256(panel) != expected_panel:
        raise ValueError("source image reference panel differs from frozen panel")
    # Same final-MAX consensus sequences imply the same deterministic score,
    # including orientation and winning reference. Cache only within this
    # authenticated immutable panel; no cached journal scores are trusted.
    score_cache = {}
    for sample, record in records.items():
        original = record["best_contig_acceptance"]
        actual = panel_acceptance(record["iva"]["artifact_dir"],
                                  record["ivanka"]["artifact_dir"], panel,
                                  min_ratio=.90, score_cache=score_cache)
        if actual != original:
            raise ValueError("final MAX score evidence disagrees with retained output")
    return panel_sha256(panel)
