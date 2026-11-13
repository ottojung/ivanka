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
        self.assertGreaterEqual(len(reports), 3)
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
        self.assertEqual(validate_public_site(), len(self.root["runs"]))
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

    def test_directed_all_tool_dominance_matrix_is_fail_closed(self):
        real = next(r for r in self.root["runs"] if r["cohort"]=="real")
        grid = real["dominance_matrix"]["metrics"]
        for name in ("alignment", "runtime", "joint"):
            self.assertEqual(grid[name]["Ivanka"]["IVA"]["status"],
                             "dominates")
            self.assertEqual(grid[name]["IVA"]["Ivanka"]["status"],
                             "does-not-dominate")
            self.assertEqual(grid[name]["IVA"]["IVA"]["status"], "self")
        self.assertEqual(grid["alignment"]["Ivanka"]["IVA"]["proof"]
                         ["zeros_nonnegative"], [])
        for run in self.root["runs"]:
            matrix = run["dominance_matrix"]
            self.assertEqual(matrix["tools"], run["tools"])
            if run["cohort"]=="synthetic":
                for metric in ("alignment", "runtime", "joint"):
                    for a in run["tools"]:
                        for b in run["tools"]:
                            expected = "self" if a==b else "incomplete"
                            self.assertEqual(matrix["metrics"][metric][a][b]
                                             ["status"], expected)
            self.assertEqual(run["micall_fork_provenance"]["status"],
                             "historical-unverified")

    def test_seven_tool_soft_clip_counts_and_densities_are_reviewable(self):
        source = SITE / "data/mapping-diagnostics.json"
        report = json.loads(source.read_text())
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["expected_cases"], 400)
        self.assertEqual(report["cases_measured"], 1)
        self.assertEqual(len(report["tools"]), 7)
        for name,tool in report["tools"].items():
            with self.subTest(tool=name):
                v,den = tool["values"],tool["denominators"]
                self.assertEqual(tool["status"],"measured")
                self.assertGreater(den["mapped_primary_records"],0)
                self.assertAlmostEqual(
                    v["clipped_read_fraction"],
                    v["soft_clipped_reads"]/den["mapped_primary_records"])
                self.assertAlmostEqual(
                    v["soft_clipped_bases_per_1000_read_bases"],
                    1000*v["soft_clipped_bases"]/
                    den["mapped_primary_read_bases"])
                self.assertIsNotNone(v["nuc_soft_clips_count"])
                self.assertIn("source_sha256",tool)
        page=(SITE/"index.html").read_text()
        js=(SITE/"app.js").read_text()
        for text in ('id="dominanceMatrix"', 'id="dominanceSubjects"',
                     'id="subjectSearch"', 'id="diagnosticMatrix"',
                     'id="diagnosticExplanation"', 'id="diagnosticChart"',
                     'id="firstTool"'):
            self.assertIn(text,page)
        self.assertIn("function drawDominance()",js)
        self.assertIn("function drawDiagnostics()",js)
        self.assertIn("function drawSubjectControls()",js)
        self.assertIn("definition.description",js)
        self.assertIn("info.denominator",js)
        self.assertIn("BenchRanks.summary(",js)
        self.assertIn("BenchRanks.pairs(",js)
        self.assertNotIn('id="dominanceMetric"',page)
        self.assertNotIn('Ivanka wins</option>',page)
        definitions=report["metric_catalog"]
        for name, metadata in definitions.items():
            self.assertGreater(len(metadata["description"]), 35, name)
            self.assertGreater(len(metadata["denominator"]), 15, name)
            self.assertIn(metadata["suggested_direction"],
                          ("higher","lower","unspecified"))

    def test_tampering_with_matrix_or_density_fails_publication(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            copy_site=Path(tmp)/"site"
            shutil.copytree(SITE,copy_site)
            data=copy.deepcopy(self.root)
            data["runs"][0]["dominance_matrix"]["metrics"]["joint"][
                "IVA"]["Ivanka"]["status"]="dominates"
            (copy_site/"data/runs.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"pairwise"):
                validate_public_site(copy_site)
            (copy_site/"data/runs.json").write_text(json.dumps(self.root))
            metrics=json.loads((copy_site/"data/mapping-diagnostics.json").read_text())
            metrics["tools"]["iva"]["values"][
                "soft_clipped_bases_per_1000_read_bases"]=0
            (copy_site/"data/mapping-diagnostics.json").write_text(
                json.dumps(metrics))
            with self.assertRaisesRegex(ValueError,"density"):
                validate_public_site(copy_site)

    def test_github_project_subpath_and_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "_site"
            build(path)
            self.assertTrue((path / "bench/index.html").is_file())
            self.assertTrue((path / "bench/app.js").is_file())
            self.assertTrue((path / "bench/subjects.js").is_file())
            self.assertTrue((path / "bench/rankings.js").is_file())
            self.assertTrue((path / "bench/style.css").is_file())
            self.assertTrue((path / "bench/data/runs.json").is_file())
            self.assertTrue((path / "bench/data/mapping-diagnostics.json").is_file())
            self.assertIn('href="./bench/"', (path / "index.html").read_text())
            self.assertIn('fetch("./data/runs.json"',
                          (path / "bench/app.js").read_text())
            with self.assertRaises(FileExistsError):
                build(path)


if __name__ == "__main__":
    unittest.main()
