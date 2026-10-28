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
 def test_missing_conseq(self):
  with TemporaryDirectory() as d:
   self.assertIsNone(m.score_outputs(Path(d),"ACGT")["best_hxb2_final_max_conseq_score"])
