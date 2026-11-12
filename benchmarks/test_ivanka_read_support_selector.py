import gzip
import os
import random
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ivanka_read_support_selector import (
    K, index_kmers, paired_reads, parse_fasta, paths_from_args,
    read_supported_ranking, rank_by_pair_weighted_breadth, write_selected,
    main,
)


class ReadSupportSelectionTests(unittest.TestCase):
    def test_parse_fasta_and_atomic_write(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "a.fasta"
            write_selected(path, [(">first", "AACGT"), (">second", "TTTT")])
            self.assertEqual(parse_fasta(path), [(">first", "AACGT"), (">second", "TTTT")])

    def test_paired_fastq_gz(self):
        with tempfile.TemporaryDirectory() as root:
            paths = (Path(root) / "R1.fastq.gz", Path(root) / "R2.fastq.gz")
            for path, sequence in zip(paths, ("ACGT" * 40, "TGCA" * 40)):
                with gzip.open(path, "wt") as file:
                    file.write(f"@pair\n{sequence}\n+\n{'!' * len(sequence)}\n")
            self.assertEqual(list(paired_reads(paths, 100)),
                             [("ACGT" * 40, "TGCA" * 40)])

    def test_original_read_support_beats_off_target_length(self):
        with tempfile.TemporaryDirectory() as root:
            randomizer = random.Random(437)
            sequence = "".join(randomizer.choice("ACGT") for _ in range(420))
            entries = [(">offtarget", "G" * 800),
                       (">supported", sequence),
                       (">short", "ACGT" * 15)]
            # Deterministic reads derived only from the second candidate.
            seq = entries[1][1]
            files = (Path(root) / "R1.fastq", Path(root) / "R2.fastq")
            for path, shift in zip(files, (0, 5)):
                with path.open("w") as stream:
                    for i in range(30):
                        frag = seq[shift + i:shift + i + 110]
                        stream.write(f"@p{i}\n{frag}\n+\n{'!' * len(frag)}\n")
            ranking, coverage, pairs = read_supported_ranking(entries, files)
            self.assertEqual(ranking[0], 1)
            self.assertGreater(coverage[1], coverage[0])
            self.assertGreater(pairs[1], pairs[0])

    def test_pair_abundance_breaks_breadth_only_offtarget_bias(self):
        entries = [(">long-low-abundance", "A" * 1100),
                   (">short-dominant", "C" * 820)]
        rank = rank_by_pair_weighted_breadth(
            entries, [990, 716], [128, 339]
        )
        self.assertEqual(rank, [1, 0])

    def test_unsupported_long_extension_is_not_dominant(self):
        # HCV S101-like metrics: long chimeric/repetitive extension has
        # less read-supported breadth despite more total paired-read hits.
        entries = [(">long", "A" * 5651), (">short", "C" * 4033)]
        rank = rank_by_pair_weighted_breadth(
            entries, [466, 1220], [8416, 3191]
        )
        self.assertEqual(rank, [1, 0])

    def test_broad_supported_assembly_beats_short_high_count(self):
        entries = [(">full", "A" * 1150), (">short", "C" * 440)]
        rank = rank_by_pair_weighted_breadth(
            entries, [1116, 420], [410, 578]
        )
        self.assertEqual(rank, [0, 1])

    def test_command_required_inputs(self):
        got = paths_from_args(["--reads1", "a", "--reads2", "b", "--output", "c"])
        self.assertEqual(got["--reads1"], Path("a"))
        with self.assertRaises(ValueError):
            paths_from_args(["--reads1", "a", "--reads2", "b"])

    def test_repetitive_kmers_are_not_false_support(self):
        entries = [(">repeat", "A" * 1000)]
        self.assertNotIn("A" * K, index_kmers(entries))

    def test_select_stable_when_no_hits(self):
        with tempfile.TemporaryDirectory() as root:
            files = (Path(root)/"a.fastq", Path(root)/"b.fastq")
            for path in files:
                path.write_text("@pair\nACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT\n+\n" +
                                "!" * 40 + "\n")
            entries = [(">x", "T" * 55), (">y", "G" * 68)]
            rank, coverage, pairs = read_supported_ranking(entries, files)
            self.assertEqual(rank, [1,0])
            self.assertEqual(coverage, [0,0])
            self.assertEqual(pairs, [0,0])


class SelectorIntegrationTests(unittest.TestCase):
    def test_empty_native_assembly_keeps_success_and_empty_fasta(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "contigs.fasta"
            def native(command, check):
                self.assertTrue(check)
                output.write_text("")
            args = ["--reads1", str(Path(root) / "absent1.fastq"),
                    "--reads2", str(Path(root) / "absent2.fastq"),
                    "--output", str(output)]
            with patch("ivanka_read_support_selector.subprocess.run", side_effect=native):
                main(args)
            self.assertEqual(output.read_bytes(), b"")

    def test_mismatched_fastq_mates_fail_before_scoring(self):
        with tempfile.TemporaryDirectory() as root:
            left = Path(root) / "left.fastq"
            right = Path(root) / "right.fastq"
            left.write_text("@first/1\nACGT\n+\nIIII\n")
            right.write_text("@different/2\nACGT\n+\nIIII\n")
            with self.assertRaisesRegex(ValueError, "pair|mate|identifier"):
                list(paired_reads((left, right), 5))

    def test_sra_and_casava_headers_match_native_parser(self):
        with tempfile.TemporaryDirectory() as root:
            left, right = (Path(root) / "r1.fastq", Path(root) / "r2.fastq")
            left.write_text(
                "@SRR123.1 1 length=40\n" + "A"*40 + "\n+\n" + "I"*40 + "\n"
                "@casava 1:N:0:sample\nACGT\n+\nIIII\n")
            right.write_text(
                "@SRR123.1 2 length=40\n" + "C"*40 + "\n+\n" + "I"*40 + "\n"
                "@casava 2:N:0:sample\nTGCA\n+\nIIII\n")
            self.assertEqual(list(paired_reads((left,right), 10)),
                             [("A"*40, "C"*40), ("ACGT", "TGCA")])

    def test_invalid_casava_designator_fails(self):
        with tempfile.TemporaryDirectory() as root:
            left, right = (Path(root) / "r1.fastq", Path(root) / "r2.fastq")
            left.write_text("@x 3:N:0:x\nACGT\n+\nIIII\n")
            right.write_text("@x 2:N:0:x\nACGT\n+\nIIII\n")
            with self.assertRaises(ValueError):
                list(paired_reads((left, right), 1))

    def test_bad_quality_and_separator_fail_before_scoring(self):
        with tempfile.TemporaryDirectory() as root:
            left, right = (Path(root) / "r1.fastq", Path(root) / "r2.fastq")
            left.write_text("@pair/1\nACGT\n-\nIIII\n")
            right.write_text("@pair/2\nACGT\n+\nIII\n")
            with self.assertRaises(ValueError):
                list(paired_reads((left, right), 5))


class TrimmedTilingIntegrationTests(unittest.TestCase):
    def test_trimmed_contig_tiles_with_original_depth_slice(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "contigs.fa"
            sequence = "A" * 2800 + "CGT" * 1300
            depth = [0] * 2800 + [10] * (len(sequence) - K + 1 - 2800)
            def native(command, check):
                output.write_text(">sample\n" + sequence + "\n")
            args = ["--reads1", "r1", "--reads2", "r2", "--output", str(output)]
            settings = {
                "IVANKA_TRIM_UNSUPPORTED_TERMINI": "1",
                "IVANKA_TRIM_SUPPORTED_ISLAND": "1",
                "IVANKA_READ_BACKED_TILE_SPAN": "2000",
                "IVANKA_READ_BACKED_TILE_OVERLAP": "512",
                "IVANKA_READ_BACKED_MAX_SPAN": "0",
                "IVANKA_POSTSELECT_CONTIGS": "1",
            }
            def observed_tiling(entry, observed, span, overlap):
                self.assertEqual(entry[1], sequence[2288:])
                self.assertEqual(observed, depth[2288:])
                self.assertEqual((span, overlap), (2000, 512))
                return [(entry[0] + "_tile1", entry[1])]
            with (patch.dict(os.environ, settings),
                  patch("ivanka_read_support_selector.subprocess.run", side_effect=native),
                  patch("ivanka_read_support_selector.read_supported_ranking",
                        return_value=([0],[len(depth)-2800],[100],[depth])),
                  patch("ivanka_read_tiling.tile_supported_contig",
                        side_effect=observed_tiling) as tiler):
                main(args)
            tiler.assert_called_once()
            entries = parse_fasta(output)
            self.assertEqual(entries, [(">sample_tile1", sequence[2288:])])
