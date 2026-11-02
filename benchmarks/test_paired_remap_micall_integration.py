"""Regression for MiCall's qname-only mate-pairing behavior."""
import csv
import io
import unittest

from paired_remap_candidate_writer import serialize_original_then_alternatives

try:
    from micall.core.sam2aln import matchmaker
except ImportError:
    matchmaker = None


def row(ref, flag, pos, mate, mapq):
    return {"qname": "read-1", "flag": str(flag), "rname": ref,
            "pos": str(pos), "mapq": str(mapq), "cigar": "4M",
            "rnext": "=", "pnext": str(mate), "tlen": "4",
            "seq": "ACGT", "qual": "IIII"}


@unittest.skipUnless(matchmaker, "MiCall is not installed in this environment")
class MiCallPairingIntegrationTests(unittest.TestCase):
    def test_real_parser_never_pairs_across_reference(self):
        original = [row("source", 99, 10, 20, 30),
                    row("source", 147, 20, 10, 30)]
        copied = [row("alternate", 99, 11, 21, 0),
                  row("alternate", 147, 21, 11, 0)]
        output = io.StringIO()
        serialize_original_then_alternatives(original, copied, output)
        output.seek(0)
        pairs = list(matchmaker(output))
        self.assertEqual([(a["rname"], b["rname"]) for a, b in pairs],
                         [("source", "source"), ("alternate", "alternate")])

    def test_interleaved_mates_are_a_real_failure(self):
        sequence = [row("source", 99, 10, 20, 30),
                    row("alternate", 99, 11, 21, 0),
                    row("source", 147, 20, 10, 30),
                    row("alternate", 147, 21, 11, 0)]
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(sequence[0]))
        writer.writeheader()
        writer.writerows(sequence)
        stream.seek(0)
        pairs = list(matchmaker(stream))
        self.assertEqual(len(pairs), 2)
        self.assertTrue(all(a["rname"] != b["rname"] for a, b in pairs))


if __name__ == "__main__":
    unittest.main()
