"""Retained scientific outputs and metrics must outlive MiCall scratch."""
import gzip
import hashlib
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import retained_artifacts
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
                "alignments.csv": "intermediate reads",
                "unstitched_alignments_unmerged.csv.gz": "intermediate reads",
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
            for name in ("remap.csv", "temp.sam", "nuc_read_countsa1b2.csv",
                         "alignments.csv", "unstitched_alignments_unmerged.csv.gz"):
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

    def test_workspace_inventory_cannot_infer_terminal_liveness(self):
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
            self.assertEqual(report["retired"], 0)
            self.assertTrue(report["errors"])
            self.assertEqual((arm / "scratch" / "nuc.csv").read_text(), "measured")
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

    def test_collated_scored_output_is_verified_before_deletion(self):
        for state in ("changed", "missing", "symlink", "ambiguous"):
            with self.subTest(state=state), TemporaryDirectory() as d:
                arm = Path(d) / "arm"
                scratch = arm / "scratch"
                scratch.mkdir(parents=True)
                (scratch / "temp.fastq").write_text("reads")
                final = arm / "nuc.csv"
                if state == "changed":
                    final.write_text("different")
                elif state == "symlink":
                    outside = Path(d) / "outside.csv"
                    outside.write_text("measured")
                    final.symlink_to(outside)
                elif state == "ambiguous":
                    final.write_text("measured")
                    with gzip.open(arm / "nuc.csv.gz", "wt") as stream:
                        stream.write("measured")
                hashes = {"input.fastq.gz": "c" * 64}
                evidence, _ = seal_terminal_evidence(
                    arm, {"metrics": {"outputs": {
                        "nuc.csv": {"sha256": digest("measured")}}}}, hashes)
                with self.assertRaises((RetentionGateError, ValueError)):
                    terminal_retire(arm, evidence_path=evidence,
                                    container_dead=True, source_hashes=hashes)
                self.assertTrue((scratch / "temp.fastq").is_file())

    def test_native_assembly_evidence_kept_without_nested_scratch(self):
        with TemporaryDirectory() as d:
            arm = Path(d)
            work = arm / "scratch" / "assembly_123"
            work.mkdir(parents=True)
            for name in ("contigs.fasta", "seeds.fasta", "assembler.log", "temp.fastq"):
                (work / name).write_text(name)
            (arm / "scratch" / "pipeline.log").write_text("failure detail")
            hashes = {"input.fastq.gz": "c" * 64}
            evidence, _ = seal_terminal_evidence(
                arm, {"failure": {"exit_code": 1}}, hashes)
            terminal_retire(arm, evidence_path=evidence,
                            container_dead=True, source_hashes=hashes)
            self.assertFalse((arm / "scratch").exists())
            for name in ("contigs.fasta", "seeds.fasta", "assembler.log"):
                self.assertEqual((arm / "assembly_123" / name).read_text(), name)
            self.assertFalse((arm / "assembly_123" / "temp.fastq").exists())
            self.assertEqual((arm / "pipeline.log").read_text(), "failure detail")

    def test_seal_rejects_symlinked_sidecar_and_temp(self):
        for name in ("terminal_evidence.json.sha256", ".terminal_evidence.json.part"):
            with self.subTest(name=name), TemporaryDirectory() as d:
                arm = Path(d) / "arm"
                arm.mkdir()
                outside = Path(d) / "precious"
                outside.write_text("unchanged")
                (arm / name).symlink_to(outside)
                with self.assertRaises(ValueError):
                    seal_terminal_evidence(arm, {"failure": {"exit_code": 1}},
                                           {"input.fastq.gz": "c" * 64})
                self.assertEqual(outside.read_text(), "unchanged")

    def test_source_hashes_required_for_terminal_retirement(self):
        with TemporaryDirectory() as d:
            arm = Path(d)
            (arm / "scratch").mkdir()
            evidence, _ = seal_terminal_evidence(
                arm, {"failure": {"exit_code": 1}}, {"input.fastq.gz": "c" * 64})
            with self.assertRaises(RetentionGateError):
                terminal_retire(arm, evidence_path=evidence, container_dead=True)
            self.assertTrue((arm / "scratch").is_dir())

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
                arm / "no_timing.json", container_dead=True)
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
                [fastq], "image-id", 124, 2400.0, arm / "no_timing.json",
                container_dead=True)
            self.assertTrue(report["retired"])
            self.assertEqual((arm / "nuc.csv").read_text(), "final")
            self.assertEqual((arm / "podman.stderr.log").read_text(),
                             "traceback")
            self.assertFalse(scratch.exists())

    def test_runner_integration_post_seal_source_change_fails_closed(self):
        import podman_full_micall
        from podman_full_micall import retire_terminal_arm
        real_seal = podman_full_micall.seal_terminal_evidence

        def seal_then_mutate(*args, **kwargs):
            result = real_seal(*args, **kwargs)
            fastq.write_bytes(b"mutated after seal")
            return result

        with TemporaryDirectory() as d:
            arm = Path(d)
            scratch = arm / "scratch"
            scratch.mkdir()
            (scratch / "nuc.csv").write_text("final")
            fastq = arm / "input.fastq.gz"
            fastq.write_bytes(b"fastq bytes")
            original = podman_full_micall.seal_terminal_evidence
            podman_full_micall.seal_terminal_evidence = seal_then_mutate
            try:
                report = retire_terminal_arm(
                    arm, {"image_id": "image-id"}, [fastq], "image-id", 0,
                    1.0, arm / "no_timing.json", container_dead=True)
            finally:
                podman_full_micall.seal_terminal_evidence = original
            self.assertFalse(report["applied"])
            self.assertIn("source hashes differ", report["error"])
            self.assertTrue(scratch.is_dir())
            self.assertTrue((scratch / "nuc.csv").is_file())

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


class CompressionInterfaceTests(unittest.TestCase):
    def test_plain_finals_never_reach_a_compressed_content_reader(self):
        prior_hasher = retained_artifacts.CONTENT_HASHER
        prior_suffixes = set(retained_artifacts.COMPRESSED_SUFFIXES)

        def restore():
            retained_artifacts.set_content_hasher(prior_hasher)
            retained_artifacts.COMPRESSED_SUFFIXES.clear()
            retained_artifacts.COMPRESSED_SUFFIXES.update(prior_suffixes)

        self.addCleanup(restore)
        seen = []

        def codec_only_reader(path):
            seen.append(Path(path).name)
            raise AssertionError("codec-only reader must not receive a plain final")

        retained_artifacts.register_compressed_suffix(".zz")
        retained_artifacts.set_content_hasher(codec_only_reader)
        with TemporaryDirectory() as d:
            plain = Path(d) / "nuc.csv"
            plain.write_text("ref,coverage\na,10\n")
            self.assertEqual(content_sha256(plain), digest(plain.read_text()))
            self.assertEqual(seen, [])

            compressed = Path(d) / "nuc.csv.zz"
            compressed.write_bytes(b"codec-specific bytes")
            with self.assertRaises(AssertionError):
                content_sha256(compressed)
            self.assertEqual(seen, ["nuc.csv.zz"])

    def test_zst_logical_hash_uses_backports_zstd_without_registered_hasher(self):
        from backports.zstd import ZstdCompressor
        prior_hasher = retained_artifacts.CONTENT_HASHER
        self.addCleanup(lambda: retained_artifacts.set_content_hasher(prior_hasher))
        retained_artifacts.set_content_hasher(None)
        plain = b"ref,coverage\na,10\n"
        with TemporaryDirectory() as d:
            path = Path(d) / "nuc.csv.zst"
            compressor = ZstdCompressor()
            path.write_bytes(compressor.compress(plain, compressor.FLUSH_FRAME))
            self.assertEqual(content_sha256(path), hashlib.sha256(plain).hexdigest())

    def test_zst_rejects_trailing_bytes_and_large_frames_stream(self):
        from backports.zstd import ZstdCompressor
        prior_hasher = retained_artifacts.CONTENT_HASHER
        self.addCleanup(lambda: retained_artifacts.set_content_hasher(prior_hasher))
        retained_artifacts.set_content_hasher(None)
        plain = b"ref,coverage\na,10\n" * 500000
        with TemporaryDirectory() as d:
            path = Path(d) / "nuc.csv.zst"
            compressor = ZstdCompressor()
            payload = compressor.compress(plain, compressor.FLUSH_FRAME)
            path.write_bytes(payload)
            self.assertEqual(content_sha256(path), hashlib.sha256(plain).hexdigest())
            path.write_bytes(payload + b"trailing")
            with self.assertRaises(RetentionGateError):
                content_sha256(path)

    def test_corrupt_compressed_final_rolls_back_every_codec_error(self):
        plain = "ref,coverage\na,10\n"
        with TemporaryDirectory() as d:
            working = Path(d) / "valid.xz"
            with lzma.open(working, "wb") as stream:
                stream.write(plain.encode())
            valid = working.read_bytes()
            corrupt = bytearray(valid)
            corrupt[10] ^= 0xFF  # flips an LZMA payload byte
            variants = {
                "lzma": (bytes(corrupt), lzma.LZMAError),
                "truncated": (valid[:len(valid) // 2], EOFError),
            }

            for label, (payload, expected_error) in variants.items():
                with self.subTest(codec_error=label):
                    arm = Path(d) / f"arm-{label}"
                    scratch = arm / "scratch"
                    scratch.mkdir(parents=True)
                    final = scratch / "nuc.csv.xz"
                    final.write_bytes(payload)
                    (arm / "podman.stderr.log").write_text("traceback")
                    hashes = {"input.fastq.gz": "a" * 64}
                    evidence, _ = seal_terminal_evidence(
                        arm, {"metrics": {"outputs": {
                            "nuc.csv": {"sha256": digest(plain)}}}}, hashes)
                    with self.assertRaises(expected_error):
                        terminal_retire(arm, evidence_path=evidence,
                                        container_dead=True,
                                        source_hashes=hashes)
                    self.assertTrue(scratch.is_dir())
                    self.assertEqual(final.read_bytes(), payload)
                    self.assertFalse((arm / "nuc.csv.xz").exists())
                    self.assertTrue((arm / "podman.stderr.log").is_file())


class RunnerLivenessGateTests(unittest.TestCase):
    def make_arm(self, root):
        arm = Path(root)
        scratch = arm / "scratch"
        scratch.mkdir()
        (scratch / "nuc.csv").write_text("final")
        (scratch / "temp.fastq").write_text("reads")
        (arm / "plot.svg").write_text("plot")
        fastq = arm / "input.fastq.gz"
        fastq.write_bytes(b"fastq bytes")
        return arm, fastq

    def test_cleanup_failure_suppresses_retirement_without_touching_scratch(self):
        from podman_full_micall import retire_terminal_arm
        with TemporaryDirectory() as d:
            arm, fastq = self.make_arm(d)
            report = retire_terminal_arm(
                arm, {"image_id": "image-id"}, [fastq], "image-id", 124,
                2400.0, arm / "no_timing.json", container_dead=False,
                cleanup_error="podman rm exited 9")
            self.assertFalse(report["applied"])
            self.assertIn("cleanup incomplete", report["error"])
            self.assertTrue((arm / "scratch" / "nuc.csv").is_file())
            self.assertTrue((arm / "plot.svg").is_file())
            self.assertFalse((arm / "terminal_evidence.json").exists())

    def test_unknown_liveness_suppresses_retirement(self):
        from podman_full_micall import retire_terminal_arm
        with TemporaryDirectory() as d:
            arm, fastq = self.make_arm(d)
            report = retire_terminal_arm(
                arm, {"image_id": "image-id"}, [fastq], "image-id", 0,
                1.0, arm / "no_timing.json", container_dead=lambda: False)
            self.assertFalse(report["applied"])
            self.assertIn("not terminated", report["error"])
            self.assertTrue((arm / "scratch" / "nuc.csv").is_file())
            self.assertFalse((arm / "terminal_evidence.json").exists())

    def test_probe_exception_suppresses_retirement(self):
        from podman_full_micall import retire_terminal_arm
        with TemporaryDirectory() as d:
            arm, fastq = self.make_arm(d)

            def broken_probe():
                raise OSError("podman unavailable")

            report = retire_terminal_arm(
                arm, {"image_id": "image-id"}, [fastq], "image-id", 0,
                1.0, arm / "no_timing.json", container_dead=broken_probe)
            self.assertFalse(report["applied"])
            self.assertIn("liveness probe failed", report["error"])
            self.assertTrue((arm / "scratch" / "nuc.csv").is_file())
            self.assertFalse((arm / "terminal_evidence.json").exists())


if __name__ == "__main__":
    unittest.main()
