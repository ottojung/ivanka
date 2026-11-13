"""Retained source-pinned executions survive a scoring or image-set change."""
import copy
import json
import unittest

from assembler_bench.history_validation import check_history
from assembler_bench.site_build import SITE


class ExecutionArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = json.loads((SITE/"data/runs.json").read_text())
        cls.history = json.loads((SITE/"data/history.json").read_text())

    def test_all_five_retained_experiments_are_selectable(self):
        expected = {
            "hxb2-prior-retained": 52,
            "real-prior-ivanka-retained": 198,
            "real-prior-haploflow-retained": 72,
            "hxb2-dedicated-retained": 10,
            "real-dedicated-ivanka-retained": 72,
        }
        self.assertEqual({r["id"]:r["sample_count"] for r in
                          self.history["runs"]}, expected)
        self.assertEqual(check_history(
            self.history,[r["id"] for r in self.current["runs"]]), 5)
        for run in self.history["runs"]:
            self.assertFalse(run["eligible_for_expanded"])
            self.assertEqual(run["score_origin"],
                             "micall_final_max_reference_panel_v1")
            self.assertEqual(run["micall_fork_provenance"]["status"], "archived")
            self.assertEqual(run["expected_sample_count"],
                             400 if run["cohort"] == "synthetic" else 198)

    def test_complete_original_physical_comparison_is_retained(self):
        run=next(r for r in self.history["runs"]
                 if r["id"]=="real-prior-ivanka-retained")
        self.assertEqual(sum(s["score"]["ivanka"] is not None
                             for s in run["samples"]),198)
        self.assertEqual(sum(s["score"]["iva"] is not None
                             for s in run["samples"]),198)
        self.assertEqual(len({s["alias"] for s in run["samples"]}),198)
        self.assertEqual(sum(bool(s["failures"]) for s in run["samples"]),0)

    def test_retained_synthetic_failures_are_not_fabricated_wins(self):
        run=next(r for r in self.history["runs"]
                 if r["id"]=="hxb2-prior-retained")
        self.assertEqual(sum("abyss" in s["failures"] for s in run["samples"]),18)
        self.assertTrue(any(s["score"]["ivanka"]>1
                            for s in run["samples"]
                            if s["score"]["ivanka"] is not None))
        for row in run["samples"]:
            for name in row["failures"]:
                self.assertIsNone(row["score"][name])
                self.assertIsNone(row["seconds"][name])

    def test_changed_archive_score_or_provenance_is_rejected(self):
        original=self.history
        current=[r["id"] for r in self.current["runs"]]
        changed=copy.deepcopy(original)
        changed["runs"][0]["samples"][0]["score"]["iva"]=float("nan")
        with self.assertRaisesRegex(ValueError,"invalid"):
            check_history(changed,current)
        changed=copy.deepcopy(original)
        changed["runs"][1]["images"]["iva"]="0"*64
        with self.assertRaisesRegex(ValueError,"mismatch"):
            check_history(changed,current)
        changed=copy.deepcopy(original)
        changed["runs"][1]["samples"][0]["alias"]="patient-S42"
        with self.assertRaisesRegex(ValueError,"alias"):
            check_history(changed,current)

    def test_matrix_before_individual_sample_list(self):
        page=(SITE/"index.html").read_text()
        offsets=[page.index('class="'+section+'"') for section in
                 ("compare","dominance","samples","provenance")]
        self.assertEqual(offsets,sorted(offsets))
        self.assertIn("03 / ALL-VERSUS-ALL",page)
        self.assertIn("04 / CASE-LEVEL VALUES",page)
        script=(SITE/"app.js").read_text()
        self.assertIn('fetch("./data/history.json"',script)
        self.assertIn('state.data.runs.push(...history.runs)',script)


if __name__ == "__main__":
    unittest.main()
