import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

spec=importlib.util.spec_from_file_location("podman_compare",Path(__file__).with_name("podman_full_micall.py"))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
class StrictCacheAuditTests(TestCase):
 def test_strict_iva_cache_audit_is_read_only_mode(self):
  from types import SimpleNamespace
  args=SimpleNamespace(mode="iva",cache_status=True,sample=None,
                       allow_missing_baseline=False,all_projects=True,
                       parallel_arms=False,jobs=10)
  m.validate_milestone198_preflight(args,m.milestone198.SAMPLE_COUNT,
      m.milestone198.MANIFEST_SHA256,m.milestone198.IVA_IMAGE_SHA256)
  with self.assertRaisesRegex(ValueError,"immutable original IVA"):
   m.validate_milestone198_preflight(args,m.milestone198.SAMPLE_COUNT,
       m.milestone198.MANIFEST_SHA256,"incorrect-image-id")
  with self.assertRaisesRegex(ValueError,"pinned full cohort"):
   m.validate_milestone198_preflight(args,m.milestone198.SAMPLE_COUNT,
       "incorrect-manifest",m.milestone198.IVA_IMAGE_SHA256)
  args.all_projects=False
  with self.assertRaisesRegex(ValueError,"pinned full cohort"):
   m.validate_milestone198_preflight(args,m.milestone198.SAMPLE_COUNT,
       m.milestone198.MANIFEST_SHA256,m.milestone198.IVA_IMAGE_SHA256)

 def test_frozen_panel_requires_exact_digest_and_count(self):
  m.validate_milestone198_panel(33,m.milestone198.PANEL_SHA256)
  with self.assertRaisesRegex(ValueError,"frozen 33-reference panel"):
   m.validate_milestone198_panel(32,m.milestone198.PANEL_SHA256)
  with self.assertRaisesRegex(ValueError,"frozen 33-reference panel"):
   m.validate_milestone198_panel(33,"incorrect-panel")

 def test_execution_cannot_use_iva_mode(self):
  from types import SimpleNamespace
  args=SimpleNamespace(mode="iva",cache_status=False,sample=None,
                       allow_missing_baseline=False,all_projects=True,
                       parallel_arms=False,jobs=10)
  with self.assertRaisesRegex(ValueError,"execution must be Ivanka-only"):
   m.validate_milestone198_preflight(args,m.milestone198.SAMPLE_COUNT,
       m.milestone198.MANIFEST_SHA256,m.milestone198.IVA_IMAGE_SHA256)
  args.mode="ivanka"
  m.validate_milestone198_preflight(args,m.milestone198.SAMPLE_COUNT,
      m.milestone198.MANIFEST_SHA256,m.milestone198.IVA_IMAGE_SHA256)


class BenchmarkTests(TestCase):
 def test_executed_images_are_pinned_by_id(self):
  configured={"iva":"test/iva:mutable","ivanka":"test/ivanka:mutable"}
  verified={"iva":"a"*64,"ivanka":"b"*64}
  self.assertEqual(m.pinned_run_images(configured,verified,verified["iva"]),verified)
  self.assertEqual(m.pinned_run_images(configured,{"ivanka":verified["ivanka"]},verified["iva"]),verified)
  self.assertEqual(m.pinned_run_images(configured,{"iva":verified["iva"]},verified["iva"])["iva"],verified["iva"])
 def test_immutable_image_id_avoids_redundant_inspect(self):
  from unittest.mock import patch
  immutable="a"*64
  with patch.object(m,"image_id",side_effect=AssertionError("unexpected inspect")):
   self.assertEqual(m.recorded_image_id(immutable),immutable)
  with patch.object(m,"image_id",return_value="b"*64) as inspect:
   self.assertEqual(m.recorded_image_id("image:mutable"),"b"*64)
   inspect.assert_called_once_with("image:mutable")
  with patch.object(m,"image_id",return_value="c"*64) as inspect:
   self.assertEqual(m.recorded_image_id("A"*64),"c"*64)
   inspect.assert_called_once()

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
  with TemporaryDirectory() as d, patch.object(m, "IVA_BASELINE_CACHE", Path(d)/"cache"):
   artifacts=Path(d)/"baseline-artifacts"
   artifacts.mkdir()
   conseq=artifacts/"conseq.csv"
   conseq.write_text("consensus-percent-cutoff,sequence\nMAX,ACGT\n")
   prov={"iva_image_id":"sha256:a","hxb2_sha256":"sha256:b",
         "fastq_sha256":["x","y"],"micall_project_code":""}
   arm={"exit_code":0,"image_id":"sha256:a","artifact_dir":str(artifacts),"metrics":{
     "best_hxb2_final_max_conseq_score":1000,"num_final_max_conseqs":1,
     "outputs":{"conseq.csv":{"exists":True,"rows":1,"sha256":m.sha(conseq)}}}}
   m.save_iva_baseline("S1",prov,arm)
   self.assertEqual((Path(d)/"cache").stat().st_mode & 0o777, 0o700)
   self.assertEqual((Path(d)/"cache"/"S1").stat().st_mode & 0o777, 0o700)
   self.assertEqual((Path(d)/"cache"/"S1"/"conseq.csv").stat().st_mode & 0o777, 0o600)
   self.assertEqual((Path(d)/"cache"/"S1"/"baseline.json").stat().st_mode & 0o777, 0o600)
   stored=m.load_iva_baseline("S1",prov)
   self.assertEqual(stored["exit_code"],0)
   self.assertEqual(stored["source_artifact_dir"],str(artifacts))
   self.assertNotEqual(stored["artifact_dir"],str(artifacts))
   conseq.write_text("consensus-percent-cutoff,sequence\nMAX,AAAA\n")
   self.assertEqual(m.load_iva_baseline("S1",prov),stored)
   cached=Path(stored["artifact_dir"])/"conseq.csv"
   cached.write_text("consensus-percent-cutoff,sequence\nMAX,AAAA\n")
   with self.assertRaisesRegex(ValueError,"final MAX artifact"):
    m.load_iva_baseline("S1",prov)
   cached.unlink()
   with self.assertRaisesRegex(ValueError,"final MAX artifact"):
    m.load_iva_baseline("S1",prov)
   with self.assertRaisesRegex(ValueError,"provenance"):
    m.load_iva_baseline("S1",prov | {"iva_image_id":"sha256:DIFFERENT"})
   with self.assertRaisesRegex(ValueError,"image ID"):
    m.save_iva_baseline("S1",prov,arm | {"image_id":"sha256:WRONG"})
   with self.assertRaisesRegex(ValueError,"No verified IVA baseline"):
    m.load_iva_baseline("S2",prov)
 def test_wrong_assembler_binding_fails_closed(self):
  from unittest.mock import patch
  from subprocess import CalledProcessError
  with patch.object(m.subprocess, "run", side_effect=CalledProcessError(1, "podman")) as runner:
   with self.assertRaisesRegex(ValueError, "executable-binding"):
    m.verify_ivanka_image_binding("image:tag")
  self.assertIn("podman", runner.call_args.args[0])
  self.assertIn("run_subprocess", runner.call_args.args[0][-1])

 def test_base_layers_must_match(self):
  from unittest.mock import patch
  layers={"iva":["a","b"],"ivanka":["a","b","c"],"foreign":["x","y"]}
  with patch.object(m,"image_layers",side_effect=lambda name:layers[name]), \
       patch.object(m.subprocess,"run") as verifier:
   m.verify_identical_micall_base("iva","ivanka")
   verifier.assert_not_called()
   m.verify_ivanka_image_binding("ivanka")
   verifier.assert_called_once()
   self.assertEqual(verifier.call_args.args[0][6], "ivanka")
   self.assertEqual(verifier.call_args.kwargs["timeout"], 180)
   with self.assertRaisesRegex(ValueError,"does not derive"):
    m.verify_identical_micall_base("iva","foreign")
 def test_slow_image_startup_fails_closed_without_misdiagnosing_binding(self):
  from unittest.mock import patch
  from subprocess import TimeoutExpired
  with patch.object(m.subprocess,"run",side_effect=TimeoutExpired(["podman","run"],180)):
   with self.assertRaisesRegex(ValueError,"Timed out waiting"):
    m.verify_ivanka_image_binding("ivanka")
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
    self.assertEqual(args[1],{"iva":"sha256:base","ivanka":"sha256:base"})
    return {"sample":row["sample"],"status":"finished","failed":False}
   with patch.object(m,"DATA",root),patch.object(m,"RESULTS",destination), \
        patch.object(m,"image_id",return_value="sha256:base"), \
        patch.object(m,"load_micall_projects",return_value=({}, "test-catalog")), \
        patch("reference_panel.build_reference_panel",return_value=(("HXB2","ACGT"),)), \
        patch.object(m,"verify_identical_micall_base"), \
        patch.object(m,"verify_ivanka_image_binding"), \
        patch.object(m,"sha",return_value="abc"), \
        patch.object(m,"evaluate_sample",side_effect=fake_sample), \
        patch.object(sys,"argv",["benchmark","--mode","both","--jobs","2"]):
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

 def test_failure_categories_do_not_confuse_unscorable_iva_with_ivanka_failure(self):
  record={"failed":True,"status":"error",
          "iva":{"exit_code":0,"metrics":{"num_final_max_conseqs":0}},
          "ivanka":{"exit_code":0,"metrics":{"num_final_max_conseqs":1}}}
  self.assertEqual(m.failure_category(record),"iva_no_final_max")
  record["iva"]["metrics"]["num_final_max_conseqs"]=1
  record["best_contig_acceptance"]={"pass":False}
  self.assertEqual(m.failure_category(record),"ivanka_below_noninferiority_threshold")
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
   def successful_internal_run(*args, **kwargs):
    path=root/"out"/"invocation"/"TEST"/"ivanka"/"micall_internal_timing.json"
    path.write_text('{"timing_origin":"micall_in_container_monotonic_v1","seconds":0.125,"exit_code":0}')
    return Mock(returncode=0)
   with patch.object(m,"DATA",root),patch.object(m,"RESULTS",root/"out"), \
        patch.object(m,"image_id",return_value="sha256:img"), \
        patch.object(m,"score_outputs",return_value={"outputs":{}}), \
        patch.object(m.subprocess,"run",side_effect=successful_internal_run) as runner:
    result=m.run_arm({"sample":"TEST"},"ivanka","image:tag","ACGT",123,"invocation",all_projects=True)
   argv=runner.call_args_list[0].args[0]
   self.assertEqual(argv[argv.index("--entrypoint")+1],"python")
   self.assertEqual(argv[argv.index("--timeout")+1],"121")
   self.assertEqual(argv[argv.index("--stop-timeout")+1],"2")
   self.assertNotIn("108s",argv)
   self.assertIn("micall",argv)
   self.assertIn("/ivanka-timer.py",argv)
   self.assertIn("--all_projects",argv)
   self.assertEqual(result["exit_code"],0)
   self.assertEqual(result["seconds"],0.125)
   self.assertEqual(result["timing_origin"],"micall_in_container_monotonic_v1")
   self.assertGreaterEqual(result["container_wall_seconds"],0)

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

 def test_parallel_iva_and_ivanka_arms_keep_separate_results(self):
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
       patch("reference_panel.panel_acceptance",return_value={"pass":True,"iva_score":100,"ivanka_score":99}) as scorer:
   result=m.evaluate_sample({"sample":"S","project":"NFLHIVDNA"},args,{"iva":"A","ivanka":"B"},
           {"iva":"hashA","ivanka":"hashB"},"base-id","refhash","ACGT",None,"inv",
           time.monotonic()+5)
  self.assertFalse(result["failed"])
  self.assertEqual(runner.call_count,2)
  self.assertTrue(result["best_contig_acceptance"]["pass"])
  self.assertEqual(result["iva"]["metrics"]["best_hxb2_final_max_conseq_score"],100)
  self.assertEqual(result["ivanka"]["metrics"]["best_hxb2_final_max_conseq_score"],99)

 def test_missing_iva_can_run_ivanka_diagnostic_but_never_pass(self):
  import time
  from types import SimpleNamespace
  from unittest.mock import patch
  args=SimpleNamespace(mode="ivanka",timeout_per_arm=6,parallel_arms=False,allow_missing_baseline=True)
  with patch.object(m,"baseline_provenance",return_value={"verified":True}), \
       patch.object(m,"load_iva_baseline",side_effect=ValueError("missing control")), \
       patch.object(m,"run_arm",return_value={"exit_code":0,"metrics":{"best_hxb2_final_max_conseq_score":1000,"outputs":{}}}) as runner:
   r=m.evaluate_sample({"sample":"S"},args,{"ivanka":"img"},{"ivanka":"hash"},"base","hxb2","ACGT",None,"inv",time.monotonic()+20)
  self.assertTrue(r["failed"])
  self.assertEqual(r["ivanka"]["exit_code"],0)
  self.assertIn("baseline_error",r)
  self.assertNotIn("best_contig_acceptance",r)
  self.assertEqual(runner.call_count,1)


 def test_qualification_enforces_thirty_minutes_per_sample(self):
  self.assertTrue(m.qualification_within_cap(1800,1800))
  self.assertTrue(m.qualification_within_cap(1780,1779))
  self.assertFalse(m.qualification_within_cap(1801,100))
  self.assertFalse(m.qualification_within_cap(1790,1791))
  self.assertFalse(m.qualification_within_cap(0,100))
  self.assertFalse(m.qualification_within_cap(1800,-1))

 def test_project_aware_comparison_uses_full_consensus_not_hxb2(self):
  with TemporaryDirectory() as d:
   root=Path(d)
   for arm,seq in (("iva","ACGT"*100),("ivanka","TTTT"*100)):
    folder=root/arm
    folder.mkdir()
    (folder/"conseq.csv").write_text(
        "region,consensus-percent-cutoff,sequence\n"
        "synthetic,MAX,"+seq+"\n")
   result=m.project_aware_acceptance(root/"iva",root/"ivanka")
   self.assertFalse(result["pass"])
   self.assertEqual(result["iva_score"],400)
   self.assertEqual(result["method"],"final_iva_max_consensus_global_alignment")

 def test_project_aware_requires_near_full_length_matching_contig(self):
  with TemporaryDirectory() as d:
   root=Path(d)
   seq="ACGT"*100
   for arm in ("iva","ivanka"):
    folder=root/arm
    folder.mkdir()
    (folder/"conseq.csv").write_text(
        "region,consensus-percent-cutoff,sequence\n"
        "synthetic,MAX,"+seq+"\n")
   self.assertTrue(m.project_aware_acceptance(root/"iva",root/"ivanka")["pass"])
   (root/"ivanka"/"conseq.csv").write_text(
       "region,consensus-percent-cutoff,sequence\n"
       "synthetic,MAX,"+seq[:100]+"\n")
   self.assertFalse(m.project_aware_acceptance(root/"iva",root/"ivanka")["pass"])

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
        patch.object(m,"load_micall_projects",return_value=({}, "test-catalog")), \
        patch("reference_panel.build_reference_panel",return_value=(("HXB2","ACGT"),)), \
        patch.object(m,"verify_identical_micall_base"), \
        patch.object(m,"verify_ivanka_image_binding"), \
        patch.object(m,"sha",return_value="sample-hash"), \
        patch.object(m,"evaluate_sample",side_effect=fake_case), \
        patch.object(m,"iva_cache_status",return_value={"verified":[],"missing_or_invalid":[]}), \
        patch.object(m.time,"time",side_effect=[1234,1235]):
    with patch.object(sys,"argv",["bench","--mode","ivanka"]):
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


 def test_import_successful_iva_even_if_ivanka_pipeline_failed(self):
  import json
  from unittest.mock import patch
  with TemporaryDirectory() as d:
   root=Path(d)
   original=root/"prior"
   original.mkdir()
   artifacts=original/"inv"/"S1"/"iva"
   artifacts.mkdir(parents=True)
   conseq=artifacts/"conseq.csv"
   conseq.write_text("consensus-percent-cutoff,sequence\nMAX,ACGT\n")
   provenance={"iva_image_id":"id","hxb2_sha256":"ref",
               "fastq_sha256":["fastq1","fastq2"],"micall_project_code":"", "all_projects":True}
   arm={"exit_code":0,"image_id":"id","artifact_dir":str(artifacts),"metrics":{
    "num_final_max_conseqs":1,
    "outputs":{"conseq.csv":{"sha256":m.sha(conseq)}}}}
   (original/"results.jsonl").write_text(json.dumps({
    "status":"error","failed":True,"sample":"S1","provenance":provenance,"iva":arm})+"\n")
   with patch.object(m,"IVA_BASELINE_CACHE",root/"cache"), \
        patch.object(m,"baseline_provenance",return_value=provenance) as evidence:
    result=m.import_iva_baselines([original],[{"sample":"S1"}],"id","ref",True)
    self.assertEqual(result["imported"],1)
    self.assertEqual(result["rejected"],0)
    self.assertEqual(evidence.call_args.args[3],True)
    imported=m.load_iva_baseline("S1",provenance)
    self.assertEqual(Path(imported["artifact_dir"]).joinpath("conseq.csv").read_text(),conseq.read_text())
    conseq.unlink()
    self.assertEqual(m.load_iva_baseline("S1",provenance),imported)
    self.assertEqual(m.import_iva_baselines([original],[{"sample":"S1"}],"id","ref",True)["imported"],0)
    self.assertEqual(m.iva_cache_status([{"sample":"S1"}],"id","ref",True)["verified"],["S1"])

 def test_cached_iva_qualification_accepts_all_original_eighteen_without_control_execution(self):
  import json
  import sys
  from unittest.mock import patch
  with TemporaryDirectory() as d:
   root=Path(d)
   (root/"manifest.tsv").write_text("sample\n"+"".join("S"+str(i)+"\n" for i in range(18)))
   (root/"hxb2.fasta").write_text(">HXB2\nACGT\n")
   results=root/"results"
   def fake_case(row,*args,**kwargs):
    return {"sample":row["sample"],"status":"finished","failed":False,
            "iva_baseline_reused":True,
            "iva":{"exit_code":0,"metrics":{"num_final_max_conseqs":1}},
            "ivanka":{"exit_code":0,"metrics":{"num_final_max_conseqs":1}},
            "total_seconds":1799,
            "best_contig_acceptance":{"pass":True}}
   with patch.object(m,"DATA",root),patch.object(m,"RESULTS",results), \
        patch.object(m,"image_id",return_value="sha256:base"), \
        patch.object(m,"load_micall_projects",return_value=({},"catalog")), \
        patch("reference_panel.build_reference_panel",return_value=(("HXB2","ACGT"),)), \
        patch.object(m,"verify_identical_micall_base"), \
        patch.object(m,"verify_ivanka_image_binding"), \
        patch.object(m,"verify_iva_eligibility",return_value={"eligibility_verified":True}), \
        patch.object(m,"iva_cache_status",return_value={"verified":["all"],"missing_or_invalid":[]}), \
        patch.object(m,"sha",return_value="manifest-hash"), \
        patch.object(m,"evaluate_sample",side_effect=fake_case), \
        patch.dict(m.os.environ,{"IVANKA_EXPECTED_MANIFEST_SHA256":"manifest-hash"}), \
        patch.object(sys,"argv",["benchmark","--qualify","--mode","ivanka","--jobs","10",
                                "--sample-time-limit","1800","--timeout-per-arm","1780"]):
    self.assertEqual(m.main(),0)
   summary=json.loads(list(results.glob("summary-*.json"))[0].read_text())
   self.assertEqual(summary["selected_samples"],18)
   self.assertEqual(summary["accepted_samples"],18)
   self.assertTrue(summary["cached_iva_comparison_pass"])
   self.assertFalse(summary["full_alpha_pass"])
   self.assertEqual(summary["jobs"],10)
   self.assertEqual(summary["sample_limit_seconds"],1800)
