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
     "best_hxb2_final_max_conseq_score":1000,
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
