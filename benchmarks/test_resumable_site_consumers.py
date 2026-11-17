"""Minimal seven-image provenance and restart-safe physical publication."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from assembler_bench import public_fork_provenance
from assembler_bench import real_progress, real_public
from assembler_bench.minimal_image_attestation import SCHEMA as MINIMAL
from expanded import fork_qualification
from expanded.adapters import ASSEMBLERS

BASE = "a"*40
IMAGES={name:f"{i+1:x}"*64 for i,name in enumerate(ASSEMBLERS)}
OTHER=tuple(name for name in ASSEMBLERS if name!="iva")

def attestation():
    return {"schema":MINIMAL,"baseline_commit":BASE,
            "images":{name:{
                "source_branch":f"bench/minimal-8458f9e5-{name}-20261117",
                "source_commit":f"{i+1:x}"*40,
                "source_url":f"https://github.com/ottojung/MiCall/tree/{i+1:x}"+"0"*39,
                "image_sha256":IMAGES[name]}
                for i,name in enumerate(ASSEMBLERS)}}

def dump(path,data):
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

class MinimalPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/"data").mkdir()
        self.att=attestation()
        self.att_path=self.root/"data"/"live-fork-attestation.json"
        dump(self.att_path,self.att)

    def test_provenance_accepts_distinct_minimal_source_branches(self):
        proof={"status":"verified","attestation_schema":MINIMAL,
               "attestation_sha256":hashlib.sha256(
                   self.att_path.read_bytes()).hexdigest(),
               "baseline_commit":BASE,"images":self.att["images"]}
        report={"tools":list(ASSEMBLERS),"images":IMAGES,
                "micall_fork_provenance":proof}
        public_fork_provenance.check(self.root,report)
        report["images"] = dict(IMAGES, ivanka="f"*64)
        with self.assertRaisesRegex(ValueError,"forged"):
            public_fork_provenance.check(self.root,report)

    def test_real_progress_accepts_v2_and_requires_same_baseline(self):
        real=self.root/"real"
        data=self.root/"physical"
        real.mkdir()
        data.mkdir()
        (data/"manifest.tsv").write_text("sample\n"+
             "".join(f"secret-{i}\n" for i in range(198)))
        frozen={"schema":real_progress.SCHEMA_RESUMABLE,
                "expected_samples":198,"selected_sample":None,
                "qualified":False,"selected_tools":list(OTHER),
                "images":IMAGES,"frozen_baseline_identity":BASE,
                "fork_attestation_sha256":
                     hashlib.sha256(self.att_path.read_bytes()).hexdigest(),
                "real_manifest_sha256":real_progress.MANIFEST}
        dump(real/"run_manifest.json",frozen)
        def source_sha(path):
            path=Path(path)
            if path.name=="manifest.tsv":
                return real_progress.MANIFEST
            return hashlib.sha256(path.read_bytes()).hexdigest()
        with (patch.object(real_progress,"source_ok") as source,
              patch.object(real_progress,"sha",side_effect=source_sha),
              patch.object(real_progress,"resumable_completed",
                           return_value={"finished":1,"failed":0}) as checker):
            progress=real_progress.snapshot(
                real,data,self.root,self.att_path,BASE,IMAGES)
            self.assertEqual(set(progress["candidates"]),set(OTHER))
            self.assertEqual(checker.call_count,6)
            self.assertTrue(source.called)
            with self.assertRaisesRegex(ValueError,"attestation mismatch"):
                real_progress.snapshot(
                    real,data,self.root,self.att_path,"b"*40,IMAGES)

    def test_real_public_reads_terminal_v2_without_started_record(self):
        real=self.root/"real"
        data=self.root/"physical"
        real.mkdir()
        data.mkdir()
        (data/"manifest.tsv").write_text("sample\nsecret-1\n")
        dump(real/"run_manifest.json",
             {"schema":real_progress.SCHEMA_RESUMABLE})
        event={"sample":"secret-1","status":"finished","failed":False,
               "iva":{"image_id":IMAGES["iva"],"exit_code":0,"seconds":8.0,
                      "timing_origin":"micall_in_container_monotonic_v1"},
               "ivanka":{"image_id":IMAGES["ivanka"],"exit_code":0,"seconds":7.0,
                         "timing_origin":"micall_in_container_monotonic_v1"},
               "best_contig_acceptance":{"iva_score":85.0,
                                         "ivanka_score":90.0}}
        def collected(folder,samples,images,name):
            return ({"secret-1":event}, {}) if name=="ivanka" else ({},{})
        with patch.object(real_public,"collect",side_effect=collected):
            _,cases,failures,diagnostics,profiles=real_public.case_rows(
                real,data,IMAGES)
        self.assertEqual(cases["ivanka"]["secret-1"],(90.,7.))
        self.assertEqual(cases["iva"]["secret-1"],(85.,8.))
        self.assertEqual(failures["ivanka"],set())
        self.assertIn("secret-1",diagnostics["ivanka"])
        self.assertEqual(profiles["ivanka"],{})

    def test_fork_qualification_fails_closed_on_partial_v2(self):
        proof=self.root/"proof.json"
        dump(proof,self.att)
        real=self.root/"physical"
        synthetic=self.root/"synthetic"
        real.mkdir()
        synthetic.mkdir()
        for root in (real,synthetic):
            (root/"run_manifest.json").write_text("{}\n")
        progress={"run_manifest_sha256":"f"*64,
                  "candidates":{name:{"finished":1,"failed":0}
                                for name in OTHER}}
        checked=({"images":IMAGES},[{"id":"clonal-s000"}],"f"*64,self.att)
        with (patch.object(fork_qualification,"checked",return_value=checked),
              patch.object(fork_qualification,"snapshot",return_value=progress)):
            result=fork_qualification.evaluate(
                synthetic,real,self.root,self.root,proof,self.root,BASE)
        self.assertFalse(result["pass"])
        self.assertEqual(result["status"],"incomplete")

if __name__=="__main__":
    unittest.main()
