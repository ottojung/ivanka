import unittest
from .proc import LIMIT, TRIP, benchmark_roots, tree_bytes


class GuardTests(unittest.TestCase):
    def test_tree_includes_descendants(self):
        table = {1: (0, 1_000_000_000, "micall analyze sample /bench/samples/X"),
                 2: (1, 2_000_000_000, "velveth"), 3: (2, 800_000_000, "bowtie2")}
        self.assertEqual(benchmark_roots(table), {1})
        amount, members = tree_bytes(table, 1)
        self.assertEqual(amount, 3_800_000_000)
        self.assertEqual(members, {1, 2, 3})
        self.assertGreaterEqual(amount, TRIP)

    def test_unrelated_processes_are_not_killed(self):
        table = {1: (0, LIMIT * 2, "cargo test --package skrynia"),
                 2: (0, LIMIT * 2, "micall analyze sample /home/private")}
        self.assertEqual(benchmark_roots(table), set())

    def test_safe_tree_under_trip(self):
        table = {1: (0, 2000, "micall analyze sample /reads/R1.fastq.gz")}
        amount, members = tree_bytes(table, 1)
        self.assertEqual(amount, 2000)
        self.assertLess(amount, TRIP)
