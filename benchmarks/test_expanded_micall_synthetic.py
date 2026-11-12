"""Invariant checks: only genuine MiCall results can qualify synthetic data."""
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from expanded import micall_synthetic


class MiCallSyntheticTests(unittest.TestCase):
    def test_every_assembler_enters_the_same_pipeline_and_not_hidden_truth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample = root / "case"
            for tool in ("ivanka", "iva", "haploflow", "megahit",
                         "abyss", "spades", "velvet"):
                argv = micall_synthetic.command(tool, "a" * 64, sample,
                                                root / "results")
                self.assertEqual(argv[-7:], [
                    "--denovo", "--keep_scratch",
                    "--bad_cycles_csv", "/results/bad_cycles.csv",
                    "--project_code", "NFLHIVDNA", "--all_projects",
                ])
                self.assertEqual(argv.count("micall"), 1)
                self.assertIn("analyze", argv)
                self.assertIn("sample", argv)
                self.assertIn("/bench/reads/R1.fastq.gz", argv)
                self.assertIn("/bench/reads/R2.fastq.gz", argv)
                mounts = [argv[i+1] for i,v in enumerate(argv[:-1]) if v=="-v"]
                self.assertEqual(len(mounts), 3)
                self.assertTrue(any(str(sample / "reads") in m and
                                    m.endswith("/bench/reads:ro")
                                    for m in mounts))
                self.assertNotIn("hidden-truth", " ".join(argv))
                self.assertNotIn("--seeds", argv)
                self.assertNotIn("--reference", argv)
                self.assertIn("--all_projects", argv)
                self.assertIn("--project_code", argv)
                self.assertNotIn("IVANKA_BENCH", " ".join(argv))
                self.assertEqual(argv[argv.index("--project_code")+1],
                                 "NFLHIVDNA")

    def test_monotonic_timing_cannot_be_fabricated_from_host_wall_time(self):
        with tempfile.TemporaryDirectory() as folder:
            clock = Path(folder) / "micall_internal_timing.json"
            with self.assertRaisesRegex(ValueError, "missing"):
                micall_synthetic.timed_result(clock, 0, 2, timeout=1800)
            clock.write_text(json.dumps({
                "timing_origin": micall_synthetic.ORIGIN,
                "seconds": 2.5, "exit_code": 0}))
            self.assertEqual(
                micall_synthetic.timed_result(clock, 0, 3, timeout=1800), 2.5)
            for bad in (float("inf"), 0, -1, 1850):
                clock.write_text(json.dumps({
                    "timing_origin": micall_synthetic.ORIGIN,
                    "seconds": bad, "exit_code": 0}))
                with self.assertRaisesRegex(ValueError, "invalid"):
                    micall_synthetic.timed_result(clock, 0, 3, timeout=1800)
            with self.assertRaisesRegex(ValueError, "container failed"):
                micall_synthetic.timed_result(clock, 2, 3, timeout=1800)

    def test_fail_closed_when_micall_success_lacks_final_consensus(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            case=root/"case"
            case.mkdir()
            dest=root/"result"
            with patch.object(micall_synthetic.subprocess, "run",
                              return_value=Mock(returncode=0,
                                                stdout="", stderr="")), patch.object(
                              micall_synthetic, "timed_result", return_value=2.5):
                result=micall_synthetic.attempt(case,dest,"ivanka","a"*64,{"hidden_truth_file": "hidden-truth/haplotypes.fasta"})
            self.assertEqual(result["status"],"failed")
            self.assertIn("missing final MiCall", result["error"])
            self.assertNotIn("seconds", result["truth_diagnostics"]
                             if "truth_diagnostics" in result else {})

    def test_only_hxb2_v2_cohorts_are_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"cohort.json").write_text(json.dumps({
                "schema": "ivanka.expanded.cohort.v1", "samples":400}))
            with self.assertRaisesRegex(ValueError, "HXB2"):
                micall_synthetic.cohort_rows(root)


if __name__ == "__main__":
    unittest.main()
