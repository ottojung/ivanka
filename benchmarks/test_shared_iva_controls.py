"""Proof that six physical competitors reuse one authentic frozen IVA control."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expanded import real_shared_controls as shared
from expanded import real_resume

IVA="a"*64
IVANKA="b"*64
IMAGES={"iva":IVA,"ivanka":IVANKA}

class SharedIvaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        first=self.root/"ivanka"
        first.mkdir()
        (self.root/"run_manifest.json").write_text('{"frozen":true}\n')
        (first/"results.jsonl").write_text('{"a":"1"}\n')
        (first/"checkpoints.json").write_text('{"a":"2"}\n')
        cache=self.root/"iva-baselines"/"sample1"
        cache.mkdir(parents=True)
        (cache/"conseq.csv").write_text("contig,sequence\nc,ACGT\n")
        raw={"image_id":IVA,"exit_code":0,"seconds":3.3,
             "artifact_dir":"/frozen/source/iva",
             "metrics":{"num_final_max_conseqs":1,"outputs":{
                 "conseq.csv":{"sha256":shared.digest(cache/"conseq.csv")}}}}
        self.row={"sample":"sample1","status":"finished","iva":raw,
                  "provenance":{"image":IVA}}
        stored=dict(raw,source_artifact_dir=raw["artifact_dir"],
                    artifact_dir=str(cache.resolve()))
        (cache/"baseline.json").write_text(json.dumps(
            {"provenance":self.row["provenance"],"iva":stored})+"\n")
        self.authentic=patch.object(shared,"authentic_arm")
        self.authentic.start()
        self.addCleanup(self.authentic.stop)
        self.stored=stored
        self.original=self.row

    def test_certify_and_reload_single_fresh_control(self):
        with patch.object(shared,"verify_collection",return_value={
                "sample1":self.original}):
            proof=shared.certify(self.root,{"sample1"},IMAGES)
            self.assertEqual(shared.load(self.root,proof,{"sample1"},IMAGES),
                             {"sample1":self.stored})
            self.assertEqual(json.loads(proof.read_text())["schema"],shared.SCHEMA)
            (self.root/"iva-baselines/sample1/conseq.csv").write_text("tampered")
            with self.assertRaisesRegex(ValueError,"cache not created"):
                shared.load(self.root,proof,{"sample1"},IMAGES)

    def test_missing_original_control_rejected(self):
        with patch.object(shared,"verify_collection",return_value={}):
            with self.assertRaisesRegex(ValueError,"incomplete"):
                shared.certify(self.root,{"sample1"},IMAGES)

    def test_invalid_source_origin_rejected(self):
        self.row["iva"]["artifact_dir"]="/different/source"
        with patch.object(shared,"verify_collection",return_value={
                "sample1":self.row}):
            with self.assertRaisesRegex(ValueError,"cache not created"):
                shared.certify(self.root,{"sample1"},IMAGES)

    def test_candidate_cached_iva_requires_authenticated_same_control(self):
        record={"sample":"sample1","invocation":"attempt-000",
                "status":"finished","failed":False,
                "provenance":{"iva_image_id":IVA,"all_projects":True,
                              "fastq_sha256":["c"*64,"d"*64]},
                "iva":self.stored,"iva_baseline_reused":True,
                "ivanka":{"image_id":IVANKA},
                "best_contig_acceptance":{
                    "reference_count":33,
                    "reference_panel_sha256":
                    "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"}}
        with patch.object(real_resume,"authentic_arm") as verifier:
            real_resume.authenticate(
                record,"sample1",IMAGES,"ivanka",self.root,
                {"sample1":self.stored})
        verifier.assert_called_once_with(
            record["ivanka"],IMAGES["ivanka"],self.root)
        with self.assertRaisesRegex(ValueError,"original source proof"):
            real_resume.authenticate(record,"sample1",IMAGES,"ivanka",self.root)
        with self.assertRaisesRegex(ValueError,"different"):
            real_resume.authenticate(
                record,"sample1",IMAGES,"ivanka",self.root,
                {"sample1":dict(self.stored,seconds=5)})

if __name__=="__main__":
    unittest.main()
