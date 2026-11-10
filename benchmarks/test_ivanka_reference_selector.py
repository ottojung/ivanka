import gzip
import tempfile
import unittest
from pathlib import Path
from ivanka_reference_selector import (
    PANEL_SHA256, index_references, load_pinned_panel,
    shared_reference_kmers, select_reference_supported,
)


class ReferenceSelectorTests(unittest.TestCase):
    def test_choose_matching_short_over_long_offtarget(self):
        index = index_references([("reference", "AACCGTTGCCATAGCTGGTCAGT")], k=5)
        entries = [
            (">off", "G" * 200),
            (">on", "AACCGTTGCCATAGCTGGTCAGT"),
        ]
        selected, scores = select_reference_supported(entries, 1, index, 5)
        self.assertEqual(selected, [entries[1]])
        self.assertGreater(scores[0], 0)

    def test_reverse_strand_is_represented(self):
        index = index_references([("reference", "AACCGTTGCCATAGCTGGTCAGT")], 5)
        self.assertGreater(shared_reference_kmers("ACTGACCAGCTATGGCAACGGTT", index, 5), 0)

    def test_fallback_longest_and_stable_ties(self):
        index = index_references([("ref", "ACGTACGTACGTACGTA")], 5)
        entries = [(">a", "NNNN"), (">b", "NNNNNN"), (">c", "NNNNNN")]
        selected, scores = select_reference_supported(entries, 2, index, 5)
        self.assertEqual(selected, [entries[1],entries[2]])
        self.assertEqual(scores, [0,0])

    def test_reject_corrupt_panel(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root)/"panel.gz"
            file.write_bytes(gzip.compress(b'[]', mtime=0))
            with self.assertRaises(ValueError):
                load_pinned_panel(file)

    def test_pinned_public_panel(self):
        file = Path(__file__).with_name("reference_panel_33_20261110.json.gz")
        refs = load_pinned_panel(file)
        self.assertEqual(len(refs), 33)
        self.assertEqual(len(PANEL_SHA256), 64)
        self.assertGreater(len(index_references(refs, 21)), 100000)
