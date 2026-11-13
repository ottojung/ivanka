"""The source-bound reuse report never launders a rival result into a new run."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expanded import reuse_unchanged_rivals as reuse
from expanded.adapters import ASSEMBLERS


def digest(value):
    return hashlib.sha256(value).hexdigest()


class CrossRunEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.original = self.root/"original"
        self.updated = self.root/"updated"
        self.original.mkdir()
        self.updated.mkdir()
        self.input_hashes = {
            "reads/R1.fastq.gz":"a"*64,
            "reads/R2.fastq.gz":"b"*64,
        }
        self.proof = {"valid":True}
        self.images = {tool:f"{i+1:064x}" for i,tool in enumerate(ASSEMBLERS)}
        self.new_images = dict(self.images)
        self.new_images["ivanka"]="a"*64
        self.fields = {
            "id":"clonal-s001", "cohort":"synthetic", "family":"clonal",
            "truth_validation":self.proof,
            "input_sha256":digest((self.input_hashes["reads/R1.fastq.gz"] +
                                   self.input_hashes["reads/R2.fastq.gz"]).encode()),
        }
        self.old_arms={name:{
            "sha256":self.images[name],
            "status":"success","score":float(i+1),
            "seconds":12.5} for i,name in enumerate(ASSEMBLERS)}
        self.before = {**self.fields,"results":self.old_arms}
        self.after = {**self.fields,"ivanka":{
            "sha256":self.new_images["ivanka"],"status":"success",
            "score":77.,"seconds":14.5}}
        (self.original/"run_manifest.json").write_text(
            json.dumps({"images":self.images}))
        (self.original/"results.jsonl").write_text(
            json.dumps(self.before)+"\n")
        for name, evidence in self.old_arms.items():
            path=self.original/"clonal-s001"/name/"execution.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(evidence))
        self.oldverified={"status":"SEVEN_INDEPENDENT_BRANCH_IMAGES_VERIFIED",
                          "base_image_sha256":"f"*64}
        self.newverified={**self.oldverified}
        self.attestation_payload=json.dumps(self.newverified,sort_keys=True)
        (self.updated/"run_manifest.json").write_text(json.dumps({
            "schema":reuse.SCHEMA,"qualified":False,"expected":400,
            "limit":None,"truth_proof":self.proof,"cohort_sha256":"c"*64,
             "fork_attestation_sha256":digest(self.attestation_payload.encode()),
            "ivanka_source_commit":"f"*40,
            "images":self.new_images,"source_sha256":{}}))
        (self.updated/"results.jsonl").write_text(
            json.dumps(self.after)+"\n")
        p=self.updated/"clonal-s001/ivanka"
        p.mkdir(parents=True)
        (p/"execution.json").write_text(json.dumps(self.after["ivanka"]))
        attfile=self.root/"new_att"
        attfile.write_text(json.dumps(self.newverified,sort_keys=True))
        self.attfile=attfile
        self.oldatt=self.root/"old_att"
        self.oldatt.write_text("{}")
        self.oldverified={"status":"SEVEN_INDEPENDENT_BRANCH_IMAGES_VERIFIED",
                          "base_image_sha256":"f"*64}
        self.newverified={**self.oldverified}
        self.attestation_payload=json.dumps(self.newverified,sort_keys=True)
        self.new_runner=self.root/"new-runner"
        self.new_runner.mkdir()

    def joined(self, *, changed=None):
        if changed is not None:
            old=json.loads((self.updated/"run_manifest.json").read_text())
            old.update(changed)
            (self.updated/"run_manifest.json").write_text(json.dumps(old))
        with (patch.object(reuse,"original_checked",return_value=(
                {"truth_proof":self.proof,"cohort_sha256":"c"*64,
                 "images":self.images}, [self.before],
                digest((self.original/"results.jsonl").read_bytes()),
                self.oldverified)),
              patch.object(reuse,"verify",return_value=self.newverified),
              patch.object(reuse,"new_source_ok"),
              patch.object(reuse.subprocess,"check_output",return_value="f"*40),
              patch.object(reuse,"check_arm",return_value=self.after),
              patch("benchmarks.assembler_bench.hxb2_preview.pinned_truth",
                    return_value=({"cases":[{
                        "id":"clonal-s001",
                        "sha256":self.input_hashes}]},self.proof))):
            return reuse.join(
                self.original, self.root, self.oldatt,
                self.updated, self.new_runner, self.attfile,
                self.root, "f"*64,"f"*40)

    def test_joins_only_proven_changed_ivanka(self):
        result=self.joined()
        self.assertEqual(result["matched_cases"],1)
        self.assertFalse(result["pass"])
        self.assertEqual(result["status"],"incomplete")
        row=result["evidence"][0]
        self.assertEqual(row["results"]["ivanka"]["score"],77.)
        self.assertEqual(row["results"]["iva"],self.old_arms["iva"])
        self.assertEqual(row["arm_evidence"]["iva"]["source"],"unchanged-rival")
        self.assertEqual(row["arm_evidence"]["ivanka"]["source"],"changed-ivanka")
        self.assertNotEqual(row["arm_evidence"]["iva"]["execution_sha256"],
                            row["arm_evidence"]["ivanka"]["execution_sha256"])

    def test_other_changed_assembler_cannot_be_reused(self):
        images=copy.deepcopy(self.new_images)
        images["iva"]="b"*64
        with self.assertRaisesRegex(ValueError,"rival assembler image changed"):
            self.joined(changed={"images":images})

    def test_wrong_truth_and_code_cannot_be_reused(self):
        with self.assertRaisesRegex(ValueError,"source and inputs differ"):
            self.joined(changed={"cohort_sha256":"b"*64})

    def test_incomplete_jsonl_line_is_not_taken_as_evidence(self):
        p=self.updated/"results.jsonl"
        p.write_text(json.dumps(self.after)+"\n"+"{\"partial\":")
        self.assertEqual(len(reuse.rows_from(self.updated)),1)
        p.write_text(json.dumps(self.after)+"\n"+json.dumps(self.after)+"\n")
        with self.assertRaisesRegex(ValueError,"duplicate"):
            reuse.rows_from(self.updated)


if __name__=="__main__":
    unittest.main()
