"""True MiCall-integrated seven-tool synthetic runner contract regression."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from expanded.adapters import ASSEMBLERS
from expanded.micall_synthetic import (SCORE_ORIGIN, TIMING_ORIGIN,
                                      attempt, command)


class MiCallSyntheticTests(unittest.TestCase):
    def test_each_tool_uses_same_final_micall_pipeline_without_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = root / "case"
            dest = root / "output"
            for name in ASSEMBLERS:
                argv = command(name, "f"*64, case, dest, "clonal-s000", 300)
                self.assertEqual(argv[-11:], [
                    "micall", "analyze", "sample",
                    "/reads/R1.fastq.gz", "/reads/R2.fastq.gz",
                    "/results", "--denovo", "--keep_scratch",
                    "--bad_cycles_csv", "/results/bad_cycles.csv",
                    "--all_projects"])
                self.assertIn(f"{case / 'reads'}:/reads:ro", argv)
                self.assertIn(f"{dest}:/results:rw", argv)
                self.assertNotIn("hidden-truth", " ".join(argv))
                self.assertNotIn("--reference", argv)
                self.assertNotIn("--seeds", argv)
                self.assertNotIn("IVANKA_BENCH_", " ".join(argv))
                self.assertIn("--network=none", argv)
                self.assertIn("--cpus=2", argv)
                self.assertIn("--memory=4g", argv)

    def test_repeated_sample_attempts_use_distinct_container_names(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            first = command("ivanka", "f" * 64, base, base / "out",
                            "quality_decay-s009", 300)
            second = command("ivanka", "f" * 64, base, base / "out",
                             "quality_decay-s009", 300)
        index = first.index("--name") + 1
        self.assertNotEqual(first[index], second[index])
        self.assertRegex(first[index],
                         r"^ivanka-bench-synth-[a-f0-9]{18}-[a-f0-9]{16}$")
        self.assertEqual(first[:index], second[:index])
        self.assertEqual(first[index + 1:], second[index + 1:])

    def test_nonce_does_not_change_pinned_inputs_or_assembler(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            with patch("expanded.micall_synthetic.secrets.token_hex",
                       side_effect=["0123456789abcdef", "fedcba9876543210"]):
                first = command("iva", "a" * 64, base, base / "out",
                                "clonal-s013", 1800)
                second = command("iva", "a" * 64, base, base / "out",
                                 "clonal-s013", 1800)
        index = first.index("--name") + 1
        self.assertEqual(first[index][-16:], "0123456789abcdef")
        self.assertEqual(second[index][-16:], "fedcba9876543210")
        self.assertEqual(
            [*first[:index], *first[index + 1:]],
            [*second[:index], *second[index + 1:]])

    def test_nonzero_micall_is_never_a_qualifying_sample(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/"case"
            source.mkdir()
            out=root/"out"
            manifest={"hidden_truth_file":"hidden-truth/haplotypes.fasta"}
            with patch("expanded.micall_synthetic.run_detached",
                       return_value=Mock(returncode=1, stage="complete")):
                result=attempt((source,manifest),out,"ivanka","a"*64,30)
            self.assertEqual(result["status"],"failed")
            self.assertEqual(result["score"],0.0)
            self.assertIsNone(result["seconds"])
            self.assertIn("MiCall exited",result["error"])

    def test_final_truth_scoring_is_outside_timed_assembler_process(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/"case"
            source.mkdir()
            output=root/"out"
            manifest={"hidden_truth_file":"hidden-truth/haplotypes.fasta"}
            def fake_micall(*args,**kwargs):
                (output/"timing.json").write_text(json.dumps({
                    "timing_origin":TIMING_ORIGIN,"exit_code":0,"seconds":3.25}))
                return Mock(returncode=0,stage="complete")
            final={"score":48.0,"score_origin":SCORE_ORIGIN,
                   "dominant_exact":False,
                   "source":{"sequence_sha256":"b"*64}}
            with (patch("expanded.micall_synthetic.run_detached",
                        side_effect=fake_micall),
                  patch("expanded.micall_synthetic.evaluate_final_alignment",
                        return_value=final),
                  patch("expanded.micall_synthetic.time.monotonic",
                        side_effect=[10,14,20])):
                result=attempt((source,manifest),output,"ivanka","a"*64,45)
            self.assertEqual(result["status"],"success")
            self.assertEqual(result["seconds"],3.25)
            self.assertEqual(result["container_wall_seconds"],4)
            self.assertEqual(result["total_wall_seconds"],10)
            self.assertEqual(result["score"],48.0)

    def test_wrong_micall_timing_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/"case"
            source.mkdir()
            output=root/"out"
            manifest={"hidden_truth_file":"hidden-truth/haplotypes.fasta"}
            def fake_micall(*args,**kwargs):
                (output/"timing.json").write_text(json.dumps({
                    "timing_origin":"standalone_wrapper_clock",
                    "exit_code":0,"seconds":2.0}))
                return Mock(returncode=0,stage="complete")
            with patch("expanded.micall_synthetic.run_detached",
                       side_effect=fake_micall):
                result=attempt((source,manifest),output,"ivanka","a"*64,25)
            self.assertEqual(result["status"],"failed")
            self.assertIn("monotonic",result["error"])
            self.assertEqual(result["score"],0.0)


if __name__ == "__main__":
    unittest.main()
