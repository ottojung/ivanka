
"""Regressions for one-placement-per-molecule HCV hypothesis balancing."""
import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from conserved_pair_remap import (
    compatible_targets, load_references, mapped_window, project_remap,
    _valid_base_sites,
)

FIELDS = ["qname", "flag", "rname", "pos", "mapq", "cigar",
          "rnext", "pnext", "tlen", "seq", "qual"]


def row(name, flag=99, pos=100, ref="1-HCV-1a", cigar="100M", quality=None):
    return dict(qname=name, flag=str(flag), rname=ref, pos=str(pos),
                mapq="0", cigar=cigar, rnext="=", pnext="0", tlen="0",
                seq="A" * 100, qual=quality or "I" * 100)


def dump(path, fields, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class ConserveMoleculesTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name)
        self.src = self.path / "remap.csv"
        self.dst = self.path / "candidate.csv"
        self.refs = self.path / "refs.csv"
        self.ref1 = "A" * 1200
        self.ref2 = self.ref1[:600] + "C" + self.ref1[601:]
        dump(self.refs, ["region", "sequence"],
             [{"region": "1-HCV-1a", "sequence": self.ref1},
              {"region": "2-HCV-1a", "sequence": self.ref2}])

    def pairs(self, count, start=0):
        result = []
        for i in range(start, start + count):
            name = f"read-{i}"
            result.extend([row(name), row(name, 147, 300)])
        return result

    def report(self):
        output, stats = project_remap(self.src, self.refs, self.dst)
        with output.open(newline="") as stream:
            records = list(csv.DictReader(stream))
        return output, stats, records

    def test_reassigns_only_surplus_without_duplicate_read_names(self):
        before = self.pairs(200)
        dump(self.src, FIELDS, before)
        original_bytes = self.src.read_bytes()
        output, stats, after = self.report()
        self.assertEqual(output, self.dst)
        self.assertEqual(stats["reassigned_pairs"], 40)
        self.assertEqual(stats["output_read_records_added"], 0)
        self.assertEqual(len(after), len(before))
        self.assertEqual(self.src.read_bytes(), original_bytes)
        self.assertEqual(Counter(r["qname"] for r in after),
                         Counter(r["qname"] for r in before))
        self.assertEqual(sum(r["rname"] == "2-HCV-1a" for r in after), 80)
        self.assertEqual(len({r["qname"] for r in after}), 200)
        self.assertFalse(any("|ivanka_hypothesis=" in r["qname"] for r in after))

    def test_insufficient_source_depth_remains_unchanged(self):
        records = self.pairs(160)
        dump(self.src, FIELDS, records)
        output, stats, after = self.report()
        self.assertEqual(output, self.src)
        self.assertEqual(stats["reassigned_pairs"], 0)
        self.assertEqual(after, records)

    def test_distinguishing_allele_excludes_pair(self):
        records = self.pairs(200)
        records.extend([row("allele", pos=550), row("allele", 147, 300)])
        dump(self.src, FIELDS, records)
        _, _, after = self.report()
        self.assertTrue(all(r["rname"] == "1-HCV-1a"
                            for r in after if r["qname"] == "allele"))

    def test_invalid_flag_and_cigar_do_not_transfer(self):
        records = self.pairs(200)
        records.extend([row("bad-flag"), row("bad-flag", 99, 300)])
        a = row("bad-cigar", cigar="10S10S80M")
        a["seq"] = "A" * 100
        records.extend([a, row("bad-cigar", 147, 300)])
        dump(self.src, FIELDS, records)
        _, _, after = self.report()
        for name in ("bad-flag", "bad-cigar"):
            self.assertTrue(all(r["rname"] == "1-HCV-1a"
                                for r in after if r["qname"] == name))

    def test_invalid_quality_cannot_prove_coverage(self):
        records = []
        for i in range(200):
            name = f"low-{i}"
            records.extend([row(name, quality="!" * 100),
                            row(name, 147, 300, quality="!" * 100)])
        dump(self.src, FIELDS, records)
        output, stats, _ = self.report()
        self.assertEqual(output, self.src)
        self.assertEqual(stats["reassigned_pairs"], 0)

    def test_multiple_matching_hypotheses_are_not_multiplied(self):
        extra = self.ref1[:800] + "C" + self.ref1[801:]
        dump(self.refs, ["region", "sequence"],
             [{"region": "1-HCV-1a", "sequence": self.ref1},
              {"region": "2-HCV-1a", "sequence": self.ref2},
              {"region": "3-HCV-1a", "sequence": extra}])
        dump(self.src, FIELDS, self.pairs(200))
        _, stats, after = self.report()
        self.assertEqual(stats["reassigned_pairs"], 40)
        self.assertEqual(len(after), 400)
        self.assertEqual(len(set(r["qname"] for r in after)), 200)

    def test_duplicate_names_untouched(self):
        dump(self.src, FIELDS, self.pairs(200) + self.pairs(1, 0))
        _, _, after = self.report()
        self.assertEqual(len(after), 402)
        self.assertEqual(sum(r["qname"] == "read-0" for r in after), 4)
        self.assertTrue(all(r["rname"] == "1-HCV-1a"
                            for r in after if r["qname"] == "read-0"))

    def test_reference_guard_and_fail_closed(self):
        original = self.pairs(1)
        dump(self.src, FIELDS, original)
        with self.assertRaisesRegex(ValueError, "separate"):
            project_remap(self.src, self.refs, self.src)
        dump(self.refs, ["region", "sequence"],
             [{"region": "1-HCV-1a", "sequence": self.ref1},
              {"region": "2-HCV-1b", "sequence": self.ref2}])
        output, stats, after = self.report()
        self.assertEqual(output, self.src)
        self.assertEqual(stats["reassigned_pairs"], 0)
        self.assertEqual(after, original)
        self.src.write_text("qname,flag\nx,99\n")
        with self.assertRaisesRegex(ValueError, "missing SAM"):
            project_remap(self.src, self.refs, self.dst)

    def test_windows_and_mates(self):
        records = self.pairs(1)
        refs = load_references(self.refs)
        groups = {"1-HCV-1a": ["2-HCV-1a"]}
        self.assertEqual(compatible_targets(records, refs, groups), ["2-HCV-1a"])
        self.assertEqual(mapped_window(records[0], "1-HCV-1a", 1200), (99, 199))
        self.assertEqual(len(_valid_base_sites(records, 1200)), 200)
        bad = dict(records[0])
        bad["cigar"] = "25S25S50M"
        self.assertIsNone(_valid_base_sites((bad, records[1]), 1200))


if __name__ == "__main__":
    unittest.main()
