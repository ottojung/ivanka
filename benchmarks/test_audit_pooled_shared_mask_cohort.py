"""Fail-closed Q15 pooled coverage tests, no haplotype depth inference."""
import csv
import json
import unittest
from pathlib import Path

from audit_pooled_shared_mask_cohort import audit_cohort
from test_screen_shared_mask_cohort import DirectCohortScreenTests


class PooledMaskCohortTests(DirectCohortScreenTests):
    def test_per_base_q15_support_is_one_pair_not_two_mates(self):
        result = audit_cohort(self.ledger, self.cohort, depth=1)
        self.assertEqual(result["candidate_count"], 2)
        self.assertFalse(result["independent_physical_molecules_inferred"])
        self.assertFalse(result["haplotype_specific_read_depth_assigned"])
        self.assertFalse(result["raw_fastq_per_mate_provenance_authenticated"])
        for r in result["records"]:
            block = r["per_base_q15_pooled_support"]
            self.assertEqual(block["mask_length"], 3)
            self.assertEqual(block["minimum_shared_base_q15_pair_ids"], 1)
            self.assertEqual(block["minimum_shared_base_distinct_pair_sequences"], 1)
            self.assertEqual(block["complete_shared_allele_original_pair_ids"], 1)
            self.assertTrue(block["every_site_meets_q15_original_pair_depth_threshold"])
            self.assertTrue(block["complete_shared_block_meets_both_pair_and_sequence_thresholds"])
            self.assertFalse(block["safe_to_assign_haplotype_specific_coverage"])
            self.assertEqual(len(block["per_site"]), 3)
            self.assertNotIn("private-qname", json.dumps(r))

    def test_depth_threshold_100_not_satisfied_by_one_pair(self):
        result = audit_cohort(self.ledger, self.cohort, depth=100)
        self.assertEqual(result["candidates_meeting_all_pooled_depth_guards"], 0)
        self.assertEqual(result["candidates_with_any_complete_shared_allele_pair"], 2)
        self.assertEqual(result["candidates_meeting_full_block_pair_and_signature_depth"], 0)

    def test_quality_q14_cannot_count_toward_support(self):
        source = self.cohort / "S1" / "ivanka" / "scratch" / "remap.csv"
        with source.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
            fields = list(rows[0])
        for row in rows:
            row["qual"] = "/" * len(row["seq"])  # Phred Q14
        with source.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        result = audit_cohort(self.ledger, self.cohort, depth=1)
        s1 = next(v for v in result["records"] if v["sample"] == "S1")
        block = s1["per_base_q15_pooled_support"]
        self.assertEqual(block["minimum_shared_base_q15_pair_ids"], 0)
        self.assertEqual(block["complete_shared_allele_original_pair_ids"], 0)

    def test_modified_discovery_or_original_micall_source_fails_closed(self):
        source = self.cohort / "S1" / "ivanka" / "remap_conseq.csv"
        source.write_text(source.read_text() + "unexpected,ACGT\n")
        with self.assertRaisesRegex(ValueError, "ledger changed"):
            audit_cohort(self.ledger, self.cohort, depth=1)

    def test_extra_hypothesis_mapping_cannot_multiply_one_original_pair(self):
        source = self.cohort / "S1" / "ivanka" / "scratch" / "remap.csv"
        with source.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
            fields = list(rows[0])
        # Four mapping rows of the same original QNAME are not a strict pair.
        rows.extend([dict(row, rname="two") for row in rows])
        with source.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        result = audit_cohort(self.ledger, self.cohort, depth=1)
        s1 = next(v for v in result["records"] if v["sample"] == "S1")
        block = s1["per_base_q15_pooled_support"]
        self.assertEqual(block["minimum_shared_base_q15_pair_ids"], 0)
        self.assertEqual(block["complete_shared_allele_original_pair_ids"], 0)

    def test_bool_and_zero_depth_cannot_bypass_threshold(self):
        for depth in (True, 0, -1):
            with self.assertRaisesRegex(ValueError, "positive"):
                audit_cohort(self.ledger, self.cohort, depth=depth)


if __name__ == "__main__":
    unittest.main()
