"""Read-only isolated container benchmark parity and provenance contracts."""
import tempfile
import unittest
from pathlib import Path

from expanded.adapters import ASSEMBLERS
from expanded.synthetic import generate_case


class ExpandedIsolatedPodmanTests(unittest.TestCase):
    def test_only_reads_and_output_are_mounted(self):
        from expanded.podman_synthetic import commands
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            for tool in ASSEMBLERS:
                directory = home / tool
                argv, output = commands(tool, "1" * 64, directory,
                                        home / "reads-only-case")
                joined = " ".join(argv)
                self.assertIn("/reads:ro", joined)
                self.assertIn("/outputs:rw", joined)
                self.assertNotIn("hidden-truth", joined)
                self.assertNotIn("--seeds", argv)
                self.assertNotIn("--reference", joined)
                self.assertEqual(argv.count("--reads1"), int(tool != "iva"))
                if tool == "ivanka":
                    self.assertIn("--unsetenv-all", argv)
                    self.assertEqual(argv[-6::2],
                                     ["--reads1", "--reads2", "--output"])
                    self.assertIn("/usr/local/bin/ivanka", argv)
                self.assertTrue(output.is_relative_to(directory))

    def test_truth_scoring_is_excluded_from_reported_assembler_seconds(self):
        from expanded import podman_synthetic
        from unittest.mock import Mock, patch
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp) / "case"
            case.mkdir()
            output = Path(temp) / "result"
            def fake_run(argv, **kwargs):
                (output / "contigs.fasta").write_text(">one\nACGT\n")
                return Mock(returncode=0, stdout="", stderr="")
            with (patch.object(podman_synthetic.subprocess, "run",
                               side_effect=fake_run),
                  patch.object(podman_synthetic, "dominant_truth_score",
                               return_value={"score": 0.8}),
                  patch.object(podman_synthetic.time, "monotonic",
                               side_effect=[10, 14, 20])):
                report = podman_synthetic.attempt(
                    case, output, "ivanka", "a" * 64,
                    {"hidden_truth_file": "hidden-truth/haplotypes.fasta"})
            self.assertEqual(report["status"], "success")
            self.assertEqual(report["seconds"], 4)
            self.assertEqual(report["total_wall_seconds"], 10)
            self.assertEqual(report["score"], 0.8)


    def test_input_provenance_commits_to_both_original_mates(self):
        from expanded import podman_synthetic
        import hashlib
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp) / "case"
            manifest = generate_case(case, "clonal", 0, pairs=20)
            sample = case / "clonal-s000"
            result_root = Path(temp) / "results"
            result_root.mkdir()
            def dummy_attempt(*args, **kwargs):
                return {"status": "failed", "sha256": "a" * 64,
                        "score": 0.0, "seconds": 1.0}
            with patch.object(podman_synthetic, "attempt",
                              side_effect=dummy_attempt):
                result = podman_synthetic.case_run(
                    ("clonal-s000", sample, manifest), result_root,
                    {name: "a" * 64 for name in ASSEMBLERS}, 10)
            combined = (
                manifest["sha256"]["reads/R1.fastq.gz"] +
                manifest["sha256"]["reads/R2.fastq.gz"]
            ).encode()
            self.assertEqual(result["input_sha256"],
                             hashlib.sha256(combined).hexdigest())

if __name__ == "__main__":
    unittest.main()
