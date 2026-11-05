"""Synthetic cohort controls for strict read-only HCV mask discovery."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from discover_shared_mask_cohort import inventory, write_private
from test_discover_shared_mask_targets import target


class CohortDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.cohort = root / "frozen"
        self.cohort.mkdir()
        self.output = root / "derived" / "cohort-audit.json"
        rows, refs = target()
        for name in ("sample-one", "sample-two"):
            folder = self.cohort / name / "ivanka"
            folder.mkdir(parents=True)
            with (folder / "conseq.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with (folder / "remap_conseq.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=("region", "sequence"))
                writer.writeheader()
                writer.writerows({"region": k, "sequence": v}
                                 for k, v in refs.items())

    def test_complete_cohort_provenance_and_candidates(self):
        result = inventory(self.cohort, anchor=8, minimum_length=3,
                           region_contains="one", expected_samples=2)
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["target_candidate_count"], 2)
        self.assertEqual(result["samples_with_candidates"], 2)
        self.assertEqual([s["sample"] for s in result["samples"]],
                         ["sample-one", "sample-two"])
        self.assertFalse(result["modifies_micall_consensus"])
        self.assertEqual(result["haplotype_phase"], "unidentified")
        write_private(result, self.output, self.cohort)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(self.output.read_text()), result)
        write_private(result, self.output, self.cohort)

    def test_fail_if_one_sample_is_missing_sources(self):
        (self.cohort / "sample-two" / "ivanka" / "conseq.csv").unlink()
        with self.assertRaisesRegex(ValueError, "missing original"):
            inventory(self.cohort, 8, 3, "one")

    def test_fail_if_sample_count_disagrees_with_expected(self):
        with self.assertRaisesRegex(ValueError, "unexpected"):
            inventory(self.cohort, 8, 3, "one", expected_samples=198)

    def test_fail_if_report_changes_or_is_written_inside_frozen_cohort(self):
        report = inventory(self.cohort, 8, 3, "one")
        with self.assertRaisesRegex(ValueError, "inside original"):
            write_private(report, self.cohort / "new" / "report.json", self.cohort)
        self.assertFalse((self.cohort / "new").exists())
        self.output.parent.mkdir(parents=True)
        self.output.write_text("different, do not overwrite")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            write_private(report, self.output, self.cohort)
        self.assertEqual(self.output.read_text(), "different, do not overwrite")

    def test_no_raw_sequences_or_biological_phase_claim(self):
        report = inventory(self.cohort, 8, 3, "one")
        payload = json.dumps(report)
        rows, refs = target()
        self.assertNotIn(rows[0]["sequence"], payload)
        self.assertFalse(report["independent_physical_molecules_assigned"])
        self.assertFalse(report["haplotype_specific_depth_assigned"])


if __name__ == "__main__":
    unittest.main()
