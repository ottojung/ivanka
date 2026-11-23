"""Synthetic regression of the pair-safe MiCall remap replay boundary."""
import csv
import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from experimental_pair_safe_replay import no_original_alignments_lost, replay


SAM_FIELDS = ("qname","flag","rname","pos","mapq","cigar","rnext",
              "pnext","tlen","seq","qual")
ALIGN_FIELDS = ("refname","qcut","rank","count","offset","seq")


def sam(name, ref, flag, pos, mate):
    return dict(qname=name,flag=str(flag),rname=ref,pos=str(pos),mapq="0",
                cigar="4M",rnext="=",pnext=str(mate),tlen="10",
                seq="ACTG" if flag==99 else "TTCG",qual="IHGF")


def csv_text(fields, records):
    out=io.StringIO()
    writer=csv.DictWriter(out,fieldnames=fields)
    writer.writeheader()
    writer.writerows(records)
    return out.getvalue()


def fake_sam2aln(source, aligned, insert_csv=None,
                 failed_csv=None, clipping_csv=None):
    writer=csv.DictWriter(aligned,fieldnames=ALIGN_FIELDS)
    writer.writeheader()
    pending={}
    rank={}
    for row in csv.DictReader(source):
        former=pending.pop(row["qname"],None)
        if former is None:
            pending[row["qname"]]=row
            continue
        if former["rname"]!=row["rname"]:
            raise AssertionError("MiCall paired unrelated references")
        ref=row["rname"]
        n=rank.get(ref,0)
        writer.writerow(dict(refname=ref,qcut="15",rank=str(n),count="1",
                             offset=former["pos"],seq=former["seq"]))
        rank[ref]=n+1
    if pending:
        raise AssertionError("Synthetic remap contains unpaired reads")
    for handle,header in ((insert_csv,"qname,fwd_rev,refname,pos,insert,qual\n"),
                          (failed_csv,"qname,cause\n"),
                          (clipping_csv,"refname,pos,count\n")):
        if handle is not None:handle.write(header)


class ReplayTests(unittest.TestCase):
    def sample(self, directory, correct=True):
        root=Path(directory)/"sample"
        scratch=root/"scratch"
        scratch.mkdir(parents=True)
        originals=[sam("r","A",99,11,21),sam("r","A",147,21,11)]
        copies=[sam("r","B",99,101,111),sam("r","B",147,111,101)]
        (scratch/"remap.csv").write_text(csv_text(SAM_FIELDS,originals))
        control=dict(refname="A",qcut="15",rank="0",count="1",
                     offset="11",seq="ACTG" if correct else "NNNN")
        (scratch/"aligned.csv").write_text(csv_text(ALIGN_FIELDS,[control]))
        (scratch/"clipping.csv").write_text("refname,pos,count\n")
        (scratch/"conseq_ins.csv").write_text("qname,fwd_rev,refname,pos,insert,qual\n")
        (scratch/"stitched_contigs.csv").write_text("ref,contig\nA,ACGT\n")
        (scratch/"remap_conseq.csv").write_text("region,sequence\nA,ACGT\n")
        return root,originals,copies

    def environment(self, copies):
        micall=types.ModuleType("micall")
        core=types.ModuleType("micall.core")
        sampler=types.ModuleType("micall.core.sam2aln")
        sampler.sam2aln=fake_sam2aln
        return patch.dict("sys.modules",{
            "micall":micall,"micall.core":core,"micall.core.sam2aln":sampler})

    def test_adds_alternatives_without_losing_original_alignments(self):
        with tempfile.TemporaryDirectory() as directory:
            root,originals,copies=self.sample(directory)
            output=Path(directory)/"new"
            with self.environment(copies),patch(
                "experimental_pair_safe_replay.verified_source_references",
                return_value={"A":"ACGT","B":"ACGT"}),patch(
                "experimental_pair_safe_replay.compatible_copies",
                return_value=(copies,{"transferred_pair":1})):
                result=replay(root,output,["A","B"])
            self.assertEqual(result["serialization"]["alternative_pairs"],1)
            self.assertTrue(result["all_original_aligned_records_preserved"])
            self.assertEqual(result["experimental"]["by_reference"],{"A":1,"B":1})
            self.assertEqual(result["control"]["by_reference"],{"A":1})
            self.assertTrue((output/"evidence.json").exists())
            self.assertEqual(len(list(csv.DictReader(
                (output/"experimental-remap.csv").open()))),4)

    def test_control_must_match_authentic_saved_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root,originals,copies=self.sample(directory,correct=False)
            output=Path(directory)/"new"
            with self.environment(copies),patch(
                "experimental_pair_safe_replay.verified_source_references",
                return_value={"A":"ACGT","B":"ACGT"}),patch(
                "experimental_pair_safe_replay.compatible_copies",
                return_value=(copies,{})):
                with self.assertRaisesRegex(AssertionError,"control replay differs"):
                    replay(root,output,["A","B"])
            self.assertFalse((output/"evidence.json").exists())

    def test_no_original_evidence_loss_guard(self):
        old={("A",):2,("C",):1}
        self.assertTrue(no_original_alignments_lost(old,{("A",):3,("C",):1}))
        self.assertFalse(no_original_alignments_lost(old,{("A",):1,("C",):9}))


if __name__=="__main__":
    unittest.main()
