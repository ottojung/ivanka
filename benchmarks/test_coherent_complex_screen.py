"""Hermetic 16-case complex-mixture screen tests without private FASTQ data."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from expanded import coherent_complex_screen as screen


def cases():
    return [
        (f"complex_mixture-s{i:03d}", Path(f"/fake/complex_mixture-s{i:03d}"),
         {"family": screen.FAMILY, "pairs": 10000,
          "nominal_fractions": [0.65, 0.25, 0.08, 0.02],
          "sampled_haplotype_pairs": [6500, 2500, 800, 200],
          "chimeric_mates": 0, "contamination_pairs": 0})
        for i in range(16)
    ]


class ComplexScreenTests(unittest.TestCase):
    def test_all_sixteen_identities_including_worst_regressions(self):
        with patch.object(screen, "cohort_rows", return_value=cases()):
            selected = screen.inputs()
        self.assertEqual(len(selected), 16)
        for name in ("complex_mixture-s011", "complex_mixture-s006",
                     "complex_mixture-s015"):
            self.assertIn(name, {row[0] for row in selected})

    def test_missing_or_duplicate_identity_fails(self):
        with patch.object(screen, "cohort_rows", return_value=cases()[:-1]):
            with self.assertRaisesRegex(ValueError, "all 16"):
                screen.inputs()
        repeated = cases()
        repeated[-1] = repeated[0]
        with patch.object(screen, "cohort_rows", return_value=repeated):
            with self.assertRaisesRegex(ValueError, "all 16"):
                screen.inputs()

    def test_four_way_majority_and_technical_metadata(self):
        meta = cases()[0][2]
        note = screen.dominance_note(meta)
        self.assertEqual(note["fixed_truth_index"], 0)
        self.assertEqual(note["observed_pair_majority_index"], 0)
        self.assertFalse(note["fixed_truth_not_observed_majority"])
        self.assertTrue(note["acceptance_score_unchanged"])
        self.assertEqual(note["sampled_haplotype_pairs"], [6500, 2500, 800, 200])

    def test_technical_and_count_inconsistencies_fail_closed(self):
        meta = dict(cases()[0][2])
        meta["sampled_haplotype_pairs"] = [6500, 2500, 800, 199]
        with self.assertRaisesRegex(ValueError, "authentic"):
            screen.dominance_note(meta)
        meta["sampled_haplotype_pairs"] = [6500, 2500, 800, -1]
        with self.assertRaisesRegex(ValueError, "authentic"):
            screen.dominance_note(meta)
        meta["sampled_haplotype_pairs"] = [6500, 2500, 800, True]
        with self.assertRaisesRegex(ValueError, "authentic"):
            screen.dominance_note(meta)

    def test_fixed_truth_mismatch_is_only_diagnostic(self):
        meta = dict(cases()[0][2])
        meta["sampled_haplotype_pairs"] = [3000, 6000, 800, 200]
        note = screen.dominance_note(meta)
        self.assertTrue(note["fixed_truth_not_observed_majority"])
        self.assertEqual(note["fixed_truth_index"], 0)
        self.assertTrue(note["acceptance_score_unchanged"])

    def test_freeze_checks_parent_source_before_touching_inputs(self):
        with patch.object(screen.parent, "freeze",
                          return_value={"benchmark_runner_commit": "wrong"}):
            with self.assertRaisesRegex(ValueError, "source changed"):
                screen.freeze()

    def test_no_truth_file_can_enter_new_case_manifest(self):
        parent = {
            "benchmark_runner_commit": screen.PARENT_COMMIT,
            "source_pilot_manifest_sha256": "p",
            "cohort_sha256": "c",
            "truth_validation": {"valid": True},
        }
        with patch.object(screen.parent, "freeze", return_value=parent), \
             patch.object(screen, "inputs", return_value=cases()), \
             patch.object(screen.parent, "sha", return_value="h") as hashed, \
             patch.object(screen.parent, "commit", return_value="commit"):
            frozen = screen.freeze()
        self.assertEqual(len(frozen["cases"]), 16)
        self.assertFalse(frozen["qualified"])
        self.assertFalse(frozen["release_qualified"])
        observed = [str(call.args[0]) for call in hashed.call_args_list]
        self.assertFalse(any("/truth" in path for path in observed))
        self.assertEqual(frozen["image_sha256"], screen.parent.IMAGE)

    def test_changed_run_manifest_rejects_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "run_manifest.json").write_text(json.dumps({"changed": True}))
            with patch.object(screen, "freeze", return_value={"qualified": False}):
                with self.assertRaisesRegex(ValueError, "resume mismatch"):
                    screen.run(root)


if __name__ == "__main__":
    unittest.main()
