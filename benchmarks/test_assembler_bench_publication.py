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
        from assembler_bench.public_validation import check_public_site
        self.assertEqual(check_public_site(SITE),
                         len(self.root["runs"]) +
                         len(json.loads((SITE / "data/history.json").read_text())["runs"]))
        self.assertEqual({r["cohort"] for r in self.root["runs"]},
                         {"synthetic", "real", "combined"})
        evidence = json.loads((SITE / "data/assembler-evidence.json").read_text())
        for run in self.root["runs"]:
            roster = evidence["cohorts"][run["cohort"]]
            expected = (roster["assemblers"] if "assemblers" in roster else
                        list(dict.fromkeys(
                            tool for part in roster["union_of"]
                            for tool in evidence["cohorts"][part]["assemblers"])))
            self.assertEqual(run["tools"], expected)
            self.assertEqual(len(run["tools"]), len(run["roster"]))
            self.assertEqual(run["status"], "incomplete")
            self.assertEqual(run["sample_count"], len(run["samples"]))
            self.assertEqual(run["micall_fork_provenance"]["status"],
                             "verified")
        real = next(r for r in self.root["runs"] if r["cohort"]=="real")
        self.assertEqual(real["sample_count"], 198)
        self.assertEqual(real["expected_sample_count"], 198)
        self.assertTrue(all(s["alias"].startswith("R") for s in
                            real["samples"]))

    def test_historical_data_is_not_published(self):
        self.assertTrue(all(r.get("status") == "incomplete"
                            and r.get("micall_fork_provenance",{}).get(
                            "status") == "verified"
                            for r in self.root["runs"]))
        self.assertNotIn("legacy-synthetic-v1-20261112",
                         json.dumps(self.root))
        self.assertNotIn("qualif", json.dumps(self.root).lower())

    def test_public_site_works_without_scientific_scoring_packages(self):
        import os
        import subprocess
        import sys
        environment = dict(os.environ)
        environment["PYTHONPATH"] = (
            str(Path(__file__).resolve().parents[1]) + os.pathsep +
            str(Path(__file__).resolve().parents[0]))
        command = [sys.executable, "-S", "-c",
                   ("import sys; from assembler_bench.site_build import "
                    "validate_public_site; assert callable(validate_public_site); "
                    "assert 'Bio' not in sys.modules")]
        process = subprocess.run(command, check=False, env=environment,
                                 text=True, capture_output=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_no_private_metadata(self):
        self.assertEqual(validate_public_site(),
                         len(self.root["runs"]) +
                         len(json.loads((SITE/"data/history.json").read_text())["runs"]))
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
            with self.assertRaisesRegex(ValueError, "unattested|invalid|vocabulary|status"):
                validate_public_site(copy_site)
            data = copy.deepcopy(self.root)
            if data["runs"][0]["samples"]:
                data["runs"][0]["samples"][0]["alias"] = "/workspace/secret.fastq"
            else:
                data["runs"][0]["source_commit"] = "/workspace/secret.fastq"
                data["runs"][2]["source_commit"] = "/workspace/secret.fastq"
            (copy_site / "data/runs.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "invalid sample|unsafe|private|not verified|alias|wrong"):
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
        self.assertEqual(report["expected_cases"], 464)
        self.assertIn(report["cases_measured"], (0, 1))
        self.assertEqual(len(report["tools"]), 7)
        for name,tool in report["tools"].items():
            with self.subTest(tool=name):
                v,den = tool["values"],tool["denominators"]
                if report["cases_measured"] == 0:
                    self.assertEqual(tool["status"], "unmeasured")
                    self.assertTrue(all(x is None for x in v.values()))
                    continue
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
                     'id="subjectSearch"', 'id="diagnosticExplanation"',
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
        from assembler_bench.public_dominance import enrich
        from assembler_bench.site_validation import check_matrices
        runs=json.loads((SITE/"data/runs.json").read_text())
        check_matrices(runs)
        recorded=next(r for r in runs["runs"] if r.get("hxb2_truth_verified"))
        sample=recorded["dominance_matrix"]["metrics"]["alignment"]["ivanka"]["iva"]
        self.assertEqual(sample["status"],"incomplete")
        self.assertIn(sample["subset"]["status"],
                      ("dominates","does-not-dominate","unresolved","no-data"))
        self.assertLessEqual(sample["paired"],recorded["sample_count"])
        corrupted=copy.deepcopy(runs)
        hxb2=next(r for r in corrupted["runs"] if r.get("hxb2_truth_verified"))
        hxb2["dominance_matrix"]["metrics"]["alignment"]["ivanka"]["iva"][
            "subset"]["status"]=("does-not-dominate" if
            sample["subset"]["status"]=="dominates" else "dominates")
        with self.assertRaisesRegex(ValueError,"pairwise PSI matrix"):
            check_matrices(corrupted)
        self.assertEqual(enrich(runs)["runs"][0]["dominance_matrix"][
            "metrics"]["alignment"]["ivanka"]["iva"]["subset"]["status"],
            sample["subset"]["status"])

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
            with self.assertRaisesRegex(ValueError,"density|must be null"):
                validate_public_site(copy_site)

    def test_pr_validation_cannot_cancel_production_pages_deployment(self):
        workflow = (Path(__file__).resolve().parents[1]
                    / ".github/workflows/pages.yml").read_text()
        self.assertIn("format('pr-{0}', github.event.pull_request.number)", workflow)
        self.assertIn("|| 'publish'", workflow)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
                      workflow)
        self.assertNotIn("group: assembler-bench-pages\n", workflow)

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

    def test_public_data_has_no_external_acceptance_vocabulary(self):
        from assembler_bench.public_vocabulary import scan_data_files
        self.assertEqual(scan_data_files(SITE), {})

    def test_cohort_rosters_are_owned_by_evidence_and_combined_is_union(self):
        evidence = json.loads((SITE / "data/assembler-evidence.json").read_text())
        by_cohort = {r["cohort"]: r for r in self.root["runs"]}
        for cohort, run in by_cohort.items():
            declaration = evidence["cohorts"][cohort]
            if "union_of" in declaration:
                expected = []
                for part in declaration["union_of"]:
                    for tool in evidence["cohorts"][part]["assemblers"]:
                        if tool not in expected:
                            expected.append(tool)
            else:
                expected = declaration["assemblers"]
            self.assertEqual(run["tools"], expected)
            self.assertEqual([item["id"] for item in run["roster"]], expected)
        combined = by_cohort["combined"]
        real = set(by_cohort["real"]["tools"])
        synthetic = set(by_cohort["synthetic"]["tools"])
        self.assertEqual(set(combined["tools"]), real | synthetic)

    def test_combined_union_missing_data_is_null_not_fabricated(self):
        combined = next(r for r in self.root["runs"] if r["cohort"] == "combined")
        for sample in combined["samples"]:
            self.assertEqual(set(sample["score"]), set(combined["tools"]))
            self.assertEqual(set(sample["seconds"]), set(combined["tools"]))
            for tool in combined["tools"]:
                score = sample["score"][tool]
                seconds = sample["seconds"][tool]
                if score is not None:
                    self.assertIsInstance(score, (int, float))
                    self.assertGreaterEqual(score, 0)
                if seconds is not None:
                    self.assertIsInstance(seconds, (int, float))
                    self.assertGreater(seconds, 0)
                if score is None:
                    self.assertIn(tool in sample.get("failures", []),
                                  (True, False))
        # A tool measured on only some canonical cases must keep nulls elsewhere.
        any_partial = False
        for tool in combined["tools"]:
            values = [s["score"][tool] for s in combined["samples"]]
            if any(v is not None for v in values) and any(v is None for v in values):
                any_partial = True
                break
        self.assertTrue(any_partial, "expected at least one partially-measured tool")

    def test_all_tools_are_equally_selectable_in_public_ui(self):
        page = (SITE / "index.html").read_text()
        js = (SITE / "app.js").read_text()
        self.assertNotIn('Ivanka wins</option>', page)
        self.assertNotIn('ivanka-only', page.lower())
        self.assertIn("function drawSubjectControls()", js)
        self.assertIn("run.tools", js)
        for run in self.root["runs"]:
            self.assertGreater(len(run["tools"]), 1)
            self.assertEqual(run["dominance_matrix"]["tools"], run["tools"])

    def test_publisher_transformation_scrubs_acceptance_and_keeps_measurements(self):
        from assembler_bench.public_view import merge_evidence, sanitize_report
        evidence = json.loads((SITE / "data/assembler-evidence.json").read_text())
        dirty = copy.deepcopy(self.root)
        dirty["runs"][0]["eligible_for_expanded"] = False
        dirty["runs"][0]["status_reason"] = "passed-original-only"
        dirty["runs"][0]["samples"][0]["qualification_effect"] = "none"
        sanitized = sanitize_report(dirty)
        self.assertNotIn("eligible_for_expanded", json.dumps(sanitized))
        self.assertNotIn("status_reason", json.dumps(sanitized))
        self.assertNotIn("qualification_effect", json.dumps(sanitized))
        merged, joined = merge_evidence(self.root, evidence)
        for run in merged["runs"]:
            self.assertEqual([item["id"] for item in run["roster"]], run["tools"])
            for item in run["roster"]:
                self.assertEqual(set(item),
                                 {"id", "name", "status", "provenance", "cases"})
        self.assertIsInstance(joined, list)

    def test_tampered_joined_measurement_or_roster_fails_validation(self):
        import shutil
        from assembler_bench.public_validation import check_public_site
        with tempfile.TemporaryDirectory() as tmp:
            copy_site = Path(tmp) / "site"
            shutil.copytree(SITE, copy_site)
            report = json.loads((copy_site / "data/runs.json").read_text())
            evidence = json.loads((copy_site / "data/assembler-evidence.json").read_text())
            # Tamper a joined score that has attested evidence.
            cases = {(a["id"], c["canonical_alias"]): c
                     for a in evidence["assemblers"] for c in a.get("cases", [])}
            tampered = False
            for run in report["runs"]:
                for sample in run["samples"]:
                    for tool, score in sample.get("score", {}).items():
                        key = (tool, sample["alias"])
                        if score is not None and key in cases:
                            sample["score"][tool] = score + 999999
                            tampered = True
                            break
                    if tampered:
                        break
                if tampered:
                    break
            self.assertTrue(tampered, "expected at least one attested joined score")
            (copy_site / "data/runs.json").write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                check_public_site(copy_site)

    def test_two_tools_may_share_same_canonical_alias(self):
        from assembler_bench.public_validation import check_joined_measurements
        evidence = {
            "assemblers": [
                {"id": "tool_a", "cases": [
                    {"canonical_alias": "R053", "score": 1.0,
                     "paired_input_sha256": "a" * 64}]},
                {"id": "tool_b", "cases": [
                    {"canonical_alias": "R053", "score": 2.0,
                     "paired_input_sha256": "b" * 64}]},
            ]
        }
        run = {"samples": [
            {"alias": "R053",
             "score": {"tool_a": 1.0, "tool_b": 2.0},
             "seconds": {"tool_a": None, "tool_b": None},
             "measurement_evidence": {
                 "tool_a": {"paired_input_sha256": "a" * 64},
                 "tool_b": {"paired_input_sha256": "b" * 64}}}
        ]}
        proof = check_joined_measurements(run, evidence)
        self.assertEqual(proof["tool_a"], {"R053"})
        self.assertEqual(proof["tool_b"], {"R053"})


if __name__ == "__main__":
    unittest.main()
