import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from remap_molecule_conservation_audit import (
    _HYPOTHESIS_MARKER, audit_remap_molecule_conservation, base_qname,
)


def write_csv(path, rows, fieldnames=("qname", "flag", "rname")):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class RemapMoleculeConservationAuditTests(unittest.TestCase):
    def test_base_qname_strips_hypothesis_marker(self):
        self.assertEqual(base_qname("readA"), "readA")
        self.assertEqual(base_qname("readA" + _HYPOTHESIS_MARKER + "2-HCV-1a"), "readA")
        with self.assertRaisesRegex(ValueError, "empty base qname"):
            base_qname(_HYPOTHESIS_MARKER + "x")

    def test_plain_paired_records_preserve_molecule_conservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remap.csv"
            write_csv(path, [
                {"qname": "r1", "flag": "99", "rname": "1-HCV-1a"},
                {"qname": "r1", "flag": "147", "rname": "1-HCV-1a"},
                {"qname": "r2", "flag": "99", "rname": "1-HCV-1a"},
                {"qname": "r2", "flag": "147", "rname": "1-HCV-1a"},
            ])
            report = audit_remap_molecule_conservation(path)
        self.assertEqual(report["rows"], 4)
        self.assertEqual(report["distinct_base_qnames"], 2)
        self.assertEqual(report["hypothesis_marker_qnames"], 0)
        self.assertFalse(report["duplicate_hypothesis_placements_detected"])
        self.assertTrue(report["molecule_conservation_preserved"])
        self.assertFalse(report["independent_molecules_claimed"])
        self.assertFalse(report["biological_safety_claimed"])
        self.assertFalse(report["affects_198_acceptance"])

    def test_hypothesis_markers_flag_duplicate_placements(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remap.csv"
            hyp = "r1" + _HYPOTHESIS_MARKER + "2-HCV-1a"
            write_csv(path, [
                {"qname": "r1", "flag": "99", "rname": "1-HCV-1a"},
                {"qname": "r1", "flag": "147", "rname": "1-HCV-1a"},
                {"qname": hyp, "flag": "99", "rname": "2-HCV-1a"},
                {"qname": hyp, "flag": "147", "rname": "2-HCV-1a"},
            ])
            report = audit_remap_molecule_conservation(path)
        self.assertEqual(report["hypothesis_marker_qnames"], 1)
        self.assertEqual(report["hypothesis_marker_rows"], 2)
        self.assertEqual(report["hypothesis_qnames_with_plain_original_base"], 1)
        self.assertEqual(report["base_qnames_with_more_than_two_records"], 1)
        self.assertEqual(report["hypothesis_refs_row_counts"], {"2-HCV-1a": 2})
        self.assertTrue(report["duplicate_hypothesis_placements_detected"])
        self.assertFalse(report["molecule_conservation_preserved"])

    def test_missing_qname_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remap.csv"
            write_csv(path, [{"flag": "99", "rname": "x"}], fieldnames=("flag", "rname"))
            with self.assertRaisesRegex(ValueError, "missing qname"):
                audit_remap_molecule_conservation(path)

    def test_cli_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "remap.csv"
            write_csv(path, [{"qname": "r1", "flag": "99", "rname": "1"}])
            proc = subprocess.run([sys.executable, str(Path(__file__).with_name(
                "remap_molecule_conservation_audit.py")), str(path), "--json"],
                check=True, capture_output=True, text=True)
        report = json.loads(proc.stdout)
        self.assertEqual(report["schema_version"], "ivanka.remap_molecule_conservation_audit.v1")
        self.assertTrue(report["molecule_conservation_preserved"])


if __name__ == "__main__":
    unittest.main()
