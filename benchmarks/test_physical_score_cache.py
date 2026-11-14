"""An in-memory exact-sequence cache cannot alter strict panel scoring."""
import unittest
from unittest.mock import patch

from benchmarks import reference_panel


class PhysicalScoreCacheTests(unittest.TestCase):
    def test_identical_sequences_reuse_independent_score(self):
        calls = []

        def align(sequences, references):
            calls.append(tuple(sequences))
            return {"score": 5.0, "reference": "R", "contig_count": 1,
                    "contig_length": 5}

        with patch.object(reference_panel, "final_max_sequences",
                          side_effect=lambda folder: ["ACGTA"]), patch.object(
                              reference_panel, "best_panel_alignment", side_effect=align):
            cache = {}
            a = reference_panel.panel_acceptance("iva", "ivanka",
                                                 (("R", "ACGTA"),), .9, cache)
            b = reference_panel.panel_acceptance("other_iva", "other_ivanka",
                                                 (("R", "ACGTA"),), .9, cache)
            self.assertEqual(a, b)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(cache), 1)

    def test_distinct_sequences_never_share_score(self):
        calls = []

        def align(sequences, references):
            calls.append(tuple(sequences))
            return {"score": float(len(sequences[0])), "reference": "R",
                    "contig_count": 1, "contig_length": len(sequences[0])}

        with patch.object(reference_panel, "final_max_sequences",
                          side_effect=lambda folder: [folder]), patch.object(
                              reference_panel, "best_panel_alignment", side_effect=align):
            cache = {}
            reference_panel.panel_acceptance("ACGT", "ACGTA", (("R", "ACGTA"),),
                                             score_cache=cache)
            self.assertEqual(calls, [("ACGT",), ("ACGTA",)])
            self.assertEqual(len(cache), 2)


if __name__ == "__main__":
    unittest.main()
