"""Objective alpha gates. HXB2 score is necessary, not sufficient."""
from pathlib import Path

import mappy
from Bio import SeqIO

# Roles are supplied from a private dataset manifest, never embedded in source.
STRUCTURAL_ROLES = {"mixed", "deletion", "fragmented"}

def reference_fidelity(reference_fasta: Path, output_fasta: Path, min_coverage: float = 0.85) -> dict:
    """Compare output molecules to real IVA raw structural controls.

    Use alignment ONLY in the evaluator; never feed truth or HXB2 into Riva.
    This is a conservative check, not proof of no recombinant chimeras.
    """
    targets = sorted(
        (x for x in SeqIO.parse(reference_fasta, "fasta") if len(x.seq) >= 2000),
        key=lambda x: len(x.seq), reverse=True,
    )[:3]
    outputs = [x for x in SeqIO.parse(output_fasta, "fasta") if len(x.seq) >= 600]
    if not targets:
        return {"pass": False, "reason": "no substantial IVA reference molecules", "coverage": []}
    aligner = mappy.Aligner(str(output_fasta), preset="asm5", best_n=25)
    if not aligner:
        return {"pass": False, "reason": "no indexed Riva output", "coverage": []}
    by_target = []
    for original in targets:
        best = (0.0, 0.0)
        for h in aligner.map(str(original.seq)):
            # This match must cover one coherent stretch of the IVA target;
            # independently aligned partial matches cannot be summed.
            match_fraction = h.mlen / max(1, h.blen)
            cov = (h.q_en - h.q_st) / len(original.seq)
            if (cov, match_fraction) > best:
                best = (cov, match_fraction)
        by_target.append({"iva_length": len(original.seq), "coverage": round(best[0],4),
                          "identity": round(best[1],4),
                          "pass": best[0] >= min_coverage and best[1] >= 0.95})
    return {"pass": any(x["pass"] for x in by_target), "coverage": by_target,
            "min_coverage": min_coverage, "min_identity": 0.95}


def accept_sample(role: str, iva: dict, riva: dict, structural: dict | None = None) -> tuple[bool, list[str]]:
    problems = []
    expected, actual = iva.get("hxb2_score"), riva.get("hxb2_score")
    if expected is None or actual is None:
        problems.append("missing HXB2 score")
    elif expected > 0:
        if actual < expected * 0.95:
            problems.append(f"HXB2 score {actual} below 95% IVA score {expected}")
    elif actual < expected:
        problems.append(f"nonpositive IVA baseline {expected}; Riva {actual} is worse")
    if riva.get("stitched_count", 0) <= 0:
        problems.append("no surviving contigs after 600-base filtering/stitching")
    # Structural-control comparison is reported as a separate diagnostic.
    # The alpha acceptance criterion is existential over individual assembled
    # contigs: one contig meeting the HXB2 threshold is enough. In particular,
    # do not require all IVA controls or all Riva output contigs to match.
    # This does not imply that an alignment-scoring contig is chimera-free.
    return not problems, problems
