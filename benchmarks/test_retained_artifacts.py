"""Retained scientific outputs and metrics must outlive MiCall scratch."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from retained_artifacts import clean_workspace, retain_arm


class RetainedArtifactsTests(unittest.TestCase):
    def test_promotes_nuc_and_destroys_intermediate_files(self):
        with TemporaryDirectory() as d:
            arm = Path(d) / "arm"
            scratch = arm / "scratch"
            scratch.mkdir(parents=True)
            originals = {
                "nuc.csv": "ref,coverage\na,100\n",
                "conseq.csv": "cutoff,sequence\nMAX,ACGT\n",
                "genome_coverage.csv": "coverage\n10\n",
                "read_summary.csv": "reads\n100\n",
                "combined_contigs.fasta": ">c\nACGT\n",
                "remap.csv": "giant temporary remapping data",
                "temp.sam": "giant temporary alignment data",
                "nuc_read_countsa1b2.csv": "giant intermediate counts",
            }
            for name, text in originals.items():
                (scratch / name).write_text(text)
            (scratch / "assembly_tmp").mkdir()
            (scratch / "assembly_tmp" / "joined.fastq").write_text("scratch reads")
            (arm / "micall_internal_timing.json").write_text('{"seconds":3}')
            audit = retain_arm(arm)
            self.assertTrue(audit["removed"])
            self.assertFalse(scratch.exists())
            for name in ("nuc.csv", "conseq.csv", "genome_coverage.csv",
                         "read_summary.csv", "combined_contigs.fasta"):
                self.assertEqual((arm / name).read_text(), originals[name])
            for name in ("remap.csv", "temp.sam", "nuc_read_countsa1b2.csv"):
                self.assertFalse((arm / name).exists())
            self.assertEqual(retain_arm(arm)["removed"], False)
            self.assertTrue((arm / "micall_internal_timing.json").is_file())

    def test_conflicting_final_file_retains_both_versions(self):
        with TemporaryDirectory() as d:
            arm = Path(d)
            (arm / "scratch").mkdir()
            (arm / "scratch" / "nuc.csv").write_text("X")
            (arm / "nuc.csv").write_text("Y")
            audit = retain_arm(arm)
            self.assertTrue(audit["removed"])
            self.assertEqual((arm / "nuc.csv").read_text(), "Y")
            self.assertEqual((arm / "scratch_nuc.csv").read_text(), "X")
            self.assertFalse((arm / "scratch").exists())

    def test_micall_metrics_and_final_max_scoring_unchanged(self):
        from podman_full_micall import score_outputs
        from project_references import final_max_sequences
        with TemporaryDirectory() as d:
            arm = Path(d)
            scratch = arm / "scratch"
            scratch.mkdir()
            (scratch / "conseq.csv").write_text(
                "seed,consensus-percent-cutoff,sequence\na,MAX,ACGT\n")
            (scratch / "nuc.csv").write_text(
                "seed,refseq.nuc.pos,coverage\na,1,17\n")
            (scratch / "genome_coverage.csv").write_text(
                "coverage,coordinates,refseq_nuc_pos\n10,HXB2,1\n")
            original = score_outputs(arm, "ACGT")
            assert original["outputs"]["nuc.csv"]["exists"]
            self.assertEqual(final_max_sequences(arm), ["ACGT"])
            retain_arm(arm)
            self.assertEqual(score_outputs(arm, "ACGT"), original)
            self.assertEqual(final_max_sequences(arm), ["ACGT"])
            self.assertFalse(scratch.exists())

    def test_only_result_arms_are_cleaned(self):
        with TemporaryDirectory() as d:
            workspace = Path(d)
            root = workspace / "ivanka-physical-results"
            arm = root / "123-456" / "case" / "iva"
            (arm / "scratch").mkdir(parents=True)
            (arm / "scratch" / "nuc.csv").write_text("measured")
            (root / "results.jsonl").write_text("{}\n")
            source_scratch = workspace / "micall-code" / "src" / "scratch"
            source_scratch.mkdir(parents=True)
            (source_scratch / "precious").write_text("code")
            self.assertEqual(clean_workspace(workspace)["scratch_directories"], 1)
            self.assertTrue((arm / "scratch").exists())
            report = clean_workspace(workspace, apply=True)
            self.assertEqual(report["retired"], 1)
            self.assertEqual((arm / "nuc.csv").read_text(), "measured")
            self.assertTrue((source_scratch / "precious").is_file())


    def test_large_outputs_removed_but_small_sample_files_survive(self):
        from retained_artifacts import MAX_FILE_BYTES
        with TemporaryDirectory() as d:
            arm = Path(d) / "arm"
            scratch = arm / "scratch"
            scratch.mkdir(parents=True)
            (scratch / "conseq.csv").write_text("MAX,ACGT\n")
            (scratch / "genome_coverage.csv").write_bytes(
                b"C" * (MAX_FILE_BYTES + 1))
            (arm / "big_intermediate.csv").write_bytes(
                b"X" * (MAX_FILE_BYTES + 1))
            (arm / "metrics.json").write_text('{"depth": 42}\n')
            (arm / "execution.json").write_text('{"status":"success"}\n')
            outcome = retain_arm(arm)
            self.assertFalse((arm / "scratch").exists())
            self.assertEqual((arm / "conseq.csv").read_text(), "MAX,ACGT\n")
            self.assertFalse((arm / "genome_coverage.csv").exists())
            self.assertFalse((arm / "big_intermediate.csv").exists())
            self.assertTrue((arm / "metrics.json").exists())
            self.assertTrue((arm / "execution.json").exists())
            self.assertIn("big_intermediate.csv", outcome["discarded_oversize"])

    def test_oversized_log_is_bounded_and_keeps_error_tail(self):
        from retained_artifacts import MAX_FILE_BYTES, LOG_TAIL_BYTES
        with TemporaryDirectory() as d:
            arm = Path(d)
            log = arm / "stderr.log"
            log.write_bytes(b"Q" * MAX_FILE_BYTES + b"LAST FAILURE\n")
            outcome = retain_arm(arm)
            self.assertLess(log.stat().st_size, LOG_TAIL_BYTES + 100)
            self.assertTrue(log.read_bytes().endswith(b"LAST FAILURE\n"))
            self.assertIn("stderr.log", outcome["trimmed_logs"])

if __name__ == "__main__":
    unittest.main()
