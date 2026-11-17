"""Authenticated real sample checkpoint/restart and tampering tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expanded import real_resume, real_matrix

PANEL="018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"
IMAGES={"iva":"a"*64,"ivanka":"b"*64}
SOURCE="c"*64

class RealRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.tool=self.root/"ivanka"
        self.tool.mkdir()
        self.manifest=self.root/"run_manifest.json"
        self.manifest.write_text('{"immutable":true}\n')
        self.timer=patch("benchmarks.container_completion.verified_internal_seconds",
                         return_value=2.)
        self.timer.start()
        self.addCleanup(self.timer.stop)

    def arm(self,base,image,sample):
        directory=base/sample/"ivanka" if image==IMAGES["ivanka"] else base/sample/"iva"
        directory.mkdir(parents=True,exist_ok=True)
        (directory/"podman.stderr.log").write_text(
            "Begin MiCall\nmicall.process_run(): Done.\n")
        (directory/"micall_internal_timing.json").write_text("{}")
        outputs={}
        for index in range(11):
            name=f"output-{index:02d}.csv"
            file=directory/name
            file.write_text(f"output {index} sample {sample}\n")
            outputs[name]={"exists":True,"sha256":real_resume.digest(file)}
        return {"artifact_dir":str(directory),"image_id":image,"exit_code":0,
                "timing_origin":"micall_in_container_monotonic_v1",
                "seconds":2.,"container_wall_seconds":3.,
                "metrics":{"outputs":outputs}}

    def record(self,attempt,sample):
        inv=attempt.name
        return {"sample":sample,"invocation":inv,"status":"finished","failed":False,
                "provenance":{"all_projects":True,"iva_image_id":IMAGES["iva"],
                              "fastq_sha256":["d"*64,"e"*64]},
                "iva":self.arm(attempt,IMAGES["iva"],sample),
                "ivanka":self.arm(attempt,IMAGES["ivanka"],sample),
                "best_contig_acceptance":{"pass":True,"reference_count":33,
                                         "reference_panel_sha256":PANEL}}

    def write_attempt(self,number,record,started_only=None):
        attempt=self.tool/f"attempt-{number:03d}"
        attempt.mkdir(exist_ok=True)
        lines=[{"sample":record["sample"],"invocation":attempt.name,
                "status":"started"}]
        if started_only is None:
            lines.append(record)
        with (attempt/"results.jsonl").open("w") as stream:
            for line in lines:
                stream.write(json.dumps(line)+"\n")
        return attempt

    def test_crash_resumes_only_missing_sample_without_modifying_prior_attempt(self):
        first=self.tool/"attempt-000"
        a=self.record(first,"a")
        self.write_attempt(0,a)
        rows,witnesses=real_resume.collect(
            self.tool,{"a","b"},IMAGES,"ivanka")
        self.assertEqual(set(rows),{"a"})
        first_sha=real_resume.digest(first/"results.jsonl")
        real_resume.commit(self.tool,rows,witnesses,self.manifest)
        restored=real_resume.verify_collection(
            self.tool,{"a","b"},IMAGES,"ivanka",self.manifest)
        self.assertEqual(set(restored),{"a"})
        second=self.tool/"attempt-001"
        b=self.record(second,"b")
        self.write_attempt(1,b)
        restored=real_resume.verify_collection(
            self.tool,{"a","b"},IMAGES,"ivanka",self.manifest,
            allow_additional=True)
        self.assertEqual(set(restored),{"a","b"})
        rows,witnesses=real_resume.collect(
            self.tool,{"a","b"},IMAGES,"ivanka")
        real_resume.commit(self.tool,rows,witnesses,self.manifest)
        self.assertEqual(set(real_resume.verify_collection(
            self.tool,{"a","b"},IMAGES,"ivanka",self.manifest)),{"a","b"})
        self.assertEqual(real_resume.digest(first/"results.jsonl"),first_sha)
        with patch.object(real_matrix,"EXPECTED",2):
            with self.assertRaisesRegex(ValueError,"exactly 198"):
                real_matrix.source_rows(self.tool/"results.jsonl")
            verified=real_matrix.source_rows(
                self.tool/"results.jsonl",self.tool/"checkpoints.json",
                IMAGES,"ivanka",self.manifest)
            self.assertEqual(set(verified),{"a","b"})

    def test_output_tampering_fails_closed(self):
        attempt=self.tool/"attempt-000"
        record=self.record(attempt,"a")
        self.write_attempt(0,record)
        rows,witnesses=real_resume.collect(
            self.tool,{"a"},IMAGES,"ivanka")
        real_resume.commit(self.tool,rows,witnesses,self.manifest)
        output=Path(record["ivanka"]["artifact_dir"])/"output-01.csv"
        output.write_text("corrupted")
        with self.assertRaisesRegex(ValueError,"MiCall output differs"):
            real_resume.verify_collection(
                self.tool,{"a"},IMAGES,"ivanka",self.manifest)

    def test_duplicate_terminal_result_rejected(self):
        attempt=self.tool/"attempt-000"
        a=self.record(attempt,"a")
        self.write_attempt(0,a)
        again=self.tool/"attempt-001"
        b=self.record(again,"a")
        self.write_attempt(1,b)
        with self.assertRaisesRegex(ValueError,"competing terminal"):
            real_resume.collect(self.tool,{"a"},IMAGES,"ivanka")

    def test_last_truncated_json_is_not_a_terminal_checkpoint(self):
        attempt=self.tool/"attempt-000"
        a=self.record(attempt,"a")
        self.write_attempt(0,a,started_only=True)
        with (attempt/"results.jsonl").open("ab") as out:
            out.write(b'{"sample":"a","status":"finished"')
        rows,_=real_resume.collect(self.tool,{"a"},IMAGES,"ivanka")
        self.assertEqual(rows,{})

    def test_checkpoint_source_manifest_must_remain_identical(self):
        attempt=self.tool/"attempt-000"
        a=self.record(attempt,"a")
        self.write_attempt(0,a)
        rows,witnesses=real_resume.collect(self.tool,{"a"},IMAGES,"ivanka")
        real_resume.commit(self.tool,rows,witnesses,self.manifest)
        self.manifest.write_text('{"immutable":false}\n')
        with self.assertRaisesRegex(ValueError,"checkpoint evidence changed"):
            real_resume.verify_collection(
                self.tool,{"a"},IMAGES,"ivanka",self.manifest)

if __name__=="__main__":
    unittest.main()
