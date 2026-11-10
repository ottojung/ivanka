import gzip
import random
from pathlib import Path
import tempfile
import unittest

from ivanka_read_support_selector import (
    K, index_kmers, paired_reads, parse_fasta, paths_from_args,
    read_supported_ranking, rank_by_pair_weighted_breadth, write_selected,
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
