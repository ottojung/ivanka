"""Read-level clipping counts are auditable and never confuse SAM placements."""
import tempfile
import unittest
from pathlib import Path

from assembler_bench.sam_metrics import summarize_sam, public_diagnostics


def row(name, flag, cigar, seq, mapq=60):
    return "\t".join((name, str(flag), "ref", "1", str(mapq), cigar,
                      "*", "0", "0", seq, "I" * len(seq))) + "\n"


class SamClipMetricTests(unittest.TestCase):
    def test_both_ends_secondary_and_supplementary_are_not_double_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / "temp.sam"
            src.write_text(
                "@SQ\tSN:ref\tLN:1000\n"
                + row("private_read1", 0, "2S5M3S", "A"*10)
                + row("private_read2", 0, "4M1I3M", "C"*8, mapq=0)
                + row("private_read3", 0x400, "6M", "G"*6, mapq=255)
                + row("private_read1", 0x100, "2S5M3S", "A"*10)
                + row("private_read1", 0x800, "2S5M3S", "A"*10)
                + row("private_read4", 0x4, "*", "T"*9))
            report = summarize_sam(src)
            self.assertEqual(report["status"], "measured")
            counts = report["values"]
            for key, number in (("records", 6), ("primary_mapped", 3),
                                ("primary_unmapped", 1), ("secondary", 1),
                                ("supplementary", 1), ("duplicates", 1),
                                ("soft_clipped_reads", 1),
                                ("soft_clip_events", 2),
                                ("soft_clipped_bases", 5),
                                ("left_clipped_bases", 2),
                                ("right_clipped_bases", 3),
                                ("read_bases", 24), ("inserted_bases", 1),
                                ("mapq_unknown", 1), ("mapq_zero", 1)):
                self.assertEqual(counts[key], number, key)
            self.assertAlmostEqual(counts["clipped_read_fraction"], 1/3)
            self.assertAlmostEqual(
                counts["soft_clipped_bases_per_1000_read_bases"], 5000/24)
            self.assertAlmostEqual(
                counts["soft_clip_events_per_1000_primary_mapped"], 2000/3)
            self.assertAlmostEqual(counts["mean_known_mapq"], 30)
            self.assertAlmostEqual(counts["primary_mapped_fraction"], 3/4)
            self.assertNotIn("private_read", str(report))
            self.assertEqual(len(report["source_sha256"]), 64)

    def test_hard_clip_does_not_count_as_soft_clip(self):
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / "temp.sam"
            src.write_text(row("read", 0, "4H2S5M3S2H", "A"*10))
            result = summarize_sam(src)
            self.assertEqual(result["status"], "measured")
            self.assertEqual(result["values"]["soft_clipped_bases"], 5)
            self.assertEqual(result["values"]["soft_clip_events"], 2)

    def test_missing_and_zero_denominators_are_not_fabricated_zeros(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(summarize_sam(root/"absent.sam")["status"],
                             "unavailable")
            sam = root/"temp.sam"
            sam.write_text(row("unmapped", 4, "*", "A"*10))
            metrics = summarize_sam(sam)["values"]
            self.assertIsNone(metrics["clipped_read_fraction"])
            self.assertIsNone(
                metrics["soft_clipped_bases_per_1000_read_bases"])
            self.assertEqual(metrics["primary_mapped_fraction"], 0)
            outcome = public_diagnostics(root)
            self.assertEqual(outcome["mapping"]["status"], "unavailable")
            self.assertIsNone(outcome["micall_csv"]["values"]["soft_clips_count"])

    def test_rejects_malformed_and_internal_soft_clip(self):
        for cigar, bases in (("5M1S5M", "A"*11), ("5M", "A"*4),
                             ("5Z", "A"*5), ("0S5M", "A"*5)):
            with self.subTest(cigar=cigar):
                with tempfile.TemporaryDirectory() as folder:
                    sam = Path(folder)/"test.sam"
                    sam.write_text(row("private_read", 0, cigar, bases))
                    outcome = summarize_sam(sam)
                    self.assertEqual(outcome["status"], "invalid")
                    self.assertEqual(outcome["values"], {})
                    self.assertNotIn("private_read", str(outcome))

    def test_per_position_nuc_clips_remain_distinct_from_sam_read_clips(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"scratch").mkdir()
            (root/"scratch"/"temp.sam").write_text(
                row("read", 0, "2S5M3S", "A"*10))
            (root/"nuc.csv").write_text(
                "seed,refseq.nuc.pos,clip,q-cutoff,coverage\n"
                "A,1,7,15,1\nA,1,6,15,1\n")
            metrics = public_diagnostics(root)
            self.assertEqual(metrics["mapping"]["values"]["soft_clipped_bases"], 5)
            self.assertEqual(metrics["micall_csv"]["values"]["soft_clips_count"], 7)
            self.assertEqual(metrics["qualification_effect"], "none")


if __name__ == "__main__":
    unittest.main()
