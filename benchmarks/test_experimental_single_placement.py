"""Conservation and phase-neutrality tests for single-placement remapping."""
import csv
import io
import unittest

from exact_pair_remap_equivalence import reverse_complement
from experimental_single_placement import reallocate, write_candidate

TEMPLATE = "ACGTACCTGCAATGACCTGA"
SOURCE = "GGGG" + TEMPLATE + "TTTT"
FORWARD = "CCCC" + TEMPLATE + "AAAA"
REVERSE = "CCCC" + reverse_complement(TEMPLATE) + "AAAA"
REFS = {"src": SOURCE, "forward": FORWARD, "reverse": REVERSE}


def pair(name="p", source="src", seq=SOURCE):
    return [
        dict(qname=name, flag="99", rname=source, pos="5", mapq="1",
             cigar="13M", rnext="=", pnext="12", tlen="20",
             seq=seq[4:17], qual="I"*13),
        dict(qname=name, flag="147", rname=source, pos="12", mapq="1",
             cigar="13M", rnext="=", pnext="5", tlen="-20",
             seq=seq[11:24], qual="H"*13),
    ]


class SinglePlacementTests(unittest.TestCase):
    def test_forward_move_preserves_molecules_and_observations(self):
        old = pair()
        new, info = reallocate(old, REFS, "forward")
        self.assertEqual([r["rname"] for r in new], ["forward"]*2)
        self.assertEqual([r["seq"] for r in new], [r["seq"] for r in old])
        self.assertEqual([r["qname"] for r in new], ["p", "p"])
        self.assertEqual(info["moved_pairs"], 1)
        self.assertEqual(info["new_pair_ids"], 0)
        self.assertEqual(info["duplicated_pair_ids"], 0)
        self.assertEqual(len(new), len(old))

    def test_reverse_move_preserves_original_orientation(self):
        old = pair()
        new, info = reallocate(old, REFS, "reverse")
        self.assertEqual(info["moved_pairs"], 1)
        self.assertEqual([r["flag"] for r in new], ["83", "163"])
        self.assertEqual(new[0]["seq"], reverse_complement(old[0]["seq"]))
        self.assertEqual(new[1]["qual"], old[1]["qual"][::-1])

    def test_original_mate_order_is_unchanged(self):
        old = list(reversed(pair()))
        new, _ = reallocate(old, REFS, "forward")
        self.assertEqual([r["flag"] for r in new], ["147", "99"])

    def test_no_reassignment_of_observed_variant(self):
        old = pair()
        old[0] = dict(old[0], seq="T"+old[0]["seq"][1:])
        new, info = reallocate(old, REFS, "forward")
        self.assertEqual(new, old)
        self.assertEqual(info["moved_pairs"], 0)

    def test_no_reassignment_of_repeated_template(self):
        refs = dict(REFS, forward=FORWARD + "CC" + TEMPLATE)
        old = pair()
        new, info = reallocate(old, refs, "forward")
        self.assertEqual(new, old)
        self.assertEqual(info["moved_pairs"], 0)

    def test_no_reassignment_of_ambiguous_or_interleaved_pairs(self):
        old = [pair("p")[0], pair("q")[0], pair("p")[1], pair("q")[1]]
        new, info = reallocate(old, REFS, "forward")
        self.assertEqual(new, old)
        self.assertEqual(info["moved_pairs"], 0)

    def test_budget_is_deterministic(self):
        old = pair("a") + pair("b")
        new, info = reallocate(old, REFS, "forward", maximum_moves=1)
        self.assertEqual([r["rname"] for r in new],
                         ["forward", "forward", "src", "src"])
        self.assertEqual(info["moved_pairs"], 1)

    def test_fail_closed_on_invalid_args(self):
        for kwargs in (dict(maximum_moves=-1), dict(maximum_span=0)):
            with self.assertRaises(ValueError):
                reallocate(pair(), REFS, "forward", **kwargs)
        with self.assertRaises(ValueError):
            reallocate(pair(), REFS, "unknown")
        with self.assertRaises(ValueError):
            reallocate([], REFS, "forward")

    def test_writer_preserves_exact_row_count(self):
        out = io.StringIO()
        stats = write_candidate(pair(), REFS, "forward", out)
        out.seek(0)
        rows = list(csv.DictReader(out))
        self.assertEqual(len(rows), 2)
        self.assertEqual(stats["original_qnames"], stats["candidate_qnames"])

    def test_source_mate_flag_malformed_never_transferred(self):
        old = pair()
        old[0] = dict(old[0], flag="35")
        new, info = reallocate(old, REFS, "forward")
        self.assertEqual(new, old)
        self.assertEqual(info["moved_pairs"], 0)


if __name__ == "__main__":
    unittest.main()
