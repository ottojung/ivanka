"""Proof-oriented tests for safe experimental SAM pair serialization."""
import csv
import io
import unittest

from exact_pair_remap_equivalence import reverse_complement
from experimental_pair_safe_writer import serialize_pairs

try:
    from micall.core.sam2aln import matchmaker as micall_matchmaker
except ImportError:
    micall_matchmaker = None


def row(name, ref, flag, pos, mate, seq="ACTG", qual="IHGF", mapq="30"):
    return {"qname":name, "flag":str(flag), "rname":ref,
            "pos":str(pos), "mapq":mapq, "cigar":str(len(seq))+"M",
            "rnext":"=", "pnext":str(mate), "tlen":"10",
            "seq":seq, "qual":qual}


def original(name="r", ref="A"):
    return [row(name,ref,99,11,21), row(name,ref,147,21,11,
                                       "TTCG","HFGI")]


def lifted(name="r", ref="B", reverse=False):
    first,second=original(name)
    flags=(83,163) if reverse else (99,147)
    def copy(source, flag, pos, mate):
        flipped=reverse
        return dict(source,flag=str(flag),rname=ref,pos=str(pos),
                    pnext=str(mate),rnext="=",mapq="0",
                    tlen="14" if source is first else "-14",
                    seq=reverse_complement(source["seq"]) if flipped else source["seq"],
                    qual=source["qual"][::-1] if flipped else source["qual"])
    return [copy(first,flags[0],101,111),copy(second,flags[1],111,101)]


def render(originals, copies):
    output=io.StringIO()
    stats=serialize_pairs(originals,copies,output)
    output.seek(0)
    return stats,list(csv.DictReader(output)),output.getvalue()


class PairSafeWriterTests(unittest.TestCase):
    def test_original_interleaving_preserved_and_candidate_pair_contiguous(self):
        a,b=original("r")
        c,d=original("s","C")
        stats,rows,_=render([a,c,b,d],lifted("r"))
        self.assertEqual([r["rname"] for r in rows],
                         ["A","C","A","B","B","C"])
        self.assertEqual([r["qname"] for r in rows],
                         ["r","s","r","r","r","s"])
        self.assertEqual([r for r in rows if r["rname"]!="B"],[a,c,b,d])
        self.assertEqual(stats["new_read_pair_ids"],0)

    def test_reverse_complement_preserves_original_mates_and_qualities(self):
        stats,rows,_=render(original(),lifted(reverse=True))
        self.assertEqual(stats["alternative_pairs"],1)
        self.assertEqual([r["flag"] for r in rows[-2:]],["83","163"])
        self.assertEqual([r["seq"] for r in rows[-2:]],
                         [reverse_complement(r["seq"]) for r in original()])

    def test_multiple_alternative_references_sort_deterministically(self):
        _,rows,_=render(original(),lifted(ref="D")+lifted(ref="B"))
        self.assertEqual([x["rname"] for x in rows],["A","A","B","B","D","D"])

    def test_reject_mutated_base_and_quality(self):
        for mutation in ({"seq":"AAAA"}, {"qual":"IIII"}):
            copies=lifted()
            copies[0]=dict(copies[0],**mutation)
            output=io.StringIO()
            with self.assertRaisesRegex(ValueError,"changes observed"):
                serialize_pairs(original(),copies,output)
            self.assertEqual(output.getvalue(),"", "validate before any write")

    def test_reject_secondary_unpaired_duplicate_and_missing_mates(self):
        for bad in (lifted()[:1], lifted()*2,
                    [dict(lifted()[0],flag="355"),lifted()[1]],
                    [dict(lifted()[0],flag="0"),lifted()[1]],
                    [dict(lifted()[0],flag="147"),lifted()[1]]):
            with self.assertRaises(ValueError):
                render(original(),bad)

    def test_reject_inconsistent_mate_coordinates_and_strands(self):
        for mutation in ({"pnext":"999"},{"rnext":"another"},
                         {"flag":"67"},{"mapq":"1"}):
            copied=lifted()
            copied[0]=dict(copied[0],**mutation)
            with self.assertRaises(ValueError):
                render(original(),copied)

    def test_reject_inconsistent_alternative_template_lengths(self):
        for lengths in (("999", "-999"), ("14", "14"), ("-14", "14"),
                        ("14", "0"), ("0", "-14")):
            copied = lifted()
            copied[0] = dict(copied[0], tlen=lengths[0])
            copied[1] = dict(copied[1], tlen=lengths[1])
            output = io.StringIO()
            with self.assertRaisesRegex(ValueError, "template length"):
                serialize_pairs(original(), copied, output)
            self.assertEqual(output.getvalue(), "")

    def test_candidate_template_length_with_same_or_reversed_starts(self):
        same = lifted()
        same[0].update(pos="101", pnext="101", tlen="4")
        same[1].update(pos="101", pnext="101", tlen="-4")
        self.assertEqual(render(original(), same)[0]["alternative_pairs"], 1)
        reversed_starts = lifted()
        reversed_starts[0].update(pos="111", pnext="101", tlen="-14")
        reversed_starts[1].update(pos="101", pnext="111", tlen="14")
        self.assertEqual(render(original(), reversed_starts)[0]["alternative_pairs"], 1)

    def test_reject_alternative_to_source_or_unknown_name(self):
        for copied in (lifted(ref="A"),lifted(name="unknown")):
            with self.assertRaises(ValueError):
                render(original(),copied)

    def test_reject_nonunique_original_qname(self):
        with self.assertRaises(ValueError):
            render(original()+[original()[0]],lifted())

    def test_preserves_original_without_candidate(self):
        a,b=original()
        _,rows,_=render([a,b],[])
        self.assertEqual(rows,[a,b])

    @unittest.skipIf(micall_matchmaker is None, "MiCall not installed")
    def test_actual_micall_matchmaker_keeps_pair_references(self):
        a,b = original("r")
        c,d = original("s","C")
        _,_,text = render([a,c,b,d],lifted("r"))
        pairs = list(micall_matchmaker(io.StringIO(text)))
        self.assertEqual([(a["rname"],b["rname"]) for a,b in pairs],
                         [("A","A"),("B","B"),("C","C")])

    def test_qname_pairing_emulates_micall_matchmaker(self):
        a,b=original("r")
        c,d=original("s","C")
        _,rows,_=render([a,c,b,d],lifted("r"))
        pending,pairs={},[]
        for x in rows:
            mate=pending.pop(x["qname"],None)
            if mate is None:pending[x["qname"]]=x
            else:pairs.append((mate["rname"],x["rname"]))
        self.assertEqual(pairs,[("A","A"),("B","B"),("C","C")])
        self.assertEqual(pending,{})


if __name__=="__main__":
    unittest.main()
