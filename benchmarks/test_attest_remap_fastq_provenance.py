"""Original FASTQ-vs-SAM provenance: reject synthetic read fabrication."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from attest_remap_fastq_provenance import attest, exact_original_fragment, main


class RemapFastqProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audit = tempfile.TemporaryDirectory()
        self.addCleanup(self.audit.cleanup)
        root = Path(self.tmp.name)
        self.r1, self.r2, self.sam = (root / x for x in
            ("R1.fastq", "R2.fastq", "remap.csv"))
        self.r1.write_text("@original/1\nAACCGGTTAACCGG\n+\nIIIIIIIIIIIIII\n")
        self.r2.write_text("@original/2\nTTAACCGGTTAACC\n+\nJJJJJJJJJJJJJJ\n")
        row = {"qname": "original", "flag": "99", "rname": "r",
               "pos": "1", "rnext": "=", "pnext": "1",
               "seq": "TTAACC", "qual": "IIIIII"}
        row2 = {**row, "flag": "147", "qual": "JJJJJJ"}
        self.csv([row, row2])

    def csv(self, rows):
        with self.sam.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)

    def test_same_processed_sequence_is_one_original_pair(self):
        x = attest(self.sam, self.r1, self.r2)
        self.assertEqual(x["raw_pair_ids_scanned"], 1)
        self.assertEqual(x["remap_pair_ids_verified"], 1)
        self.assertEqual(x["remap_rows_verified"], 2)
        self.assertEqual(x["identical_sequence_remap_mate_pairs"], 1)
        self.assertEqual(x["identical_quality_remap_mate_pairs"], 0)
        self.assertFalse(x["independent_physical_molecules_inferred"])
        self.assertFalse(x["full_length_haplotype_phase_inferred"])
        self.assertNotIn("original/1", json.dumps(x))

    def test_missing_original_pair_rejected(self):
        self.r1.write_text("@other/1\nAACCGGTTAACCGG\n+\nIIIIIIIIIIIIII\n")
        self.r2.write_text("@other/2\nTTAACCGGTTAACC\n+\nJJJJJJJJJJJJJJ\n")
        with self.assertRaisesRegex(ValueError, "missing from original"):
            attest(self.sam, self.r1, self.r2)

    def test_mismatched_fastq_names_rejected(self):
        self.r2.write_text("@unrelated/2\nTTAACCGGTTAACC\n+\nJJJJJJJJJJJJJJ\n")
        with self.assertRaisesRegex(ValueError, "order disagree"):
            attest(self.sam, self.r1, self.r2)

    def test_mutated_sam_bases_rejected(self):
        with self.sam.open() as f: rows=list(csv.DictReader(f))
        rows[1]["seq"] = "ACGTAC"
        self.csv(rows)
        with self.assertRaisesRegex(ValueError, "not from original FASTQ"):
            attest(self.sam, self.r1, self.r2)

    def test_mutated_quality_rejected_even_if_sequence_matches(self):
        with self.sam.open() as f: rows=list(csv.DictReader(f))
        rows[1]["qual"] = "!!!!!!!"
        self.csv(rows)
        with self.assertRaisesRegex(ValueError, "not from original FASTQ"):
            attest(self.sam, self.r1, self.r2)

    def test_identical_sequences_but_swapped_mate_qualities_rejected(self):
        with self.sam.open() as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["qual"], rows[1]["qual"] = rows[1]["qual"], rows[0]["qual"]
        self.csv(rows)
        # Both sequence+quality pairs occur in *some* FASTQ mate, but the
        # observed qualities are not from the mate named by SAM first/second.
        with self.assertRaisesRegex(ValueError, "not from original FASTQ mate"):
            attest(self.sam, self.r1, self.r2)

    def test_first_and_second_sam_flags_required(self):
        with self.sam.open() as f: rows=list(csv.DictReader(f))
        rows[1]["flag"] = "99"
        self.csv(rows)
        with self.assertRaisesRegex(ValueError, "one original R1"):
            attest(self.sam, self.r1, self.r2)

    def test_reverse_complement_and_reversed_quality_match(self):
        assert exact_original_fragment("GGTTAA", "JJJJJJ",
            [("TTAACC", "JJJJJJ")])
        self.assertFalse(exact_original_fragment("GGTTAA", "IIIIII",
            [("TTAACC", "JJJJJJ")]))

    def test_duplicate_original_fastq_name_rejected(self):
        with self.r1.open("a") as stream:
            stream.write(self.r1.read_text())
        with self.r2.open("a") as stream:
            stream.write(self.r2.read_text())
        with self.assertRaisesRegex(ValueError, "Duplicate original FASTQ"):
            attest(self.sam, self.r1, self.r2)

    def test_refuses_nonpaired_or_repeated_sam_records(self):
        with self.sam.open() as stream:
            rows = list(csv.DictReader(stream))
        self.csv(rows + [rows[0]])
        with self.assertRaisesRegex(ValueError, "two remap records"):
            attest(self.sam, self.r1, self.r2)

    def test_single_fastq_cannot_claim_both_mates(self):
        with self.assertRaisesRegex(ValueError, "distinct original FASTQ"):
            attest(self.sam, self.r1, self.r1)

    def test_wrong_fastq_mate_metadata_rejected(self):
        self.r2.write_text("@original/1\nTTAACCGGTTAACC\n+\nJJJJJJJJJJJJJJ\n")
        with self.assertRaisesRegex(ValueError, "Wrong FASTQ mate"):
            attest(self.sam, self.r1, self.r2)

    def test_cli_private_attestation_and_no_replacement(self):
        output = Path(self.audit.name) / "audit.json"
        args = ["attestor", str(self.sam), str(self.r1),
                str(self.r2), "--output", str(output)]
        with patch.object(sys, "argv", args):
            main()
            main()
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        result = json.loads(output.read_text())
        self.assertEqual(result["remap_pair_ids_verified"], 1)
        output.write_text("previous incompatible report")
        with patch.object(sys, "argv", args):
            with self.assertRaises(SystemExit):
                main()
        self.assertEqual(output.read_text(), "previous incompatible report")

    def test_disallows_creating_reports_inside_original_source_folder(self):
        for output in (Path(self.tmp.name) / "new-report.json",
                       Path(self.tmp.name) / "nested" / "new-report.json"):
            with patch.object(sys, "argv", ["attestor", str(self.sam),
                     str(self.r1), str(self.r2), "--output", str(output)]):
                with self.assertRaises(SystemExit):
                    main()
            self.assertFalse(output.exists())

    def test_refuses_mutating_original_sam_via_cli_output(self):
        with patch.object(sys, "argv", ["attestor", str(self.sam),
              str(self.r1), str(self.r2), "--output", str(self.sam)]):
            with self.assertRaises(SystemExit):
                main()
        self.assertTrue(self.sam.read_text().startswith("qname,flag,"))


if __name__ == "__main__":
    unittest.main()
