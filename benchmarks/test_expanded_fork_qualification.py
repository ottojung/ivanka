"""Independent seven-way gate must not upgrade partial or malformed evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expanded import fork_qualification as gate
from expanded.adapters import ASSEMBLERS


class DedicatedQualificationTests(unittest.TestCase):
    def fixture(self, root):
        root = Path(root)
        att = root/"att.json"
        images = {tool: f"{index+1:x}"*64
                  for index, tool in enumerate(ASSEMBLERS)}
        proof = {"schema": gate.SCHEMA, "images": {
            tool: {"source_commit": format(index+1,"x")*40}
            for index, tool in enumerate(ASSEMBLERS)}}
        att.write_text(json.dumps(proof))
        synth = root/"synthetic"
        synth.mkdir()
        (synth/"run_manifest.json").write_text("{}")
        return att, proof, images, synth

    def call(self, root, att, proof, images, synth, cases, finished):
        counter = {name: {"finished": finished, "failed": 0}
                   for name in ASSEMBLERS if name != "iva"}
        physical = {"run_manifest_sha256": "a"*64, "candidates": counter}
        frozen = {"images": images}
        with (patch.object(gate,"checked",return_value=(
                  frozen,cases,"sha",proof)),
              patch.object(gate,"snapshot",return_value=physical),
              patch.object(gate,"sample_aliases",return_value={"private":"R001"}),
              patch.object(gate,"join_real_runs",return_value=[{
                  "id":"private", "cohort":"real"}]) as join,
              patch.object(gate,"summarize_gate",return_value={
                  "pass":True,"errors":[]}) as summary):
            result=gate.evaluate(
                synth,root/"real",root/"data",root/"runner",
                att,root/"sources","b"*64)
        return result,join,summary

    def test_partial_synthetic_and_real_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            att,proof,images,synth=self.fixture(folder)
            result,join,summary=self.call(
                Path(folder),att,proof,images,synth,[],198)
            self.assertEqual(result["status"],"incomplete")
            self.assertFalse(result["pass"])
            join.assert_not_called()
            summary.assert_not_called()
            result,join,summary=self.call(
                Path(folder),att,proof,images,synth,[{}]*400,197)
            self.assertFalse(result["pass"])
            join.assert_not_called()
            summary.assert_not_called()

    def test_all_verified_cohorts_are_submitted_without_private_sample_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            att,proof,images,synth=self.fixture(folder)
            result,join,summary=self.call(
                Path(folder),att,proof,images,synth,[{}]*400,198)
            self.assertEqual(result["status"],"passed")
            self.assertTrue(result["pass"])
            self.assertEqual(result["provenance"]["unique_fork_commits"],7)
            rows=summary.call_args.args[0]
            self.assertEqual(len(rows),401)
            self.assertEqual(rows[-1]["id"],"R001")
            join.assert_called_once()

    def test_shared_source_commit_never_qualifies(self):
        with tempfile.TemporaryDirectory() as folder:
            att,proof,images,synth=self.fixture(folder)
            old=proof["images"]["iva"]["source_commit"]
            proof["images"]["ivanka"]["source_commit"]=old
            att.write_text(json.dumps(proof))
            with self.assertRaisesRegex(ValueError,"seven distinct"):
                self.call(Path(folder),att,proof,images,synth,[{}]*400,198)
            proof["schema"]="shared-commit"
            att.write_text(json.dumps(proof))
            with self.assertRaisesRegex(ValueError,"seven dedicated"):
                self.call(Path(folder),att,proof,images,synth,[{}]*400,198)

    def test_invalid_physical_pair_cannot_reach_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            att,proof,images,synth=self.fixture(root)
            counter={tool:{"finished":198,"failed":0}
                     for tool in ASSEMBLERS if tool!="iva"}
            with (patch.object(gate,"checked",return_value=(
                      {"images":images},[{}]*400,"sha",proof)),
                  patch.object(gate,"snapshot",return_value={
                      "run_manifest_sha256":"a"*64,"candidates":counter}),
                  patch.object(gate,"join_real_runs",
                      side_effect=ValueError("private sample: image differs")),
                  patch.object(gate,"summarize_gate") as summary):
                result=gate.evaluate(synth,root/"real",root/"data",
                    root/"runner",att,root/"sources","b"*64)
            self.assertFalse(result["pass"])
            self.assertEqual(result["status"],"invalid-physical-evidence")
            self.assertNotIn("private sample",json.dumps(result))
            summary.assert_not_called()


if __name__=="__main__":
    unittest.main()
