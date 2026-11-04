"""Safety regressions for reference-consistent alternative-haplotype remapping."""
from csv import DictReader, DictWriter
from pathlib import Path
import tempfile
import unittest

from conserved_pair_remap import (
    compatible_groups, compatible_targets, load_references, mapped_window,
    project_remap,
)

FIELDS = ["qname", "flag", "rname", "pos", "mapq", "cigar",
          "rnext", "pnext", "tlen", "seq", "qual"]


def row(name="read", flag=99, pos=100, rname="1-HCV-1a",
        cigar="100M", seq=None, qual=None):
    if seq is None:
        seq = "A" * 100
    return dict(qname=name, flag=str(flag), rname=rname, pos=str(pos),
                mapq="0", cigar=cigar, rnext="=", pnext="0", tlen="0",
                seq=seq, qual="I" * len(seq) if qual is None else qual)


def make_csv(path, fields, records):
    with path.open("w", newline="") as stream:
        writer = DictWriter(stream, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


class ConservativeRemapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.src = self.base / "remap.csv"
        self.refs = self.base / "remap_conseq.csv"
        self.out = self.base / "hypotheses.csv"
        self.seq1 = "A" * 1200
        self.seq2 = self.seq1[:600] + "C" + self.seq1[601:]
        self.ref_rows = [
            {"region": "1-HCV-1a", "sequence": self.seq1},
            {"region": "2-HCV-1a", "sequence": self.seq2},
        ]
        make_csv(self.refs, ["region", "sequence"], self.ref_rows)

    def test_identical_regions_support_both_alternatives_once(self):
        originals = [row(flag=99), row(flag=147, pos=300)]
        make_csv(self.src, FIELDS, originals)
        used, stats = project_remap(self.src, self.refs, self.out)
        self.assertEqual(used, self.out)
        self.assertEqual(stats["projected_pairs"], 1)
        with self.out.open() as stream:
            copied = list(DictReader(stream))
        self.assertEqual(copied[:2], originals)
        self.assertEqual(len(copied), 4)
        self.assertEqual({x["qname"] for x in copied[2:]},
                         {"read|ivanka_hypothesis=2-HCV-1a"})
        self.assertEqual({x["rname"] for x in copied[2:]}, {"2-HCV-1a"})
        self.assertEqual([x["seq"] for x in copied[2:]], ["A" * 100] * 2)
        self.assertEqual(self.src.read_text().count("hypothesis="), 0)

    def test_distinguishing_allele_blocks_projection(self):
        make_csv(self.src, FIELDS, [
            row(pos=550), row(flag=147, pos=300),
        ])
        _, stats = project_remap(self.src, self.refs, self.out)
        self.assertEqual(stats["projected_pairs"], 0)
        with self.out.open() as stream:
            self.assertEqual(len(list(DictReader(stream))), 2)

    def test_reverse_flag_and_terminal_soft_clip(self):
        one = row(flag=83, cigar="1S99M", seq="G" + "A" * 99)
        two = row(flag=163, pos=300, cigar="99M1S", seq="A" * 99 + "T")
        make_csv(self.src, FIELDS, [one, two])
        _, stats = project_remap(self.src, self.refs, self.out)
        self.assertEqual(stats["projected_pairs"], 1)
        self.assertEqual(mapped_window(one, "1-HCV-1a", 1200), (99, 198))

    def test_reject_indels_missing_quality_and_wrong_mate_flags(self):
        refs = load_references(self.refs)
        groups = compatible_groups(refs)
        valid = [row(flag=83), row(flag=163, pos=300)]
        self.assertEqual(compatible_targets(valid, refs, groups), ["2-HCV-1a"])
        for bad in (row(flag=163, cigar="50M1I49M", seq="A" * 100),
                    row(flag=163, qual="*"), row(flag=163, rname="2-HCV-1a")):
            self.assertEqual(compatible_targets([valid[0], bad], refs, groups), [])
        self.assertEqual(compatible_targets([valid[0], row(flag=83)], refs, groups), [])

    def test_multiple_alternatives_not_independent_molecules(self):
        refs = {}
        for i, pos in enumerate((100, 250, 400, 550, 700), start=1):
            seq = list("A" * 1200)
            seq[pos] = "C"
            refs[f"{i}-HCV-1a"] = "".join(seq)
        self.assertEqual(len(compatible_groups(refs)["1-HCV-1a"]), 4)
        make_csv(self.refs, ["region", "sequence"],
                 [{"region": k, "sequence": v} for k, v in refs.items()])
        make_csv(self.src, FIELDS, [row(pos=750), row(flag=147, pos=900)])
        _, stats = project_remap(self.src, self.refs, self.out)
        self.assertEqual(stats["projected_pairs"], 4)
        # The same original pair supports four hypotheses, once each.
        # It is not four independent source molecules.
        make_csv(self.src, FIELDS, [row(pos=100), row(flag=147, pos=900)])
        _, rejected = project_remap(self.src, self.refs, self.out)
        self.assertEqual(rejected["projected_pairs"], 0)

    def test_projection_preserves_unique_pair_observation_per_reference(self):
        other = self.seq1[:800] + "C" + self.seq1[801:]
        make_csv(self.refs, ["region", "sequence"],
                 self.ref_rows + [{"region": "3-HCV-1a", "sequence": other}])
        original = [row(name="unique1", flag=99), row(name="unique1", flag=147, pos=300),
                    row(name="unique2", flag=99, pos=900),
                    row(name="unique2", flag=147, pos=1050)]
        make_csv(self.src, FIELDS, original)
        _, stats = project_remap(self.src, self.refs, self.out)
        self.assertGreaterEqual(stats["projected_pairs"], 2)
        from collections import Counter
        with self.out.open() as stream:
            result = list(DictReader(stream))
        per_reference = Counter(
            (item["rname"], item["qname"].split("|ivanka_hypothesis=", 1)[0])
            for item in result
        )
        self.assertTrue(all(count == 2 for count in per_reference.values()))
        # One original molecule appears across alternative hypotheses, but
        # never twice within the same reference's conditional consensus.
        self.assertGreater(sum(name == "unique1" for _, name in per_reference), 1)

    def test_duplicate_names_do_not_create_synthetic_independence(self):
        records = [row(flag=99), row(flag=147, pos=300),
                   row(flag=99), row(flag=147, pos=300)]
        make_csv(self.src, FIELDS, records)
        _, stats = project_remap(self.src, self.refs, self.out)
        self.assertEqual(stats["projected_pairs"], 0)
        with self.out.open() as stream:
            self.assertEqual(len(list(DictReader(stream))), 4)

    def test_no_alternative_keeps_original_remap_unchanged(self):
        make_csv(self.refs, ["region", "sequence"],
                 [self.ref_rows[0], {"region": "2-HCV-1b", "sequence": self.seq2}])
        make_csv(self.src, FIELDS, [row(), row(flag=147)])
        used, stats = project_remap(self.src, self.refs, self.out)
        self.assertEqual(used, self.src)
        self.assertEqual(stats["projected_pairs"], 0)
        self.assertFalse(self.out.exists())

    def test_reference_names_from_remap_conseq_not_array_positions(self):
        make_csv(self.refs, ["region", "sequence"],
                 self.ref_rows + [{"region": "3-unknown-partial", "sequence": self.seq1}])
        self.assertEqual(set(load_references(self.refs)), {"1-HCV-1a", "2-HCV-1a"})

    def test_no_overwrite_or_missing_sam_fields(self):
        make_csv(self.src, FIELDS, [row(), row(flag=147)])
        with self.assertRaisesRegex(ValueError, "separate"):
            project_remap(self.src, self.refs, self.src)
        self.src.write_text("qname,flag\nx,99\n")
        with self.assertRaisesRegex(ValueError, "missing SAM"):
            project_remap(self.src, self.refs, self.out)


if __name__ == "__main__":
    unittest.main()
