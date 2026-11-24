"""Retained scientific outputs and metrics must outlive MiCall scratch."""
import gzip
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from retained_artifacts import (
    RetentionGateError, clean_workspace, content_sha256, logical_name,
    remove_visuals, retain_arm, seal_terminal_evidence, terminal_retire)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


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


class TerminalRetentionTests(unittest.TestCase):
    def test_pdf_and_nested_visuals_removed(self):
        with TemporaryDirectory() as d:
            arm = Path(d) / "arm"
            deep = arm / "diagnostics" / "plots" / "nested"
            deep.mkdir(parents=True)
            for folder in (arm, deep):
                (folder / "figure.pdf").write_text("page")
                (folder / "coverage.svg").write_text("vector")
            (arm / "nuc.csv").write_text("evidence")
            (arm / "failure.log").write_text("failed run")
            outside = Path(d) / "outside.pdf"
            outside.write_text("keep")
            (arm / "linked-dir").symlink_to(Path(d), target_is_directory=True)
            report = remove_visuals(arm)
            self.assertEqual(report["removed_images"], 4)
            self.assertEqual(remove_visuals(arm)["removed_images"], 0)
            self.assertFalse((arm / "figure.pdf").exists())
            self.assertFalse((deep / "figure.pdf").exists())
            self.assertTrue(outside.is_file())
            self.assertTrue((arm / "linked-dir").is_symlink())
            self.assertEqual((arm / "nuc.csv").read_text(), "evidence")
            self.assertEqual((arm / "failure.log").read_text(), "failed run")

    def test_compressed_final_table_is_retained_and_hash_is_logical(self):
        self.assertEqual(logical_name("nuc.csv.zst"), "nuc.csv")
        with TemporaryDirectory() as d:
            arm = Path(d) / "arm"
            scratch = arm / "scratch"
            scratch.mkdir(parents=True)
            plain = "ref,coverage\na,10\n"
            with gzip.open(scratch / "nuc.csv.gz", "wt") as stream:
                stream.write(plain)
            (arm / "podman.stderr.log").write_text("log")
            evidence, _ = seal_terminal_evidence(
                arm, {"metrics": {"outputs": {
                    "nuc.csv": {"sha256": digest(plain)}}}},
                {"input.fastq.gz": "a" * 64})
            report = terminal_retire(
                arm, evidence_path=evidence, container_dead=True,
                source_hashes={"input.fastq.gz": "a" * 64})
            self.assertEqual(report["verified_outputs"], 1)
            self.assertTrue((arm / "nuc.csv.gz").is_file())
            self.assertEqual(content_sha256(arm / "nuc.csv.gz"), digest(plain))
            self.assertFalse(scratch.exists())
            self.assertTrue((arm / "podman.stderr.log").is_file())
            self.assertFalse((arm / "scratch.tar.gz").exists())

    def test_terminal_retire_is_idempotent(self):
        with TemporaryDirectory() as d:
            arm = Path(d)
            scratch = arm / "scratch"
            scratch.mkdir()
            (scratch / "nuc.csv").write_text("measured")
            (arm / "times.json").write_text("{}")
            hashes = {"input.fastq.gz": "b" * 64}
            evidence, _ = seal_terminal_evidence(
                arm, {"metrics": {"outputs": {
                    "nuc.csv": {"sha256": digest("measured")}}}}, hashes)
            first = terminal_retire(arm, evidence_path=evidence,
                                    container_dead=True, source_hashes=hashes)
            self.assertTrue(first["retired"])
            self.assertEqual((arm / "nuc.csv").read_text(), "measured")
            second = terminal_retire(arm, evidence_path=evidence,
                                     container_dead=True, source_hashes=hashes)
            self.assertFalse(second["scratch_present"])
            self.assertFalse(second["retired"])
            self.assertTrue((arm / "times.json").is_file())
            self.assertTrue((arm / "terminal_evidence.json.sha256").is_file())

    def test_fails_closed_without_sealed_evidence_or_dead_container(self):
        with TemporaryDirectory() as d:
            arm = Path(d)
            scratch = arm / "scratch"
            scratch.mkdir()
            (scratch / "nuc.csv").write_text("measured")
            hashes = {"input.fastq.gz": "c" * 64}
            with self.assertRaises(RetentionGateError):
                terminal_retire(arm, evidence_path=arm / "missing.json",
                                container_dead=True, source_hashes=hashes)
            evidence, _ = seal_terminal_evidence(
                arm, {"failure": {"exit_code": 1}}, hashes)
            with self.assertRaises(RetentionGateError):
                terminal_retire(arm, evidence_path=evidence,
                                container_dead=False, source_hashes=hashes)
            with self.assertRaises(RetentionGateError):
                terminal_retire(arm, evidence_path=evidence,
                                container_dead=True,
                                source_hashes={"input.fastq.gz": "d" * 64})
            self.assertTrue(scratch.is_dir())
            self.assertEqual((scratch / "nuc.csv").read_text(), "measured")

    def test_metrics_digest_mismatch_rolls_back_promotion(self):
        with TemporaryDirectory() as d:
            arm = Path(d)
            scratch = arm / "scratch"
            scratch.mkdir()
            (scratch / "nuc.csv").write_text("original")
            hashes = {"input.fastq.gz": "f" * 64}
            evidence, _ = seal_terminal_evidence(
                arm, {"metrics": {"outputs": {
                    "nuc.csv": {"sha256": digest("different")}}}}, hashes)
            with self.assertRaises(RetentionGateError):
                terminal_retire(arm, evidence_path=evidence,
                                container_dead=True, source_hashes=hashes)
            self.assertTrue(scratch.is_dir())
            self.assertEqual((scratch / "nuc.csv").read_text(), "original")
            self.assertFalse((arm / "nuc.csv").exists())

    def test_failed_arm_keeps_logs_but_loses_disposable_scratch_and_visuals(self):
        with TemporaryDirectory() as d:
            arm = Path(d)
            scratch = arm / "scratch"
            scratch.mkdir()
            (scratch / "temp.fastq").write_text("reads")
            (scratch / "align.sam").write_text("alignment")
            (scratch / "nuc.csv").write_text("final evidence")
            (arm / "plot.pdf").write_text("figure")
            (arm / "podman.stderr.log").write_text("traceback")
            hashes = {"input.fastq.gz": "e" * 64}
            evidence, _ = seal_terminal_evidence(
                arm, {"failure": {"exit_code": 124, "error_tail": "timeout"}},
                hashes)
            report = terminal_retire(arm, evidence_path=evidence,
                                     container_dead=True, source_hashes=hashes)
            self.assertTrue(report["retired"])
            self.assertEqual(report["removed_images"], 1)
            self.assertFalse(scratch.exists())
            self.assertFalse((arm / "plot.pdf").exists())
            self.assertEqual((arm / "nuc.csv").read_text(), "final evidence")
            self.assertEqual((arm / "podman.stderr.log").read_text(), "traceback")

    def test_runner_integration_seals_evidence_then_applies_policy(self):
        from podman_full_micall import retire_terminal_arm
        with TemporaryDirectory() as d:
            arm = Path(d)
            scratch = arm / "scratch"
            scratch.mkdir()
            (scratch / "nuc.csv").write_text("final")
            (scratch / "temp.fastq").write_text("reads")
            (arm / "plot.svg").write_text("plot")
            (arm / "podman.stderr.log").write_text("traceback")
            fastq = arm / "input.fastq.gz"
            fastq.write_bytes(b"fastq bytes")
            result = {"image_id": "image-id", "metrics": {
                "outputs": {"nuc.csv": {"sha256": digest("final")}}}}
            report = retire_terminal_arm(
                arm, result, [fastq], "image-id", 0, 1.0,
                arm / "no_timing.json")
            self.assertTrue(report["retired"])
            self.assertEqual(report["verified_outputs"], 1)
            self.assertEqual(report["removed_images"], 1)
            self.assertEqual((arm / "nuc.csv").read_text(), "final")
            self.assertFalse(scratch.exists())
            self.assertTrue((arm / "terminal_evidence.json").is_file())
            self.assertTrue((arm / "terminal_evidence.json.sha256").is_file())
            self.assertEqual((arm / "podman.stderr.log").read_text(),
                             "traceback")

    def test_runner_integration_failed_arm_keeps_evidence(self):
        from podman_full_micall import retire_terminal_arm
        with TemporaryDirectory() as d:
            arm = Path(d)
            scratch = arm / "scratch"
            scratch.mkdir()
            (scratch / "nuc.csv").write_text("final")
            (arm / "podman.stderr.log").write_text("traceback")
            fastq = arm / "input.fastq.gz"
            fastq.write_bytes(b"fastq bytes")
            report = retire_terminal_arm(
                arm, {"image_id": "image-id", "error": "timeout"},
                [fastq], "image-id", 124, 2400.0, arm / "no_timing.json")
            self.assertTrue(report["retired"])
            self.assertEqual((arm / "nuc.csv").read_text(), "final")
            self.assertEqual((arm / "podman.stderr.log").read_text(),
                             "traceback")
            self.assertFalse(scratch.exists())

    def test_scratch_symlink_is_not_followed(self):
        with TemporaryDirectory() as d:
            arm = Path(d) / "arm"
            scratch = arm / "scratch"
            scratch.mkdir(parents=True)
            outside = Path(d) / "escape.csv"
            outside.write_text("precious")
            (scratch / "linked.csv").symlink_to(outside)
            retain_arm(arm)
            self.assertTrue(outside.is_file())
            self.assertEqual(outside.read_text(), "precious")
            self.assertFalse((arm / "linked.csv").exists())


if __name__ == "__main__":
    unittest.main()
