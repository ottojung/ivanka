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

    def test_malformed_soft_clips_cannot_be_projected(self):
        refs = load_references(self.refs)
        groups = compatible_groups(refs)
        for cigar in ("10S20S70M", "30M10S60M", "30M10S60S",
                      "0S100M", "100M0S", "10S80M0S", "100M10S"):
            mate = row(flag=147, cigar=cigar)
            self.assertEqual(compatible_targets(
                [row(flag=99), mate], refs, groups), [], cigar)

    def test_invalid_sam_numeric_fields_fail_closed(self):
        refs = load_references(self.refs)
        groups = compatible_groups(refs)
        for pos in ("", "*", "not-a-position", "1.5", "0"):
            self.assertEqual(compatible_targets(
                [row(flag=99, pos=pos), row(flag=147, pos=300)],
                refs, groups), [], pos)
        for flag in ("", "*", "invalid"):
            self.assertEqual(compatible_targets(
                [row(flag=flag), row(flag=147, pos=300)],
                refs, groups), [], flag)

    def test_minor_allele_and_pair_phase_are_not_rewritten(self):
        # Both original mate sequences can disagree with their reference.
        # Projection must copy those actual bases and qualities verbatim.
        first = row(flag=99, pos=100, seq="A" * 20 + "G" + "A" * 79)
        second = row(flag=147, pos=300, seq="A" * 35 + "T" + "A" * 64)
        first["qual"] = "H" * 100
        second["qual"] = "J" * 100
        make_csv(self.src, FIELDS, [first, second])
        _, stats = project_remap(self.src, self.refs, self.out)
        self.assertEqual(stats["projected_pairs"], 1)
        with self.out.open() as stream:
            copies = list(DictReader(stream))[2:]
        self.assertEqual([r["seq"] for r in copies],
                         [first["seq"], second["seq"]])
        self.assertEqual([r["qual"] for r in copies], ["H" * 100, "J" * 100])
        self.assertEqual([r["flag"] for r in copies], ["99", "147"])
        self.assertEqual(len({r["qname"] for r in copies}), 1)

    def test_multiple_alternatives_fail_closed(self):
        refs = {}
        for i, pos in enumerate((100, 250, 400, 550, 700), start=1):
            seq = list("A" * 1200)
            seq[pos] = "C"
            refs[f"{i}-HCV-1a"] = "".join(seq)
        self.assertEqual(compatible_groups(refs), {})
        make_csv(self.refs, ["region", "sequence"],
                 [{"region": k, "sequence": v} for k, v in refs.items()])
        make_csv(self.src, FIELDS, [row(pos=750), row(flag=147, pos=900)])
        used, stats = project_remap(self.src, self.refs, self.out)
        self.assertEqual(used, self.src)
        self.assertEqual(stats["projected_pairs"], 0)
        self.assertFalse(self.out.exists())

    def test_isolated_reciprocal_pairs_remain_eligible(self):
        refs = {
            "1-HCV-1a": "A" * 1200,
            "2-HCV-1a": "A" * 600 + "C" + "A" * 599,
            "3-HCV-1a": "C" * 1200,
            "4-HCV-1a": "C" * 600 + "A" + "C" * 599,
        }
        self.assertEqual(compatible_groups(refs), {
            "1-HCV-1a": ["2-HCV-1a"], "2-HCV-1a": ["1-HCV-1a"],
            "3-HCV-1a": ["4-HCV-1a"], "4-HCV-1a": ["3-HCV-1a"],
        })

    def test_nonreciprocal_nearest_neighbor_chain_is_rejected(self):
        base = "A" * 1200
        near = "C" * 8 + "A" * 1192
        far = "C" * 16 + "A" * 1184
        refs = {"1-HCV-1a": base, "2-HCV-1a": near, "3-HCV-1a": far}
        # An ambiguous center must not lend evidence to either end.
        self.assertEqual(compatible_groups(refs), {})

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
