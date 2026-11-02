"""Tests that alternative mapping pairs are never interleaved with mates."""
import csv
import io
import unittest
from paired_remap_candidate_writer import serialize_original_then_alternatives

def record(name, ref, flag, position, mate):
    return {"qname": name, "flag": str(flag), "rname": ref,
            "pos": str(position), "mapq": "0" if ref == "B" else "20",
            "cigar": "4M", "rnext": "=", "pnext": str(mate),
            "tlen": "4", "seq": "ACGT", "qual": "IIII"}

def source():
    return [record("same", "A", 99, 10, 20),
            record("other", "C", 99, 30, 40),
            record("same", "A", 147, 20, 10),
            record("other", "C", 147, 40, 30)]

def alternatives():
    return [record("same", "B", 99, 11, 21),
            record("same", "B", 147, 21, 11)]

def run(original=None, copies=None):
    stream = io.StringIO()
    stats = serialize_original_then_alternatives(
        source() if original is None else original,
        alternatives() if copies is None else copies, stream)
    stream.seek(0)
    return stats, list(csv.DictReader(stream)), stream.getvalue()

class PairedRemapWriterTests(unittest.TestCase):
    def test_original_order_and_contiguous_mate_groups(self):
        stats, rows, _ = run()
        self.assertEqual(stats["alternative_pair_refs"], 1)
        self.assertEqual([r["rname"] for r in rows],
                         ["A", "C", "A", "B", "B", "C"])
        self.assertEqual([r["qname"] for r in rows[3:5]], ["same", "same"])

    def test_original_rows_byte_equivalent_csv_fields(self):
        _, rows, _ = run()
        originals = [row for row in rows if row["rname"] != "B"]
        self.assertEqual(originals, source())

    def test_never_insert_before_last_original_mate(self):
        original = [source()[0], source()[1], source()[3], source()[2]]
        _, rows, _ = run(original)
        self.assertEqual([r["rname"] for r in rows], ["A","C","C","A","B","B"])

    def test_reject_missing_or_duplicate_alternative_mates(self):
        for copied in (alternatives()[:1], alternatives()*2):
            with self.assertRaises(ValueError): run(copies=copied)

    def test_reject_fake_reference_and_malformed_pair(self):
        bad = alternatives()
        bad[1] = dict(bad[1], pnext="999")
        with self.assertRaises(ValueError): run(copies=bad)
        copied = [dict(row, rname="A") for row in alternatives()]
        with self.assertRaises(ValueError): run(copies=copied)

    def test_reject_secondary_and_nonzero_mapq(self):
        for mutation in (dict(flag=str(99 | 0x100)), dict(mapq="1")):
            copied = alternatives()
            copied[0] = dict(copied[0], **mutation)
            with self.assertRaises(ValueError): run(copies=copied)

    def test_reject_nonexclusive_mate_bits_and_unpaired_flags(self):
        for first, second in ((0xC1, 0x1), (0xC0, 0),
                              (0x40, 0x80), (0x40, 0x81)):
            copied = alternatives()
            copied[0] = dict(copied[0], flag=str(first))
            copied[1] = dict(copied[1], flag=str(second))
            with self.subTest(flags=(first, second)):
                with self.assertRaises(ValueError):
                    run(copies=copied)

    def test_no_extra_molecule_identifiers(self):
        _, rows, _ = run()
        self.assertEqual({r["qname"] for r in rows}, {"same", "other"})
        self.assertEqual(len(rows), len(source()) + len(alternatives()))

    def test_ambiguous_original_cannot_be_duplicated(self):
        extra = source()+[source()[0]]
        with self.assertRaises(ValueError): run(original=extra)
        missing = [r for r in source() if r["qname"]!="same"]
        with self.assertRaises(ValueError): run(original=missing)

if __name__ == "__main__":
    unittest.main()
