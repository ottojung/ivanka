"""Live publication must use actual per-arm checkpoints, never a stale cohort."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.expanded.adapters import ASSEMBLERS
from benchmarks.assembler_bench import current_inputs as inputs
from benchmarks.assembler_bench import current_publish as publish
from benchmarks.assembler_bench import current_runs as runs
from benchmarks.assembler_bench.current_validation_v2 import check_current

IMAGES={name:f"{i+1:064x}" for i,name in enumerate(ASSEMBLERS)}


class UnifiedReportingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def report(self):
        sample=inputs.sample("H001",ASSEMBLERS,"clonal")
        inputs.accept(sample,"iva",dict(status="success",score=80,seconds=4.5),
                      {"records":30})
        inputs.accept(sample,"megahit",
                      dict(status="success",score=74,seconds=5.),
                      {"records":23})
        proof={"status":"verified","images":{
            name:{"source_commit":"f"*40} for name in ASSEMBLERS}}
        with (patch.object(runs,"synthetic",return_value=(
                  {"clonal-s000":sample},"a"*64)),
              patch.object(runs,"physical",return_value=({},None)),
              patch.object(runs,"fork_provenance",return_value=proof)):
            return runs.current(None,None,None,None,None,IMAGES,
                                "2026-11-17",None,None)

    def test_normal_site_has_current_sparse_data_not_previous_cohort(self):
        report=self.report()
        self.assertTrue(check_current(report))
        syn,real,combined=report["runs"]
        self.assertEqual((syn["sample_count"],real["sample_count"],
                          combined["sample_count"]),(1,0,1))
        self.assertEqual(syn["tool_progress"]["iva"]["finished"],1)
        self.assertEqual(syn["tool_progress"]["ivanka"]["finished"],0)
        self.assertEqual(syn["samples"][0]["score"]["ivanka"],None)
        self.assertEqual(syn["samples"][0]["outcome"],"incomplete")
        self.assertEqual(syn["samples"][0]["diagnostics"]["iva"]["records"],30)
        self.assertEqual(syn["tool_progress"]["velvet"]["failed"],0)
        matrix=syn["dominance_matrix"]["metrics"]["alignment"]
        self.assertEqual(matrix["iva"]["megahit"]["paired"],1)
        self.assertEqual(matrix["iva"]["ivanka"]["paired"],0)
        self.assertEqual(combined["samples"][0]["alias"],"S-H001")

    def test_forged_counters_and_synthetic_completion_fail(self):
        report=self.report()
        report["runs"][0]["tool_progress"]["iva"]["finished"]=400
        with self.assertRaisesRegex(ValueError,"counter"):
            check_current(report)
        report=self.report()
        report["runs"][0]["sample_count"]=400
        with self.assertRaisesRegex(ValueError,"sample count"):
            check_current(report)

    def test_monotone_rejects_dropped_or_rescored_cases(self):
        old=self.report()
        new=copy.deepcopy(old)
        self.assertIsNone(publish.monotone(old,new))
        new["runs"][0]["tool_progress"]["iva"]["finished"]=0
        with self.assertRaisesRegex(ValueError,"regressed"):
            publish.monotone(old,new)
        new=copy.deepcopy(old)
        new["runs"][0]["samples"][0]["score"]["iva"]=999
        with self.assertRaisesRegex(ValueError,"scored"):
            publish.monotone(old,new)

    def test_source_arm_output_hash_and_image_verified(self):
        path=self.root/"synthetic"/"iva"
        path.mkdir(parents=True)
        (path/"conseq.csv").write_text("sequence\nACGT\n")
        image=IMAGES["iva"]
        record={"sha256":image,"status":"success",
                "argv":["podman",image,"--all_projects"],
                "score":4.,"seconds":7.,
                "score_origin":"micall_final_max_reference_panel_v1",
                "timing_origin":"micall_in_container_monotonic_v1",
                "exit_code":0,"final_dominant":{
                    "source_output":"conseq.csv",
                    "conseq_csv_sha256":inputs.sha(path/"conseq.csv")}}
        (path/"execution.json").write_text(json.dumps(record))
        self.assertEqual(inputs.synth_arm(path,"iva",image),record)
        (path/"conseq.csv").write_text("altered")
        with self.assertRaisesRegex(ValueError,"final MiCall output changed"):
            inputs.synth_arm(path,"iva",image)

    def test_physical_witness_binds_private_sample_without_exposing_it(self):
        pairs={"sample"+str(i):[{"sha256":f"{i+1:064x}","bytes":10},
              {"sha256":f"{i+2:064x}","bytes":20}] for i in range(198)}
        digest=hashlib.sha256(json.dumps(
            pairs,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        witness=self.root/"witness.json"
        anchor=self.root/"original.json"
        witness.write_text(json.dumps({"schema":
            "ivanka.assembler-bench.verified-original-fastq-pairs.v1",
            "samples":pairs,"input_pairs_sha256":digest}))
        anchor.write_text(json.dumps({"schema":
            "ivanka.assembler-bench.authentic-physical-inputs.v1",
            "input_pairs_sha256":digest}))
        self.assertEqual(inputs.physical_pairs(witness,anchor),pairs)
        pairs["sample0"][0]["sha256"]="a"*64
        witness.write_text(json.dumps({"schema":
            "ivanka.assembler-bench.verified-original-fastq-pairs.v1",
            "samples":pairs,"input_pairs_sha256":digest}))
        with self.assertRaisesRegex(ValueError,"witnesses differ"):
            inputs.physical_pairs(witness,anchor)

    def test_physical_arm_rejects_witness_drift(self):
        root=self.root/"real"
        (root/"artifacts"/"sample"/"iva").mkdir(parents=True)
        folder=root/"artifacts"/"sample"/"iva"
        (folder/"conseq.csv").write_text("sequence\nACGT\n")
        pair=[{"sha256":"1"*64},{"sha256":"2"*64}]
        name="PRIVATE_SOURCE_NAME"
        sub=root/"iva"/"checkpoints"
        sub.mkdir(parents=True)
        original={"image_id":IMAGES["iva"],"exit_code":0,
                  "seconds":7.,"artifact_dir":str(folder),
                  "metrics":{"outputs":{"conseq.csv":{
                      "sha256":inputs.sha(folder/"conseq.csv")}}}}
        record={"sample":name,"tool":"iva","image_id":IMAGES["iva"],
                "status":"finished","failed":False,
                "input_sha256":inputs.sha_bytes(("1"*64+"2"*64).encode()),
                "reference_panel_sha256":inputs.PANEL,
                "arm":original,"measurement":{"score":4.,"seconds":7.}}
        (sub/(inputs.sha_bytes(name.encode())+".json")).write_text(
            json.dumps(record))
        self.assertEqual(inputs.real_arm(root,"iva",name,IMAGES["iva"],pair)[
            "score"],4.)
        with self.assertRaisesRegex(ValueError,"original read pair"):
            inputs.real_arm(root,"iva",name,IMAGES["iva"],
                            [{"sha256":"3"*64},{"sha256":"2"*64}])

    def test_no_separate_rerun_ui(self):
        site=Path(__file__).resolve().parents[1]/"site/bench"
        html=(site/"index.html").read_text()
        js=(site/"app.js").read_text()
        self.assertNotIn("comparatorProgress",html)
        self.assertFalse((site/"comparator-progress.js").exists())
        self.assertFalse((site/"data/comparator-progress.json").exists())
        self.assertIn('id="toolProgress"',html)
        self.assertIn('run.tool_progress',js)


if __name__=="__main__":
    unittest.main()
