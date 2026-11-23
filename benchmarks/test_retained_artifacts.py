"""Retained scientific outputs and metrics must outlive MiCall scratch."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from retained_artifacts import clean_workspace, retain_arm, remove_visuals


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

    def test_generated_images_removed_without_touching_scientific_data(self):
        with TemporaryDirectory() as d:
            arm = Path(d) / "arm"
            subdir = arm / "diagnostics"
            subdir.mkdir(parents=True)
            for name in ("alignment.png", "coverage.svg", "plot.webp"):
                (subdir / name).write_text("plot")
            for name in ("nuc.csv", "conseq.fasta", "metrics.json"):
                (arm / name).write_text("evidence")
            outside = Path(d) / "outside.png"
            outside.write_text("outside")
            (arm / "linked.png").symlink_to(outside)
            (arm / "linked-dir").symlink_to(Path(d), target_is_directory=True)
            report = remove_visuals(arm)
            self.assertEqual(report["removed_images"], 3)
            self.assertEqual(remove_visuals(arm)["removed_images"], 0)
            self.assertTrue(outside.is_file())
            self.assertTrue((arm / "linked.png").is_symlink())
            for name in ("nuc.csv", "conseq.fasta", "metrics.json"):
                self.assertEqual((arm / name).read_text(), "evidence")

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


if __name__ == "__main__":
    unittest.main()
