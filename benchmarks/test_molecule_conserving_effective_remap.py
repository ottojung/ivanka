import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from molecule_conserving_effective_remap import (
    derive_exclusive_view,
    exclusive_molecule_bound,
    require_molecule_conservation,
)
from remap_molecule_conservation_audit import _HYPOTHESIS_MARKER


def write_csv(path, rows, fieldnames=("qname", "flag", "rname")):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


class ExclusiveBoundTests(unittest.TestCase):
    def test_plain_file_has_no_overcount(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remap.csv"
            write_csv(path, [
                {"qname": "r1", "flag": "99", "rname": "1-HCV-1a"},
                {"qname": "r1", "flag": "147", "rname": "1-HCV-1a"},
            ])
            bound = exclusive_molecule_bound(path)
        self.assertEqual(bound["rows"], 2)
        self.assertEqual(bound["distinct_base_qnames"], 1)
        self.assertEqual(bound["hypothesis_marker_rows"], 0)
        self.assertEqual(
            bound["overcounted_rows_beyond_one_pair_per_molecule"], 0)
        self.assertEqual(bound["molecule_upper_bound_pairs"], 1)
        self.assertFalse(bound["independent_molecules_claimed"])
        self.assertFalse(bound["biological_safety_claimed"])

    def test_hypothesis_rows_count_as_overcount(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remap.csv"
            hyp = "r1" + _HYPOTHESIS_MARKER + "2-HCV-1a"
            write_csv(path, [
                {"qname": "r1", "flag": "99", "rname": "1-HCV-1a"},
                {"qname": "r1", "flag": "147", "rname": "1-HCV-1a"},
                {"qname": hyp, "flag": "99", "rname": "2-HCV-1a"},
                {"qname": hyp, "flag": "147", "rname": "2-HCV-1a"},
            ])
            bound = exclusive_molecule_bound(path)
        self.assertEqual(bound["rows"], 4)
        self.assertEqual(bound["distinct_base_qnames"], 1)
        self.assertEqual(bound["hypothesis_marker_rows"], 2)
        self.assertEqual(
            bound["overcounted_rows_beyond_one_pair_per_molecule"], 2)
        self.assertEqual(bound["molecule_upper_bound_pairs"], 1)

    def test_missing_qname_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remap.csv"
            write_csv(path, [{"flag": "99", "rname": "x"}],
                      fieldnames=("flag", "rname"))
            with self.assertRaisesRegex(ValueError, "missing qname"):
                exclusive_molecule_bound(path)
            with self.assertRaisesRegex(ValueError, "missing qname"):
                require_molecule_conservation(path)


class RequireConservationTests(unittest.TestCase):
    def test_plain_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remap.csv"
            write_csv(path, [
                {"qname": "r1", "flag": "99", "rname": "a"},
                {"qname": "r1", "flag": "147", "rname": "a"},
                {"qname": "r2", "flag": "99", "rname": "a"},
                {"qname": "r2", "flag": "147", "rname": "a"},
            ])
            self.assertEqual(require_molecule_conservation(path), 2)

    def test_hypothesis_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remap.csv"
            hyp = "r1" + _HYPOTHESIS_MARKER + "b"
            write_csv(path, [
                {"qname": "r1", "flag": "99", "rname": "a"},
                {"qname": hyp, "flag": "99", "rname": "b"},
            ])
            with self.assertRaisesRegex(ValueError, "hypothesis-duplicated"):
                require_molecule_conservation(path)


class DeriveExclusiveViewTests(unittest.TestCase):
    def test_plain_passthrough_preserves_rows_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.csv"
            out = Path(tmp) / "out.csv"
            rows = [
                {"qname": "r1", "flag": "99", "rname": "a"},
                {"qname": "r1", "flag": "147", "rname": "a"},
                {"qname": "r2", "flag": "99", "rname": "a"},
                {"qname": "r2", "flag": "147", "rname": "a"},
            ]
            write_csv(src, rows)
            stats = derive_exclusive_view(src, out)
            self.assertEqual(stats["retained_original_rows"], 4)
            self.assertEqual(stats["removed_hypothesis_rows"], 0)
            self.assertFalse(stats["independent_molecules_claimed"])
            self.assertEqual(
                [r["qname"] for r in read_rows(out)],
                ["r1", "r1", "r2", "r2"])
            with src.open(newline="") as a, out.open(newline="") as b:
                self.assertEqual(list(csv.DictReader(a)),
                                 list(csv.DictReader(b)))

    def test_hypothesis_rows_removed_originals_kept_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.csv"
            out = Path(tmp) / "out.csv"
            hyp = "r1" + _HYPOTHESIS_MARKER + "2-HCV-1a"
            write_csv(src, [
                {"qname": "r1", "flag": "99", "rname": "1-HCV-1a"},
                {"qname": "r1", "flag": "147", "rname": "1-HCV-1a"},
                {"qname": hyp, "flag": "99", "rname": "2-HCV-1a"},
                {"qname": hyp, "flag": "147", "rname": "2-HCV-1a"},
                {"qname": "r2", "flag": "99", "rname": "1-HCV-1a"},
                {"qname": "r2", "flag": "147", "rname": "1-HCV-1a"},
            ])
            stats = derive_exclusive_view(src, out)
            self.assertEqual(stats["retained_original_rows"], 4)
            self.assertEqual(stats["removed_hypothesis_rows"], 2)
            got = read_rows(out)
            self.assertEqual(
                [r["qname"] for r in got], ["r1", "r1", "r2", "r2"])
            self.assertTrue(all(
                _HYPOTHESIS_MARKER not in r["qname"] for r in got))
            # Exclusive output must pass the fail-closed gate.
            self.assertEqual(require_molecule_conservation(out), 2)

    def test_same_path_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.csv"
            write_csv(src, [{"qname": "r1", "flag": "99", "rname": "a"}])
            with self.assertRaisesRegex(ValueError, "must be separate"):
                derive_exclusive_view(src, src)

    def test_empty_base_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.csv"
            out = Path(tmp) / "out.csv"
            write_csv(src, [
                {"qname": _HYPOTHESIS_MARKER + "x", "flag": "99",
                 "rname": "b"},
            ])
            with self.assertRaisesRegex(ValueError, "empty base"):
                derive_exclusive_view(src, out)

    def test_cli_check_only_and_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remap.csv"
            write_csv(path, [{"qname": "r1", "flag": "99", "rname": "a"}])
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).with_name(
                    "molecule_conserving_effective_remap.py")),
                 str(path), "--check-only", "--json"],
                check=True, capture_output=True, text=True)
            report = json.loads(proc.stdout)
            self.assertTrue(report["molecule_conservation_preserved"])
            hyp = "r1" + _HYPOTHESIS_MARKER + "b"
            write_csv(path, [
                {"qname": "r1", "flag": "99", "rname": "a"},
                {"qname": hyp, "flag": "99", "rname": "b"},
            ])
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).with_name(
                    "molecule_conserving_effective_remap.py")),
                 str(path), "--check-only"],
                capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
