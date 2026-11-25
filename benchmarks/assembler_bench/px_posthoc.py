"""Source-pinned posthoc scoring for PX final MAX outputs.

Scoring is post-execution only: truth/reference never enters the assembler.
Physical scoring uses the fixed 33-reference panel local alignment. Synthetic
scoring uses the canonical MiCall final-MAX abundant-truth balanced scorer.
"""
import hashlib
import json
from pathlib import Path

from . import px_cohort_scheduler as sched
from . import px_source_pins

SCHEMA = "ivanka.px.scorer.v1"
PHYSICAL_METHOD = "best_final_max_contig_local_alignment_over_reference_panel"
SYNTHETIC_METHOD = "micall_final_max_abundant_truths_balanced_v2"


def source_sha256():
    """Bind scorer identity to the canonical source digests it executes."""
    sources = px_source_pins.verify()
    payload = json.dumps(sources, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def build_default_scorer(projects_path=None, hxb2_path=None):
    """Build a scorer from canonical reference assets when available."""
    repo = Path(__file__).resolve().parents[2]
    hxb2 = Path(hxb2_path) if hxb2_path else (
        repo / "benchmarks/expanded/references/K03455.1.fasta")
    candidates = [Path(projects_path)] if projects_path else [
        Path("/workspace/micall-px-skesa-zero-20261123/micall/projects.json"),
        repo / "benchmarks" / "projects.json",
    ]
    projects = next((p for p in candidates if p.is_file()), None)
    panel = None
    panel_sha = None
    if projects and hxb2.is_file():
        from benchmarks.expanded.score import read_fasta
        from benchmarks.reference_panel import build_reference_panel, panel_sha256
        panel = build_reference_panel(json.loads(projects.read_bytes()),
                                      read_fasta(hxb2)[0])
        panel_sha = panel_sha256(panel)
    return PxScorer(physical_panel=panel, physical_panel_sha256=panel_sha)


def _final_max_sequences(output_dir):
    from benchmarks.project_references import final_max_sequences
    return final_max_sequences(Path(output_dir))


def _manifest_truth(manifest_path):
    """Read the exact frozen truth digest without opening truth contents."""
    data = json.loads(Path(manifest_path).read_bytes())
    digest = (data.get("sha256") or {}).get("hidden-truth/haplotypes.fasta")
    if not sched.SHA256.fullmatch(digest or ""):
        raise ValueError("synthetic truth hash is not pinned")
    return digest


class PxScorer:
    """Score one PX arm from its retained final MAX output only."""

    def __init__(self, *, physical_panel=None, physical_panel_sha256=None,
                 synthetic_manifest=None, synthetic_truth=None):
        self.physical_panel = physical_panel
        self.physical_panel_sha256 = physical_panel_sha256
        self.synthetic_manifest = synthetic_manifest
        self.synthetic_truth = synthetic_truth
        self.source_sha256 = source_sha256()

    def score(self, *, alias, cohort, output_sha256, output_dir=None,
              receipt=None, arm=None, case=None):
        del arm
        if output_dir is None:
            raise ValueError("posthoc scoring requires output_dir")
        sequences = _final_max_sequences(output_dir)
        if cohort == "physical":
            return self._score_physical(alias, sequences)
        if cohort == "synthetic":
            return self._score_synthetic(alias, sequences, case=case,
                                         receipt=receipt,
                                         output_sha256=output_sha256)
        raise ValueError("unknown PX cohort")

    def _score_physical(self, alias, sequences):
        if not sequences:
            return {"alias": alias, "outcome": "success", "score": 0.0,
                    "method": PHYSICAL_METHOD,
                    "reference_panel_sha256": self.physical_panel_sha256}
        if not self.physical_panel or not self.physical_panel_sha256:
            raise ValueError("physical scorer is missing reference panel")
        from benchmarks.reference_panel import best_panel_alignment
        best = best_panel_alignment(sequences, self.physical_panel)
        return {"alias": alias, "outcome": "success", "score": best["score"],
                "method": PHYSICAL_METHOD,
                "reference_panel_sha256": self.physical_panel_sha256,
                "best_reference": best["reference"]}

    def _synthetic_inputs(self, case):
        """Resolve per-case truth only from the hash-pinned v6 cohort."""
        if self.synthetic_manifest and self.synthetic_truth:
            manifest = Path(self.synthetic_manifest)
            truth = Path(self.synthetic_truth)
            if not manifest.is_file() or not truth.is_file():
                raise ValueError("synthetic truth inputs are missing")
            data = json.loads(manifest.read_bytes())
            expected = (data.get("sha256") or {}).get(
                "hidden-truth/haplotypes.fasta")
            if (data.get("hidden_truth_file")
                    != "hidden-truth/haplotypes.fasta"
                    or not sched.SHA256.fullmatch(expected or "")
                    or sched.sha256_file(truth) != expected):
                raise ValueError("synthetic truth hash mismatch")
            return manifest, truth
        if case is None:
            return None, None
        cohort = Path(sched.SYNTHETIC_COHORT)
        if sched.sha256_file(cohort) != sched.SYNTHETIC_COHORT_SHA256:
            raise ValueError("synthetic cohort SHA256 changed")
        record = next((item for item in json.loads(cohort.read_bytes())["cases"]
                       if item["id"] == case.source_id), None)
        if record is None:
            raise ValueError("synthetic case is absent from the pinned cohort")
        root = Path(case.r1).resolve().parent.parent
        manifest = root / "manifest.json"
        truth = root / "hidden-truth" / "haplotypes.fasta"
        if not manifest.is_file() or not truth.is_file():
            raise ValueError("synthetic truth inputs are missing")
        # The v6 cohort pins the truth hash; accept neither a rewritten FASTA
        # nor a truth file borrowed from another case.
        expected_truth = record["sha256"]["hidden-truth/haplotypes.fasta"]
        if (not sched.SHA256.fullmatch(expected_truth or "")
                or sched.sha256_file(truth) != expected_truth):
            raise ValueError("synthetic per-case truth hash mismatch")
        manifest_data = json.loads(manifest.read_bytes())
        if (manifest_data.get("sha256") != record["sha256"]
                or manifest_data.get("hidden_truth_file")
                != "hidden-truth/haplotypes.fasta"):
            raise ValueError("synthetic manifest disagrees with pinned cohort")
        return manifest, truth

    def _score_synthetic(self, alias, sequences, case=None, receipt=None,
                         output_sha256=None):
        """Bind even a zero-contig result to the exact frozen truth digest."""
        manifest_path, truth_path = self._synthetic_inputs(case)
        if manifest_path is None or truth_path is None:
            raise ValueError("synthetic scorer is missing truth inputs")
        truth = _manifest_truth(manifest_path)
        if not isinstance(receipt, dict) or not sched.SHA256.fullmatch(
                str(receipt.get("output_sha256") or "")):
            raise ValueError("synthetic scoring requires an immutable receipt")
        if receipt["output_sha256"] != output_sha256:
            raise ValueError("synthetic output hash differs from receipt")
        runner = receipt.get("runner_receipt_sha256")
        if not sched.SHA256.fullmatch(str(runner or "")):
            raise ValueError("synthetic receipt lacks a runner receipt digest")
        if sequences:
            manifest = json.loads(Path(manifest_path).read_bytes())
            from benchmarks.expanded.score import score_sequences
            scored = score_sequences(manifest, truth_path, sequences)
            score, count = scored["score"], scored["reference_count"]
        else:
            # An empty final MAX yields the same zero score as before; truth
            # binding and receipt identity are still mandatory.
            score, count = 0.0, 0
        return {"alias": alias, "outcome": "success", "score": score,
                "method": SYNTHETIC_METHOD, "truth_sha256": truth,
                "output_sha256": receipt["output_sha256"],
                "runner_receipt_sha256": runner,
                "synthetic_abundant_truth_count": count}
