from pathlib import Path
import tempfile
import unittest

from runtime_decomposition import cohort, parse_stages, signed_psi, summarize


class RuntimeDecompositionTests(unittest.TestCase):
    def test_stage_parser(self):
        log = ("Ivanka wrote 2 contigs in 4.5s\n"
               "2026-10-31 12:00:00,000[INFO] Running remap\n"
               "2026-10-31 12:00:03,250[INFO] Running sam2aln\n")
        self.assertEqual(parse_stages(log), (4.5, 3.25))
        with self.assertRaises(ValueError):
            parse_stages("Ivanka wrote 2 contigs in 4.5s")

    def test_signed_power_psi_including_ties(self):
        psi = signed_psi([3, -2, 0])
        self.assertEqual(psi["faster"], 1)
        self.assertEqual(psi["slower"], 1)
        self.assertEqual(psi["ties"], 1)
        self.assertAlmostEqual(psi["psi0"], 0)
        self.assertAlmostEqual(psi["psi1"], 1/3)
        self.assertAlmostEqual(psi["psi2"], 5/3)

    def test_diagnostic_zero_assembly_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            logpath = Path(tmp) / "podman.stderr.log"
            logpath.write_text("Ivanka wrote 2 contigs in 4.0s\n"
                               "2026-10-31 12:00:00,000 Running remap\n"
                               "2026-10-31 12:00:08,000 Running sam2aln\n")
            record = {"sample": "example-MidHCV", "status": "finished",
                      "failed": False, "iva": {"seconds": 10},
                      "ivanka": {"seconds": 15, "artifact_dir": tmp}}
            rows = cohort([record], 1)
            self.assertEqual(rows[0]["delta"], -5)
            self.assertEqual(rows[0]["zero_assembler_delta"], -1)
            report = summarize(rows)
            self.assertIs(report["formal_qualification"], False)
            self.assertEqual(report["groups"]["all"]["remap_total_seconds"], 8)
            self.assertEqual(report["groups"]["all"]["observed_runtime"]["faster"], 0)
            self.assertEqual(report["groups"]["all"]["zero_assembly_counterfactual"]["faster"], 0)
            with self.assertRaisesRegex(ValueError, "duplicated"):
                cohort([record, record], 2)
            with self.assertRaisesRegex(ValueError, "Expected 2"):
                cohort([record], 2)
            record["status"] = "started"
            with self.assertRaisesRegex(ValueError, "Unfinished"):
                cohort([record], 1)

    def test_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            signed_psi([float("nan")])
        with self.assertRaises(ValueError):
            signed_psi([])


if __name__ == "__main__":
    unittest.main()
