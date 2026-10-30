import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

spec=importlib.util.spec_from_file_location("podman_compare",Path(__file__).with_name("podman_full_micall.py"))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class BenchmarkTests(TestCase):
 def test_best_conseq(self):
  with TemporaryDirectory() as d:
   p=Path(d)/"scratch"
   p.mkdir()
   (p/"conseq.csv").write_text("seed,consensus-percent-cutoff,sequence\na,MAX,TTTT\nb,MAX,ACGT\nc,0.5,ACGT\n")
   s=m.score_outputs(Path(d),"ACGT")
   self.assertEqual(s["best_hxb2_final_max_conseq_score"],4.0)
   self.assertEqual(s["num_final_max_conseqs"],2)
 def test_output_differences_are_explicit(self):
  left={"outputs":{"conseq.csv":{"exists":True,"rows":2,"sha256":"abc"}}}
  right={"outputs":{"conseq.csv":{"exists":True,"rows":3,"sha256":"def"}}}
  d=m.compare_outputs(left,right)["conseq.csv"]
  self.assertEqual(d["row_delta"],1)
  self.assertFalse(d["same_sha256"])
 def test_verified_iva_baseline_roundtrip(self):
  from unittest.mock import patch
  with TemporaryDirectory() as d, patch.object(m, "RESULTS", Path(d)):
   prov={"iva_image_id":"sha256:a","hxb2_sha256":"sha256:b",
         "fastq_sha256":["x","y"],"micall_project_code":""}
   arm={"exit_code":0,"metrics":{
     "best_hxb2_final_max_conseq_score":1000,"num_final_max_conseqs":1,
     "outputs":{"conseq.csv":{"exists":True,"rows":1,"sha256":"x"}}}}
   m.save_iva_baseline("S1",prov,arm)
   self.assertEqual(m.load_iva_baseline("S1",prov),arm)
   with self.assertRaisesRegex(ValueError,"provenance"):
    m.load_iva_baseline("S1",prov | {"iva_image_id":"sha256:DIFFERENT"})
   with self.assertRaisesRegex(ValueError,"No verified IVA baseline"):
    m.load_iva_baseline("S2",prov)
 def test_base_layers_must_match(self):
  from unittest.mock import patch
  layers={"iva":["a","b"],"riva":["a","b","c"],"foreign":["x","y"]}
  with patch.object(m,"image_layers",side_effect=lambda name:layers[name]):
   m.verify_identical_micall_base("iva","riva")
   with self.assertRaisesRegex(ValueError,"does not derive"):
    m.verify_identical_micall_base("iva","foreign")
 def test_missing_conseq(self):
  with TemporaryDirectory() as d:
   self.assertIsNone(m.score_outputs(Path(d),"ACGT")["best_hxb2_final_max_conseq_score"])

 def test_negative_iva_baseline_uses_absolute_threshold(self):
  self.assertTrue(m.best_consensus_acceptance(-120,-119)["pass"])
  self.assertFalse(m.best_consensus_acceptance(-120,-121)["pass"])
  self.assertEqual(m.best_consensus_acceptance(-120,-119)["threshold"],-120)

 def test_positive_iva_baseline_requires_95_percent(self):
  self.assertTrue(m.best_consensus_acceptance(1000,950)["pass"])
  self.assertFalse(m.best_consensus_acceptance(1000,949)["pass"])
  self.assertFalse(m.best_consensus_acceptance(1000,None)["pass"])

 def test_missing_iva_baseline_fails(self):
  self.assertFalse(m.best_consensus_acceptance(None,1000)["pass"])

 def test_parallel_runner_emits_parseable_jsonl(self):
  import json
  import sys
  from unittest.mock import patch
  with TemporaryDirectory() as d:
   root=Path(d)
   (root/"manifest.tsv").write_text("sample\nA\nB\n")
   (root/"hxb2.fasta").write_text(">reference\nACGT\n")
   destination=root/"results"
   def fake_sample(row,*args,**kwargs):
    return {"sample":row["sample"],"status":"finished","failed":False}
   with patch.object(m,"DATA",root),patch.object(m,"RESULTS",destination), \
        patch.object(m,"image_id",return_value="sha256:base"), \
        patch.object(m,"verify_identical_micall_base"), \
        patch.object(m,"sha",return_value="abc"), \
        patch.object(m,"evaluate_sample",side_effect=fake_sample), \
        patch.object(sys,"argv",["benchmark","--jobs","2"]):
    self.assertEqual(m.main(),0)
   events=[json.loads(line) for line in (destination/"results.jsonl").read_text().splitlines()]
   self.assertEqual(len(events),4)
   self.assertEqual(sum(e["status"]=="started" for e in events),2)
   self.assertEqual(sum(e["status"]=="finished" for e in events),2)
   summaries=list(destination.glob("summary-*.json"))
   self.assertEqual(len(summaries),1)
   summary=json.loads(summaries[0].read_text())
   self.assertFalse(summary["full_alpha_pass"])
   self.assertFalse(summary["cached_iva_comparison_pass"])
   self.assertEqual(summary["selected_samples"],2)

 def test_failure_categories_do_not_confuse_unscorable_iva_with_riva_failure(self):
  record={"failed":True,"status":"error",
          "iva":{"exit_code":0,"metrics":{"num_final_max_conseqs":0}},
          "riva":{"exit_code":0,"metrics":{"num_final_max_conseqs":1}}}
  self.assertEqual(m.failure_category(record),"iva_no_final_max")
  record["iva"]["metrics"]["num_final_max_conseqs"]=1
  record["best_contig_acceptance"]={"pass":False}
  self.assertEqual(m.failure_category(record),"riva_below_noninferiority_threshold")
  record["best_contig_acceptance"]["pass"]=True
  record["failed"]=False
  self.assertIsNone(m.failure_category(record))

 def test_run_arm_enforces_timeout_inside_container(self):
  from unittest.mock import patch,Mock
  with TemporaryDirectory() as d:
   root=Path(d)
   fq=root/"samples"/"TEST"
   fq.mkdir(parents=True)
   for end in (1,2):
    (fq/f"TEST_L001_R{end}_001.fastq.gz").write_bytes(b"placeholder")
   with patch.object(m,"DATA",root),patch.object(m,"RESULTS",root/"out"), \
        patch.object(m,"image_id",return_value="sha256:img"), \
        patch.object(m,"score_outputs",return_value={"outputs":{}}), \
        patch.object(m.subprocess,"run",return_value=Mock(returncode=0)) as runner:
    result=m.run_arm({"sample":"TEST"},"riva","image:tag","ACGT",123,"invocation",all_projects=True)
   argv=runner.call_args.args[0]
   self.assertEqual(argv[argv.index("--entrypoint")+1],"/usr/bin/timeout")
   self.assertEqual(argv[argv.index("--timeout")+1],"121")
   self.assertEqual(argv[argv.index("--stop-timeout")+1],"2")
   self.assertIn("108s",argv)
   self.assertIn("micall",argv)
   self.assertIn("--all_projects",argv)
   self.assertEqual(result["exit_code"],0)

 def test_depth_metrics_streamed_from_final_micall_report(self):
  with TemporaryDirectory() as d:
   root=Path(d)
   (root/"genome_coverage.csv").write_text("coverage\n0\n9\n10\n120\n")
   depth=m.score_outputs(root,"ACGT")["coverage_depth"]
   self.assertEqual(depth["positions"],4)
   self.assertEqual(depth["covered_positions"],3)
   self.assertEqual(depth["positions_ge_10"],2)
   self.assertEqual(depth["positions_ge_100"],1)
   self.assertEqual(depth["mean_depth"],34.75)

 def test_coverage_breadth_deduplicates_multiple_contigs(self):
  with TemporaryDirectory() as d:
   root=Path(d)
   (root/"genome_coverage.csv").write_text(
      "coordinates,refseq_nuc_pos,coverage\n"
      "HXB2,1,15\nHXB2,1,20\nHXB2,2,8\nHXB2,3,0\n")
   depth=m.score_outputs(root,"ACGT")["coverage_depth"]
   self.assertEqual(depth["covered_positions"],3)
   self.assertEqual(depth["unique_reference_positions_covered"],2)
   self.assertEqual(depth["unique_reference_positions_ge_10"],1)

 def test_parallel_iva_and_riva_arms_keep_separate_results(self):
  import time
  from types import SimpleNamespace
  from unittest.mock import patch
  args=SimpleNamespace(mode="both",timeout_per_arm=3,parallel_arms=True)
  def fake_arm(row,arm,*arguments):
   score=100 if arm=="iva" else 99
   return {"exit_code":0,"metrics":{
     "best_hxb2_final_max_conseq_score":score,"outputs":{}}}
  with patch.object(m,"baseline_provenance",return_value={"verified":True}), \
       patch.object(m,"save_iva_baseline"), \
       patch.object(m,"run_arm",side_effect=fake_arm) as runner, \
       patch("reference_panel.panel_acceptance",return_value={"pass":True,"iva_score":100,"riva_score":99}) as scorer:
   result=m.evaluate_sample({"sample":"S","project":"NFLHIVDNA"},args,{"iva":"A","riva":"B"},
           {"iva":"hashA","riva":"hashB"},"base-id","refhash","ACGT",None,"inv",
           time.monotonic()+5)
  self.assertFalse(result["failed"])
  self.assertEqual(runner.call_count,2)
  self.assertTrue(result["best_contig_acceptance"]["pass"])
  self.assertEqual(result["iva"]["metrics"]["best_hxb2_final_max_conseq_score"],100)
  self.assertEqual(result["riva"]["metrics"]["best_hxb2_final_max_conseq_score"],99)

 def test_missing_iva_can_run_riva_diagnostic_but_never_pass(self):
  import time
  from types import SimpleNamespace
  from unittest.mock import patch
  args=SimpleNamespace(mode="riva",timeout_per_arm=6,parallel_arms=False,allow_missing_baseline=True)
  with patch.object(m,"baseline_provenance",return_value={"verified":True}), \
       patch.object(m,"load_iva_baseline",side_effect=ValueError("missing control")), \
       patch.object(m,"run_arm",return_value={"exit_code":0,"metrics":{"best_hxb2_final_max_conseq_score":1000,"outputs":{}}}) as runner:
   r=m.evaluate_sample({"sample":"S"},args,{"riva":"img"},{"riva":"hash"},"base","hxb2","ACGT",None,"inv",time.monotonic()+20)
  self.assertTrue(r["failed"])
  self.assertEqual(r["riva"]["exit_code"],0)
  self.assertIn("baseline_error",r)
  self.assertNotIn("best_contig_acceptance",r)
  self.assertEqual(runner.call_count,1)


 def test_qualification_enforces_twenty_minutes_per_sample(self):
  self.assertTrue(m.qualification_within_cap(1200,1200))
  self.assertTrue(m.qualification_within_cap(1180,1179))
  self.assertFalse(m.qualification_within_cap(1201,100))
  self.assertFalse(m.qualification_within_cap(1190,1191))
  self.assertFalse(m.qualification_within_cap(0,100))
  self.assertFalse(m.qualification_within_cap(1200,-1))

 def test_project_aware_comparison_uses_full_consensus_not_hxb2(self):
  with TemporaryDirectory() as d:
   root=Path(d)
   for arm,seq in (("iva","ACGT"*100),("riva","TTTT"*100)):
    folder=root/arm
    folder.mkdir()
    (folder/"conseq.csv").write_text(
        "region,consensus-percent-cutoff,sequence\n"
        "synthetic,MAX,"+seq+"\n")
   result=m.project_aware_acceptance(root/"iva",root/"riva")
   self.assertFalse(result["pass"])
   self.assertEqual(result["iva_score"],400)
   self.assertEqual(result["method"],"final_iva_max_consensus_global_alignment")

 def test_project_aware_requires_near_full_length_matching_contig(self):
  with TemporaryDirectory() as d:
   root=Path(d)
   seq="ACGT"*100
   for arm in ("iva","riva"):
    folder=root/arm
    folder.mkdir()
    (folder/"conseq.csv").write_text(
        "region,consensus-percent-cutoff,sequence\n"
        "synthetic,MAX,"+seq+"\n")
   self.assertTrue(m.project_aware_acceptance(root/"iva",root/"riva")["pass"])
   (root/"riva"/"conseq.csv").write_text(
       "region,consensus-percent-cutoff,sequence\n"
       "synthetic,MAX,"+seq[:100]+"\n")
   self.assertFalse(m.project_aware_acceptance(root/"iva",root/"riva")["pass"])

 def test_cached_control_never_claims_two_arm_alpha(self):
  import json
  import sys
  from unittest.mock import patch
  with TemporaryDirectory() as d:
   root=Path(d)
   samples="".join(f"S{i}\n" for i in range(7))
   (root/"manifest.tsv").write_text("sample\n"+samples)
   (root/"hxb2.fasta").write_text(">HXB2\nACGT\n")
   results=root/"results"
   def fake_case(row,*args,**kwargs):
    return {"sample":row["sample"],"status":"finished","failed":False,
            "best_contig_acceptance":{"pass":True}}
   with patch.object(m,"DATA",root),patch.object(m,"RESULTS",results), \
        patch.object(m,"image_id",return_value="sha256:fixed"), \
        patch.object(m,"verify_identical_micall_base"), \
        patch.object(m,"sha",return_value="sample-hash"), \
        patch.object(m,"evaluate_sample",side_effect=fake_case), \
        patch.object(m.time,"time",side_effect=[1234,1235]):
    with patch.object(sys,"argv",["bench","--mode","riva"]):
     self.assertEqual(m.main(),0)
    cached=json.loads(list(results.glob("summary-*.json"))[0].read_text())
    self.assertFalse(cached["cached_iva_comparison_pass"])
    self.assertFalse(cached["full_alpha_pass"])
    with patch.object(sys,"argv",["bench","--mode","both"]):
     self.assertEqual(m.main(),0)
   summaries=[json.loads(p.read_text()) for p in results.glob("summary-*.json")]
   paired=next(r for r in summaries if r["mode"]=="both")
   self.assertFalse(paired["full_alpha_pass"])
   self.assertFalse(paired["cached_iva_comparison_pass"])
