"""The real cohort witness must depend on actual 396 original FASTQ files."""
import csv
import hashlib
from pathlib import Path
import tempfile
import unittest

from expanded.physical_inputs import attest

class PhysicalInputAttestationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/"samples").mkdir()
        (self.root/"hxb2.fasta").write_text(">HXB2\nACGT\n")
        self.data={}
        for name in ("S0","S1"):
            folder=self.root/"samples"/name
            folder.mkdir()
            pair=[]
            for mate in (1,2):
                source=folder/f"{name}_L001_R{mate}_001.fastq.gz"
                payload=(f"{name}:{mate}:original".encode()*10)
                source.write_bytes(payload)
                pair.append({"md5":hashlib.md5(payload,usedforsecurity=False).hexdigest(),
                             "size":len(payload),"path":source})
            self.data[name]=pair
        self.write_manifest()

    def write_manifest(self):
        path=self.root/"manifest.tsv"
        names=("sample","local_md5_r1","kive_md5_r1","r1_bytes",
               "local_md5_r2","kive_md5_r2","r2_bytes")
        with path.open("w",newline="") as handle:
            writer=csv.DictWriter(handle,names,delimiter="\t")
            writer.writeheader()
            for name,pair in sorted(self.data.items()):
                row={"sample":name}
                for n,source in enumerate(pair,1):
                    row[f"local_md5_r{n}"]=source["md5"]
                    row[f"kive_md5_r{n}"]=source["md5"]
                    row[f"r{n}_bytes"]=source["size"]
                writer.writerow(row)
        self.manifest_hash=hashlib.sha256(path.read_bytes()).hexdigest()

    def proof(self):
        return attest(self.root,expected=2,manifest_sha=self.manifest_hash)

    def test_authentic_fixed_inputs_yield_deterministic_digest(self):
        a=self.proof()
        self.assertEqual(a,self.proof())
        self.assertEqual(a["sample_count"],2)
        self.assertEqual(a["total_fastq_bytes"],sum(
            m["size"] for pairs in self.data.values() for m in pairs))

    def test_modified_original_mate_fails_even_if_tsv_is_unchanged(self):
        file=self.data["S0"][0]["path"]
        file.write_bytes(file.read_bytes().replace(b"original",b"altered!"))
        with self.assertRaisesRegex(ValueError,"content differs"):
            self.proof()

    def test_same_size_replaced_fastq_fails(self):
        file=self.data["S1"][1]["path"]
        file.write_bytes(b"x"*file.stat().st_size)
        with self.assertRaisesRegex(ValueError,"content differs"):
            self.proof()

    def test_manifest_edit_is_rejected(self):
        (self.root/"manifest.tsv").write_text("changed")
        with self.assertRaisesRegex(ValueError,"TSV changed"):
            self.proof()

    def test_missing_mate_is_rejected(self):
        self.data["S1"][1]["path"].unlink()
        with self.assertRaisesRegex(ValueError,"original FASTQ mate"):
            self.proof()

    def test_duplicate_extra_mate_is_rejected(self):
        source=self.data["S0"][0]["path"]
        (source.parent/"other_R1_001.fastq.gz").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError,"original FASTQ mate"):
            self.proof()

if __name__=="__main__":
    unittest.main()
