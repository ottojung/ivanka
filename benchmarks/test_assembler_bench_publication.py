"""Public Assembler Bench publishing: original-gate integrity and privacy."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from assembler_bench.site_build import SITE, build, validate_public_site


class PublicAssemblerBenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = json.loads((SITE / "data/runs.json").read_text())

    def test_public_data_is_independently_grounded_and_complete(self):
        reports = self.root["runs"]
        self.assertEqual(len(reports), 2)
        real = next(r for r in reports if r["cohort"] == "real")
        self.assertEqual(real["sample_count"], 198)
        self.assertEqual(len(real["samples"]), 198)
        self.assertEqual({s["alias"] for s in real["samples"]},
                         {f"R{i:03d}" for i in range(1, 199)})
        self.assertEqual(real["status"], "passed-original-only")
        self.assertEqual(real["tools"], ["IVA", "Ivanka"])
        self.assertFalse(real["eligible_for_expanded"])
        for score in real["psi"].values():
            self.assertTrue(score["positive_all_nonnegative"])
            self.assertEqual(score["zeros_nonnegative"], [])
        self.assertAlmostEqual(real["psi"]["runtime"]["psi1"],
                               44.26979640412626, places=8)

    def test_legacy_random_truth_cannot_pretend_to_qualify(self):
        run = next(r for r in self.root["runs"] if r["cohort"] == "synthetic")
        self.assertEqual(run["status"], "ineligible")
        self.assertFalse(run["eligible_for_expanded"])
        self.assertEqual(run["sample_count"], 400)
        self.assertEqual(len(run["families"]), 25)
        self.assertFalse(run["psi"])
        self.assertGreater(sum(sum(f["failures"].values())
                               for f in run["families"]), 0)

    def test_no_private_metadata(self):
        self.assertEqual(validate_public_site(), 2)
        text = json.dumps(self.root)
        for token in ("/workspace/", "/home/", ".fastq", "_R1_001",
                      "MidHCV_S", "V3LOOP_S", "patient_id"):
            self.assertNotIn(token, text)

    def test_reject_unattested_pass_or_failure_hiding(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_site = Path(tmp) / "site"
            import shutil
            shutil.copytree(SITE, copy_site)
            data = copy.deepcopy(self.root)
            data["runs"][1]["status"] = "passed-expanded"
            (copy_site / "data/runs.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "unattested"):
                validate_public_site(copy_site)
            data = copy.deepcopy(self.root)
            data["runs"][0]["samples"][0]["alias"] = "/workspace/secret.fastq"
            (copy_site / "data/runs.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "unsafe"):
                validate_public_site(copy_site)

    def test_github_project_subpath_and_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "_site"
            build(path)
            self.assertTrue((path / "bench/index.html").is_file())
            self.assertTrue((path / "bench/app.js").is_file())
            self.assertTrue((path / "bench/style.css").is_file())
            self.assertTrue((path / "bench/data/runs.json").is_file())
            self.assertIn('href="./bench/"', (path / "index.html").read_text())
            self.assertIn('fetch("./data/runs.json"',
                          (path / "bench/app.js").read_text())
            with self.assertRaises(FileExistsError):
                build(path)


if __name__ == "__main__":
    unittest.main()
