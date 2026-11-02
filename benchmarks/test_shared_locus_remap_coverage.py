"""Read-only tests for quality-filtered remap depth without double counting."""
import random
from types import SimpleNamespace
import unittest

from shared_locus_remap_coverage import audit, group_loci, sam_observations
from shared_mask_locus_audit import reverse_complement


class SharedLocusDepthTests(unittest.TestCase):
    def setUp(self):
        rng = random.Random(122113)
        randseq = lambda n: "".join(rng.choices("ACGT", k=n))
        self.left, self.allele, self.right = randseq(31), randseq(36), randseq(31)
        self.sequence = self.left + "x" * 36 + self.right
        self.masked = SimpleNamespace(sequence=self.sequence, start=31, end=67)
        self.fragment = self.left + self.allele + self.right
        self.refs = {
            "one": randseq(100) + self.fragment + randseq(130),
            "two": randseq(120) + self.fragment + randseq(140),
        }
        self.starts = {name: seq.index(self.left) + 31 for name, seq in self.refs.items()}

    def row(self, rname, qname, bases=None, qual=None, pos=None, cigar="36M"):
        bases = self.allele if bases is None else bases
        return {
            "rname": rname, "qname": qname, "flag": "0",
            "pos": str(self.starts[rname] + 1 if pos is None else pos),
            "seq": bases, "qual": qual if qual is not None else "I" * len(bases),
            "cigar": cigar,
        }

    def test_pooled_allele_spectrum_excludes_conflicting_pairs(self):
        alt = "A" if self.allele[4] != "A" else "C"
        mutated = self.allele[:4] + alt + self.allele[5:]
        rows = [
            self.row("one", "seed"),
            self.row("two", "seed"),
            self.row("two", "minor", bases=mutated),
            self.row("one", "conflict"),
            self.row("two", "conflict", bases=mutated),
            self.row("two", "unknown", bases=self.allele[:4] + "N" + self.allele[5:]),
        ]
        r = audit(self.masked, self.refs, rows)
        site = r["pooled_allele_spectrum"][4]
        self.assertEqual(site["read_pair_counts"][self.allele[4]], 1)
        self.assertEqual(site["read_pair_counts"][alt], 1)
        self.assertEqual(site["unambiguous_read_pairs"], 2)
        self.assertEqual(site["conflicting_or_non_acgt_read_pairs"], 2)
        self.assertEqual(site["seed_allele_fraction"], 0.5)
        self.assertEqual(r["pooled_deduplicated"]["per_position"][4], 1)

    def test_pooled_allele_spectrum_orients_reverse_target(self):
        self.refs["two"] = reverse_complement(self.refs["two"])
        _, loci = group_loci(self.masked, self.refs)
        reverse_start = min(loci["two"])
        rows = [self.row("one", "first"),
                self.row("two", "second", bases=reverse_complement(self.allele),
                         pos=reverse_start + 1)]
        r = audit(self.masked, self.refs, rows)
        self.assertEqual([site["unambiguous_read_pairs"]
                          for site in r["pooled_allele_spectrum"]], [2] * 36)
        self.assertTrue(all(site["seed_allele_fraction"] == 1
                            for site in r["pooled_allele_spectrum"]))

    def test_pooled_allele_spectrum_no_depth_is_unknown(self):
        r = audit(self.masked, self.refs, [])
        self.assertTrue(all(site["seed_allele_fraction"] is None
                            for site in r["pooled_allele_spectrum"]))

    def test_distinct_pairs_pool_across_reference_without_duplication(self):
        reads = [
            self.row("one", "a"),
            self.row("one", "b"),
            self.row("two", "b"),
            self.row("two", "c"),
            self.row("two", "c"),
        ]
        r = audit(self.masked, self.refs, reads, required_depth=3)
        self.assertEqual(r["per_reference"]["one"]["minimum"], 2)
        self.assertEqual(r["per_reference"]["two"]["minimum"], 2)
        self.assertEqual(r["pooled_deduplicated"]["minimum"], 3)
        self.assertEqual(r["pooled_deduplicated"]["positions_meeting_depth"], 36)

    def test_conflicting_and_low_quality_read_pairs(self):
        alt = ("A" if self.allele[4] != "A" else "C")
        conflict = self.allele[:4] + alt + self.allele[5:]
        rows = [self.row("one", "a"), self.row("two", "a", bases=conflict),
                self.row("one", "b"), self.row("two", "low", qual="!" * 36)]
        r = audit(self.masked, self.refs, rows, required_depth=2)
        depths = r["pooled_deduplicated"]["per_position"]
        self.assertEqual(min(depths), 1)
        self.assertEqual(depths[4], 1)
        self.assertEqual(depths[5], 2)
        self.assertEqual(r["discordant_pair_ids_per_position"][4], 1)
        self.assertEqual(r["pooled_deduplicated"]["positions_meeting_depth"], 35)

    def test_reverse_complemented_reference(self):
        self.refs["two"] = reverse_complement(self.refs["two"])
        allele, loci = group_loci(self.masked, self.refs)
        self.assertEqual(allele, self.allele)
        reverse_start = min(loci["two"])
        read = self.row("two", "reverse", bases=reverse_complement(self.allele),
                        pos=reverse_start + 1)
        result = audit(self.masked, self.refs, [read])
        self.assertEqual(result["pooled_deduplicated"]["minimum"], 1)

    def test_soft_clips_and_deletion_do_not_invent_depth(self):
        clipped = self.row("one", "a", bases="TT"+self.allele+"TT",
                           pos=self.starts["one"]+1, cigar="2S36M2S")
        result = audit(self.masked, self.refs, [clipped])
        self.assertEqual(result["pooled_deduplicated"]["minimum"], 1)
        insertion = self.row("one", "b", bases=self.allele[:10]+"A"+self.allele[10:],
                             cigar="10M1I26M")
        result = audit(self.masked, self.refs, [insertion])
        self.assertEqual(result["pooled_deduplicated"]["minimum"], 1)

    def test_conflicting_seed_allele_fails_closed(self):
        alternate = ("A" if self.allele[1] != "A" else "C")
        frag = self.left+self.allele[:1]+alternate+self.allele[2:]+self.right
        self.refs["two"] = self.refs["two"].replace(self.fragment, frag)
        with self.assertRaisesRegex(ValueError, "conflicting allele"):
            audit(self.masked, self.refs, [])

    def test_repeated_anchor_and_missing_reference_fail_closed(self):
        self.refs["two"] += self.fragment
        with self.assertRaisesRegex(ValueError, "expected one exact locus"):
            audit(self.masked, self.refs, [])
        with self.assertRaises(ValueError):
            audit(self.masked, {"one": self.refs["one"]}, [])

    def test_malformed_sam_fails_closed(self):
        _, loci = group_loci(self.masked, self.refs)
        bad = self.row("one", "bad", cigar="20M")
        with self.assertRaisesRegex(ValueError, "does not consume"):
            list(sam_observations(bad, loci["one"]))
        bad = self.row("one", "bad", cigar="0M36M")
        with self.assertRaisesRegex(ValueError, "Zero-length"):
            list(sam_observations(bad, loci["one"]))
        bad = self.row("one", "bad", qual="I" * 35)
        with self.assertRaisesRegex(ValueError, "Malformed sequence"):
            list(sam_observations(bad, loci["one"]))
        bad = self.row("one", "bad", cigar="36Z")
        with self.assertRaisesRegex(ValueError, "Malformed CIGAR"):
            list(sam_observations(bad, loci["one"]))

    def test_min_quality_and_absence_rejected(self):
        r = audit(self.masked, self.refs, [self.row("one", "a", qual="!"*36)])
        self.assertEqual(r["pooled_deduplicated"]["minimum"], 0)
        with self.assertRaises(ValueError):
            audit(self.masked, self.refs, [], minimum_quality=-1)


if __name__ == "__main__":
    unittest.main()
