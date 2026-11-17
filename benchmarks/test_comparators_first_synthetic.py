"""Synthetic comparator-only execution never starts Ivanka or replays evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expanded import comparators_first_synthetic as phase

IMAGES={name:f"{i+1:064x}" for i,name in enumerate(phase.TOOLS)}
PROOF={"valid":True,"samples_validated":400}
MANIFEST={"family":"clonal","sha256":{
    "reads/R1.fastq.gz":"a"*64,"reads/R2.fastq.gz":"b"*64}}
SAMPLE=("clonal-s000",None,MANIFEST)


class ComparatorFirstTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.calls=[]

    def fake_attempt(self,case,destination,name,image,timeout):
        self.calls.append(name)
        destination.mkdir()
        source=destination/"conseq.csv"
        source.write_text("sequence\nACGT\n")
        result={
            "status":"success","score":4.,"exit_code":0,"seconds":1.,
            "score_origin":"micall_final_max_reference_panel_v1",
            "timing_origin":"micall_in_container_monotonic_v1",
            "sha256":image,"argv":["podman",image,"--all_projects"],
            "final_dominant":{"source_output":"conseq.csv",
                              "conseq_csv_sha256":hashlib.sha256(
                                  source.read_bytes()).hexdigest()},
        }
        (destination/"execution.json").write_text(json.dumps(result))
        return result

    def test_all_six_not_ivanka_and_resume_zero_replay(self):
        with patch.object(phase,"attempt",side_effect=self.fake_attempt):
            first=phase.run_case(SAMPLE,self.root,IMAGES,PROOF)
            second=phase.run_case(SAMPLE,self.root,IMAGES,PROOF)
        self.assertEqual(self.calls,list(phase.TOOLS))
        self.assertEqual(first,second)
        self.assertNotIn("ivanka",self.calls)

    def test_interrupted_arm_recovered_without_repeating_previous(self):
        (self.root/SAMPLE[0]).mkdir()
        with patch.object(phase,"attempt",side_effect=self.fake_attempt):
            self.fake_attempt(SAMPLE,self.root/SAMPLE[0]/"iva",
                              "iva",IMAGES["iva"],1800)
            folder=self.root/SAMPLE[0]/"haploflow"
            folder.mkdir()
            row=phase.run_case(SAMPLE,self.root,IMAGES,PROOF)
        self.assertEqual(self.calls.count("iva"),1)
        self.assertEqual(len(row["results"]),6)
        self.assertEqual(len(list((self.root/SAMPLE[0]/"_interrupted").iterdir())),1)

    def test_tampered_success_fails_closed(self):
        with patch.object(phase,"attempt",side_effect=self.fake_attempt):
            phase.run_case(SAMPLE,self.root,IMAGES,PROOF)
        (self.root/SAMPLE[0]/"iva"/"conseq.csv").write_text("tampered")
        with self.assertRaisesRegex(ValueError,"completion evidence changed"):
            phase.run_case(SAMPLE,self.root,IMAGES,PROOF)

    def test_manifest_has_no_candidate_image_pin(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"cohort.json").write_text("{}")
            evidence=root/"att.json"
            evidence.write_text("{}")
            manifest=phase.source_manifest(root,PROOF,IMAGES,evidence)
        self.assertEqual(set(manifest["images"]),set(phase.TOOLS))
        self.assertTrue(manifest["ivanka_deferred"])


if __name__=="__main__":
    unittest.main()
