import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from ivanka_postselect_longest import output_path, parse_fasta, top_contigs, replace_fasta, native_arguments, small_input_settings


class LongestPostselectTests(unittest.TestCase):
    def test_small_input_raises_native_budget_and_keeps_more_contigs(self):
        with tempfile.TemporaryDirectory() as directory:
            small = Path(directory) / "reads.fastq"
            small.write_bytes(b"x" * 80)
            with patch.dict("os.environ", {
                    "IVANKA_SMALL_FASTQ_BYTES": "1024",
                    "IVANKA_SMALL_CONTIGS": "4",
                    "IVANKA_SMALL_PRIMARY_SEEDS": "1000",
                    "IVANKA_SMALL_RESCUE_SEEDS": "400"}):
                env, keep = small_input_settings(["--reads1", str(small)], 1)
                self.assertEqual(keep, 4)
                self.assertEqual(env["IVANKA_BENCH_PRIMARY_SEEDS"], "1000")
                self.assertEqual(env["IVANKA_BENCH_RESCUE_SEEDS"], "400")

    def test_large_input_preserves_fast_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            large = Path(directory) / "reads.fastq"
            large.write_bytes(b"x" * 100)
            with patch.dict("os.environ", {"IVANKA_SMALL_FASTQ_BYTES": "60"}):
                self.assertEqual(small_input_settings(["--reads1", str(large)], 1),
                                 (None, 1))

    def test_optional_native_budget_without_changing_default(self):
        with patch.dict("os.environ", {"IVANKA_NATIVE_MAX_CONTIGS": ""}):
            self.assertEqual(native_arguments(["--reads1", "x"]), ["--reads1", "x"])
        with patch.dict("os.environ", {"IVANKA_NATIVE_MAX_CONTIGS": "4"}):
            self.assertEqual(native_arguments(["--reads1", "x"]),
                             ["--reads1", "x", "--max-contigs", "4"])
            with self.assertRaises(ValueError):
                native_arguments(["--max-contigs", "8"])

    def test_optional_read_sampling_limit(self):
        with patch.dict("os.environ", {"IVANKA_NATIVE_MAX_CONTIGS": "",
                                      "IVANKA_NATIVE_MAX_PAIRS": "10000"}):
            self.assertEqual(native_arguments(["--reads1", "x"]),
                             ["--reads1", "x", "--max-pairs", "10000"])
            with self.assertRaises(ValueError):
                native_arguments(["--max-pairs", "100"])
        with patch.dict("os.environ", {"IVANKA_NATIVE_MAX_PAIRS": "0"}):
            with self.assertRaises(ValueError):
                native_arguments(["--reads1", "x"])

    def test_invalid_native_budget(self):
        for budget in ("0", "1001", "-5"):
            with patch.dict("os.environ", {"IVANKA_NATIVE_MAX_CONTIGS": budget}):
                with self.assertRaises(ValueError):
                    native_arguments(["--reads1", "x"])

    def test_stable_ranking(self):
        inp=[(">short", "A"),(">longA", "ACGT"),(">medium", "TTT"),
             (">longB", "CCCC")]
        self.assertEqual([x[0] for x in top_contigs(inp,2)],
                         [">longA",">longB"])

    def test_one_output_required(self):
        self.assertEqual(output_path(["--output","/a"]),Path("/a"))
        self.assertEqual(output_path(["--output=/a"]),Path("/a"))
        for args in ([],["--output"],["--output","a","--output","b"]):
            with self.assertRaises(ValueError):output_path(args)

    def test_roundtrip_preserves_seqs_and_headers(self):
        with tempfile.TemporaryDirectory() as root:
            f=Path(root)/"out.fa"
            entries=[(">zero title", "ACGT"),(">one", "A"*201)]
            replace_fasta(f,entries)
            self.assertEqual(parse_fasta(f),entries)
            replace_fasta(f,top_contigs(entries,1))
            self.assertEqual(parse_fasta(f),entries[1:])

    def test_reject_empty_invalid_fasta(self):
        with tempfile.TemporaryDirectory() as root:
            f=Path(root)/"x.fa";f.write_text(">a\n")
            with self.assertRaises(ValueError):parse_fasta(f)
            f.write_text("ACGT\n")
            with self.assertRaises(ValueError):parse_fasta(f)

    def test_invalid_limits(self):
        for n in (0,-1,1001):
            with self.assertRaises(ValueError):top_contigs([(">a","A")],n)
