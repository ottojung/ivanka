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
        from assembler_bench.current_validation import EXPECTED
        self.assertEqual({r["id"] for r in self.root["runs"]}, EXPECTED)
        self.assertEqual({r["cohort"] for r in self.root["runs"]},
                         {"synthetic", "real", "combined"})
        for run in self.root["runs"]:
            self.assertEqual(len(run["tools"]), 7)
            self.assertEqual(run["status"], "incomplete")
            self.assertEqual(run["sample_count"], len(run["samples"]))
            self.assertFalse(run["eligible_for_expanded"])
            self.assertEqual(run["micall_fork_provenance"]["status"],
                             "verified")
        real = next(r for r in self.root["runs"] if r["cohort"]=="real")
        self.assertLessEqual(real["sample_count"],198)
        self.assertEqual(real["expected_sample_count"],198)
        self.assertTrue(all(s["alias"].startswith("R") for s in
                            real["samples"]))
        self.assertGreater(real["sample_count"],0)

    def test_historical_data_is_not_published(self):
        self.assertTrue(all(r.get("status") != "ineligible"
                            and r.get("micall_fork_provenance",{}).get(
                            "status") == "verified"
                            for r in self.root["runs"]))
        self.assertNotIn("legacy-synthetic-v1-20261112",
                         json.dumps(self.root))

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
            with self.assertRaisesRegex(ValueError, "invalid sample|unsafe"):
                validate_public_site(copy_site)

    def test_directed_all_tool_dominance_matrix_is_fail_closed(self):
        for run in self.root["runs"]:
            matrix = run["dominance_matrix"]
            self.assertEqual(matrix["tools"],run["tools"])
            for metric in ("alignment","runtime","joint"):
                for a in run["tools"]:
                    for b in run["tools"]:
                        result=matrix["metrics"][metric][a][b]
                        self.assertEqual(result["status"],
                            "self" if a==b else "incomplete")
            self.assertEqual(run["micall_fork_provenance"]["status"],
                             "verified")

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

    def test_partial_psi_proof_is_independently_recomputed(self):
        import copy
        from assembler_bench.site_validation import check_matrices
        from assembler_bench.public_dominance import enrich
        runs=json.loads((SITE/"data/runs.json").read_text())
        check_matrices(runs)
        recorded=next(r for r in runs["runs"] if r.get("hxb2_truth_verified"))
        sample=recorded["dominance_matrix"]["metrics"]["alignment"]["ivanka"]["iva"]
        self.assertEqual(sample["status"],"incomplete")
        self.assertEqual(sample["subset"]["status"],"dominates")
        self.assertTrue(sample["subset"]["proof"]["positive_all_nonnegative"])
        self.assertEqual(sample["paired"],recorded["sample_count"])
        corrupted=copy.deepcopy(runs)
        hxb2=next(r for r in corrupted["runs"] if r.get("hxb2_truth_verified"))
        hxb2["dominance_matrix"]["metrics"]["alignment"]["ivanka"]["iva"][
            "subset"]["status"]="does-not-dominate"
        with self.assertRaisesRegex(ValueError,"pairwise PSI matrix"):
            check_matrices(corrupted)
        self.assertEqual(enrich(runs)["runs"][0]["dominance_matrix"][
            "metrics"]["alignment"]["ivanka"]["iva"]["subset"]["status"],
            "dominates")

    def test_tampering_with_matrix_or_density_fails_publication(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            copy_site=Path(tmp)/"site"
            shutil.copytree(SITE,copy_site)
            data=copy.deepcopy(self.root)
            data["runs"][0]["dominance_matrix"]["metrics"]["joint"][
                "iva"]["ivanka"]["status"]="dominates"
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
