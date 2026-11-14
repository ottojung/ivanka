"""No result-journal score is authoritative without recomputing MiCall output."""
import unittest
from unittest.mock import patch
from benchmarks.expanded.strict_fork_physical198_scoring import authenticate_scores


class IndependentScoringTests(unittest.TestCase):
    def test_rejects_score_tampering_and_wrong_panel(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "hxb2.fasta").write_text(">HXB2\nACGT\n")
            expected = {"method": "best_final_max_contig_local_alignment_over_reference_panel",
                        "iva_score": 100.0, "ivanka_score": 95.0, "pass": True}
            records = {"s": {"best_contig_acceptance": dict(expected),
                             "iva": {"artifact_dir": "iva"},
                             "ivanka": {"artifact_dir": "ivanka"}}}
            with patch("benchmarks.expanded.strict_fork_physical198_scoring.load_micall_projects",
                       return_value=({"regions": {}}, "hash")), patch(
                       "benchmarks.expanded.strict_fork_physical198_scoring.build_reference_panel",
                       return_value=tuple(range(33))), patch(
                       "benchmarks.expanded.strict_fork_physical198_scoring.panel_sha256",
                       return_value="panel"), patch(
                       "benchmarks.expanded.strict_fork_physical198_scoring.panel_acceptance",
                       return_value=expected) as score:
                self.assertEqual(authenticate_scores(records, source, {"iva": "image"},
                                                     "panel"), "panel")
                score.assert_called_once_with("iva", "ivanka", tuple(range(33)),
                                              min_ratio=.90, score_cache={})
                records["s"]["best_contig_acceptance"]["ivanka_score"] = 99.0
                with self.assertRaisesRegex(ValueError, "disagrees"):
                    authenticate_scores(records, source, {"iva": "image"}, "panel")
                with self.assertRaisesRegex(ValueError, "panel differs"):
                    authenticate_scores(records, source, {"iva": "image"}, "other")


if __name__ == "__main__":
    unittest.main()
