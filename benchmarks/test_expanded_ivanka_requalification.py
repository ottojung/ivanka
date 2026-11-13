"""Verify source-bound Ivanka-only MiCall runs and crash-safe checkpoints."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expanded import fork_ivanka_requalification as solo
from expanded.adapters import ASSEMBLERS
from expanded.micall_checkpoint import digest
from expanded.micall_dominant import SCORE_ORIGIN
from expanded.micall_synthetic_constants import TIMING_ORIGIN


class SingleArmRequalificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root/"data"
        self.data.mkdir()
        (self.data/"cohort.json").write_text("{}")
        self.out = self.root/"output"
        self.att = self.root/"attestation.json"
        self.att.write_text('{"schema":"source-attested"}')
        self.images = {name:f"{i+1:064x}" for i,name in
                       enumerate(ASSEMBLERS)}
        self.source_commit = "f"*40
        self.proof = {"valid":True,"cohort_sha256":"e"*64}
        self.input = {"family":"clonal",
                      "sha256":{"reads/R1.fastq.gz":"a"*64,
                                "reads/R2.fastq.gz":"b"*64}}
        self.cases = [(f"s{i:03}",self.root/f"s{i:03}",self.input)
                      for i in range(400)]
        self.verification = {"images":{"ivanka":{
            "image_sha256":self.images["ivanka"]}}}

    def fake_attempt(self, case, folder, name, image, timeout):
        folder.mkdir(parents=True)
        (folder/"conseq.csv").write_text("MAX,ACGT\n")
        record = {"status":"success", "score":4.,
                  "score_origin":SCORE_ORIGIN,"timing_origin":TIMING_ORIGIN,
                  "sha256":image, "exit_code":0,"seconds":12.5,
                  "final_dominant":{
                      "source_output":"conseq.csv",
                      "conseq_csv_sha256":digest(folder/"conseq.csv")}}
        (folder/"execution.json").write_text(json.dumps(record))
        return record

    def run_mocked(self, *, resume=False, commit=None):
        with (patch.object(solo,"checked_images",
                           return_value=self.verification),
              patch.object(solo.subprocess,"check_output",
                           return_value=commit or self.source_commit),
              patch.object(solo,"attestation",return_value=self.proof),
              patch.object(solo,"cohort_rows",return_value=self.cases),
              patch.object(solo,"attempt",side_effect=self.fake_attempt)):
            return solo.run(self.data,self.out,self.images,"/source",
                            "base",self.att,self.source_commit,
                            jobs=1,limit=1,resume=resume)

    def test_immutable_complete_case_can_resume_without_micall(self):
        self.assertEqual(self.run_mocked(),1)
        folder=self.out/"s000"
        self.assertEqual(json.loads((folder/"case.json").read_text())
                         ["ivanka"]["score"],4.)
        self.assertEqual(len((self.out/"results.jsonl").read_text().splitlines()),1)
        with patch.object(solo,"attempt",side_effect=AssertionError("rerun")):
            with (patch.object(solo,"checked_images",
                               return_value=self.verification),
                  patch.object(solo.subprocess,"check_output",
                               return_value=self.source_commit),
                  patch.object(solo,"attestation",return_value=self.proof),
                  patch.object(solo,"cohort_rows",return_value=self.cases)):
                self.assertEqual(solo.run(
                    self.data,self.out,self.images,"/source","base",
                    self.att,self.source_commit,
                    jobs=1,limit=1,resume=True),1)
        self.assertEqual(len((self.out/"results.jsonl").read_text().splitlines()),1)

    def test_mutated_final_consensus_fails_closed(self):
        self.run_mocked()
        (self.out/"s000/ivanka/conseq.csv").write_text("changed")
        with self.assertRaisesRegex(ValueError,"final MAX evidence altered"):
            self.run_mocked(resume=True)

    def test_changed_rust_source_label_refused_before_execution(self):
        with self.assertRaisesRegex(ValueError,"source commit differs"):
            self.run_mocked(commit="e"*40)
        self.assertFalse(self.out.exists())

    def test_recover_preserves_unfinished_files_in_audit_directory(self):
        self.out.mkdir()
        case=self.out/"s000"
        case.mkdir()
        (case/"stderr.log").write_text("interrupted")
        cases=self.cases[:1]
        got=solo.reassemble(self.out,cases,self.images["ivanka"],self.proof)
        self.assertEqual(got,[])
        self.assertFalse(case.exists())
        archived=list((self.out/"_interrupted").iterdir())
        self.assertEqual(len(archived),1)
        self.assertEqual((archived[0]/"stderr.log").read_text(),"interrupted")


if __name__=="__main__":
    unittest.main()
