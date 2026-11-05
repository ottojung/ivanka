"""Only strict, single-placement original pair identities enter A/B comparisons."""
import csv
import tempfile
import unittest
from pathlib import Path
from snv_remap_assignment_ab import assignments, compare


def make(folder, placement, extras=()):
    scratch=folder/"scratch"
    scratch.mkdir(parents=True,exist_ok=True)
    with (scratch/"remap_conseq.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=("region","sequence"))
        w.writeheader()
        w.writerows([{"region":"ref-a","sequence":"ACGT"},
                     {"region":"ref-b","sequence":"TGCA"}])
    with (scratch/"remap.csv").open("w",newline="") as f:
        fields=("qname","flag","rname","pos","mapq","cigar",
                "rnext","pnext","tlen","seq","qual")
        w=csv.DictWriter(f,fieldnames=fields)
        w.writeheader()
        for q,ref in placement.items():
            for flag in (99,147):
                w.writerow({"qname":q,"flag":flag,"rname":ref,
                            "pos":1,"mapq":60,"cigar":"4M",
                            "rnext":"=","pnext":1,"tlen":4,
                            "seq":"ACGT","qual":"IIII"})
        for row in extras:w.writerow(row)


class RemapOriginalPairTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.b=Path(self.temp.name)/"b"
        self.c=Path(self.temp.name)/"c"
        make(self.b,{"q1":"ref-a","q2":"ref-a"})
        make(self.c,{"q1":"ref-b","q2":"ref-a"})

    def test_one_original_pair_reassigned_not_doubled(self):
        result=compare(self.b,self.c)
        self.assertEqual(result["original_qnames_mapped_by_both"],2)
        self.assertEqual(
            result["same_original_qname_placed_on_different_reference_sequence"],1)
        self.assertFalse(result["exact_original_pair_placement_equivalence"])
        self.assertFalse(result["original_qnames_are_independent_DNA_molecules"])
        self.assertEqual(result["new_reference_sequences_in_experimental"],1)

    def test_identical_placements_satisfy_exact_assignment(self):
        make(self.c,{"q1":"ref-a","q2":"ref-a"})
        self.assertTrue(compare(self.b,self.c)["exact_original_pair_placement_equivalence"])

    def test_improper_original_qname_excluded_not_used_as_molecule(self):
        bad={"qname":"partial","flag":133,"rname":"*",
             "pos":0,"mapq":0,"cigar":"*",
             "rnext":"*","pnext":0,"tlen":0,"seq":"ACGT","qual":"IIII"}
        make(self.c,{"q1":"ref-b","q2":"ref-a"},[bad])
        data,proof=assignments(self.c)
        self.assertEqual(len(data),2)
        self.assertEqual(proof["excluded_improper_or_unmapped_pair_qnames"],1)

    def test_duplicate_primary_mapping_does_not_count_twice(self):
        bad={"qname":"q2","flag":99,"rname":"ref-b",
             "pos":1,"mapq":60,"cigar":"4M",
             "rnext":"=","pnext":1,"tlen":4,"seq":"ACGT","qual":"IIII"}
        make(self.c,{"q1":"ref-b","q2":"ref-a"},[bad])
        data,proof=assignments(self.c)
        self.assertEqual(len(data),1)
        self.assertEqual(proof["excluded_nonstrict_or_multiassigned_pair_qnames"],1)

    def test_same_reference_sequence_with_reindexed_name_is_not_a_new_haplotype(self):
        # Reference labels are mutable; content identity is the correct key.
        make(self.c,{"q1":"ref-b","q2":"ref-a"})
        seed=self.c/"scratch"/"remap_conseq.csv"
        data=seed.read_text().replace("ref-a","renumbered-unknown")
        seed.write_text(data)
        sam=self.c/"scratch"/"remap.csv"
        sam.write_text(sam.read_text().replace(",ref-a,",",renumbered-unknown,"))
        x=compare(self.b,self.c)
        self.assertEqual(
            x["same_original_qname_placed_on_different_reference_sequence"],1)
        self.assertEqual(x["baseline_reference_sequences_absent_in_experimental"],0)

    def test_two_primary_mates_on_different_references_are_excluded(self):
        bad={"qname":"q2","flag":147,"rname":"ref-b",
             "pos":1,"mapq":60,"cigar":"4M",
             "rnext":"=","pnext":1,"tlen":4,"seq":"ACGT","qual":"IIII"}
        make(self.c,{"q1":"ref-b","q2":"ref-a"})
        sam=self.c/"scratch"/"remap.csv"
        content=sam.read_text().splitlines()
        content[-1]=",".join([content[-1].split(",")[0],"147","ref-b"]+
                            content[-1].split(",")[3:])
        sam.write_text("\n".join(content)+"\n")
        mapped,proof=assignments(self.c)
        self.assertEqual(len(mapped),1)
        self.assertEqual(proof["excluded_nonstrict_or_multiassigned_pair_qnames"],1)

    def test_missing_reference_for_proper_pair_fails_closed(self):
        rows=[{"qname":"new","flag":99,"rname":"missing",
               "pos":1,"mapq":60,"cigar":"4M",
               "rnext":"=","pnext":1,"tlen":4,"seq":"ACGT","qual":"IIII"}]
        make(self.c,{"q1":"ref-b"},rows)
        with self.assertRaisesRegex(ValueError,"Unrecognized"):
            assignments(self.c)


if __name__=="__main__":
    unittest.main()
