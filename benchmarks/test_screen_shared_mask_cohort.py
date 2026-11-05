"""Synthetic no-fabrication controls for cohort-wide local phase screening."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from discover_shared_mask_cohort import inventory, write_private
from screen_shared_mask_cohort import screen
from test_shared_block_phase_links import fixture, pair


class DirectCohortScreenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.cohort = root / "frozen"
        self.cohort.mkdir()
        self.ledger = root / "reports" / "original-discovery.json"
        masked, refs = fixture()
        pairs = pair("one", "private-qname", refs["one"])
        for sample in ("S1", "S2"):
            source = self.cohort / sample / "ivanka"
            (source / "scratch").mkdir(parents=True)
            for filename, fields, rows in (
                ("conseq.csv",
                 ("region", "q-cutoff", "consensus-percent-cutoff", "sequence"),
                 [{"region": "one", "q-cutoff": "15",
                   "consensus-percent-cutoff": "MAX",
                   "sequence": masked.sequence}]),
                ("remap_conseq.csv", ("region", "sequence"),
                 [{"region": k, "sequence": v} for k, v in refs.items()]),
                ("scratch/remap.csv", tuple(pairs[0]), pairs),
            ):
                with (source / filename).open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
        report = inventory(self.cohort, anchor=8, minimum_length=3,
                           region_contains="one", expected_samples=2)
        write_private(report, self.ledger, self.cohort)

    def test_two_samples_direct_links_with_no_molecule_claims(self):
        result = screen(self.ledger, self.cohort, marker_radius=100)
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["candidates_with_direct_links"], 2)
        self.assertEqual(result["candidates_without_eligible_markers"], 0)
        self.assertEqual(result["candidates_with_markers_but_no_links"], 0)
        self.assertEqual(result["records"][0]["per_marker_original_pair_links"], [1])
        self.assertEqual(result["records"][1][
            "per_marker_distinct_pair_sequence_signatures"], [1])
        self.assertNotIn("private-qname", json.dumps(result))
        self.assertFalse(result["raw_fastq_provenance_authenticated"])
        self.assertFalse(result["independent_physical_molecules_inferred"])
        self.assertFalse(result["haplotype_specific_depth_assigned"])

    def test_source_mutation_causes_failure(self):
        source = self.cohort / "S1" / "ivanka" / "remap_conseq.csv"
        source.write_text(source.read_text() + "other,AAAA\n")
        with self.assertRaisesRegex(ValueError, "ledger changed"):
            screen(self.ledger, self.cohort, marker_radius=100)

    def test_modified_ledger_rejected_before_reading_pairs(self):
        report = json.loads(self.ledger.read_text())
        report["samples"][0]["target_candidates"][0]["mask_start"] += 1
        self.ledger.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "ledger changed"):
            screen(self.ledger, self.cohort, marker_radius=100)

    def test_unsafe_quality_and_search_parameters_rejected(self):
        for bad in (0, 14, True):
            with self.assertRaises(ValueError):
                screen(self.ledger, self.cohort, min_phred=bad,
                       marker_radius=100)
        with self.assertRaises(ValueError):
            screen(self.ledger, self.cohort, marker_radius=0)

    def test_no_marker_does_not_become_fake_phase_support(self):
        result = screen(self.ledger, self.cohort, marker_radius=1)
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["candidates_with_direct_links"], 0)
        self.assertEqual(result["candidates_without_eligible_markers"], 2)
        self.assertEqual(result["records"][0]["per_marker_original_pair_links"], [])

    def test_low_quality_original_remap_pairs_produce_explicit_zero(self):
        source = self.cohort / "S1" / "ivanka" / "scratch" / "remap.csv"
        with source.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
            fields = list(rows[0])
        for row in rows:
            row["qual"] = "!" * len(row["seq"])
        with source.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        result = screen(self.ledger, self.cohort, marker_radius=100)
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["candidates_with_direct_links"], 1)
        s1 = next(r for r in result["records"] if r["sample"] == "S1")
        self.assertEqual(s1["per_marker_original_pair_links"], [0])
        self.assertEqual(s1["per_marker_distinct_pair_sequence_signatures"], [0])

    def test_refuse_creating_report_under_original_cohort(self):
        result = screen(self.ledger, self.cohort, marker_radius=100)
        forbidden = self.cohort / "S1" / "ivanka" / "false-consensus.json"
        with self.assertRaisesRegex(ValueError, "inside original"):
            write_private(result, forbidden, self.cohort)
        self.assertFalse(forbidden.exists())


if __name__ == "__main__":
    unittest.main()
