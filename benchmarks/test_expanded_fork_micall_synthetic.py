"""Source-authenticated synthetic execution keeps historical runners frozen."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expanded import fork_micall_synthetic as runner
from expanded.adapters import ASSEMBLERS


class SourceVerifiedForkRunnerTests(unittest.TestCase):
    def setUp(self):
        self.images = {name: (f"{i+1:x}"*64)[:64]
                       for i, name in enumerate(ASSEMBLERS)}

    def test_labels_alone_cannot_be_trusted(self):
        with tempfile.TemporaryDirectory() as folder:
            proof = Path(folder)/"attestation.json"
            proof.write_text(json.dumps({"images": {"iva": {}}}))
            with patch.object(runner, "verify", return_value={
                    "images": self.images}):
                with self.assertRaisesRegex(ValueError, "differs"):
                    runner.checked_images(self.images, proof, "/fork", "base")
            proof.write_text(json.dumps({"images": self.images}))
            with patch.object(runner, "verify", return_value={
                    "images": self.images}):
                result = runner.checked_images(
                    self.images, proof, "/fork", "base")
                self.assertEqual(result["images"], self.images)
            altered = dict(self.images)
            altered.pop("iva")
            with self.assertRaisesRegex(ValueError, "all seven"):
                runner.checked_images(altered, proof, "/fork", "base")

    def test_full_cohort_required_even_when_development_limit_one(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/"truth"
            data.mkdir()
            output=Path(folder)/"benchmark"
            attestor=Path(folder)/"att.json"
            attestor.write_text("{}")
            with (patch.object(runner, "checked_images", return_value={}),
                  patch.object(runner, "attestation", return_value={}),
                  patch.object(runner, "cohort_rows", return_value=[
                      ("only", data/"only", {})])):
                with self.assertRaisesRegex(ValueError, "incomplete HXB2"):
                    runner._run(data, output, self.images, "/fork", "base",
                                attestor, jobs=1, timeout=1800, limit=1,
                                resume=False)
            self.assertFalse(output.exists())

    def test_partial_execution_records_failed_arms_without_qualifying(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            data=directory/"truth"
            data.mkdir()
            (data/"cohort.json").write_text("{}")
            output=directory/"benchmark"
            attestor=directory/"attestation.json"
            attestor.write_text("{}")
            cases=[(f"s{i}", data/f"s{i}", {"family": "clonal"})
                   for i in range(400)]
            def fake_run(case, root, images, proof, timeout):
                identifier=case[0]
                return {"id": identifier,
                        "results": {
                            name: {"status": "failed" if name=="abyss"
                                   else "success"}
                            for name in images}}
            with (patch.object(runner, "checked_images", return_value={}),
                  patch.object(runner, "attestation", return_value={
                      "valid": True}),
                  patch.object(runner, "cohort_rows", return_value=cases),
                  patch.object(runner, "run_case", side_effect=fake_run),
                  patch.object(runner, "prune_case") as verified_cleanup):
                result=runner._run(
                    data, output, self.images, "/fork", "base",
                    attestor, jobs=1, timeout=1800, limit=1, resume=False)
            self.assertEqual(verified_cleanup.call_count,1)
            self.assertEqual(result["cases_attempted"],1)
            self.assertEqual(result["failed_arms"],1)
            self.assertEqual(result["status"],"ATTEMPTED_NOT_QUALIFIED")
            record=json.loads((output/"results.jsonl").read_text())
            self.assertEqual(record["results"]["abyss"]["status"],"failed")
            frozen=json.loads((output/"run_manifest.json").read_text())
            self.assertEqual(frozen["expected"],400)
            self.assertFalse(frozen["qualified"])
            self.assertEqual(frozen["schema"],runner.SCHEMA)

    def test_wrong_frozen_resume_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            data=root/"truth"
            data.mkdir()
            (data/"cohort.json").write_text("{}")
            output=root/"run"
            output.mkdir()
            (output/"run_manifest.json").write_text('{"source":"wrong"}')
            attestor=root/"attestation.json"
            attestor.write_text("{}")
            cases=[(f"s{i}",data/f"s{i}",{"family":"clonal"})
                   for i in range(400)]
            with (patch.object(runner, "checked_images", return_value={}),
                  patch.object(runner, "attestation", return_value={
                      "valid": True}),
                  patch.object(runner, "cohort_rows", return_value=cases)):
                with self.assertRaisesRegex(ValueError, "resume manifest"):
                    runner._run(
                        data,output,self.images,"/fork","base",attestor,
                        jobs=1,timeout=1800,limit=1,resume=True)

    def test_resume_audits_prior_log_before_recovering_checkpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            data=root/"truth"
            data.mkdir()
            (data/"cohort.json").write_text("{}")
            output=root/"run"
            output.mkdir()
            proof_file=root/"attestation.json"
            proof_file.write_text("{}")
            truth={"valid":True}
            selected=[(f"s{i}",data/f"s{i}",{"family":"clonal"})
                      for i in range(400)]
            prior='{"corrupted":"old-stream"}\n'
            (output/"results.jsonl").write_text(prior)
            frozen=runner.manifest(data,truth,self.images,proof_file,None)
            (output/"run_manifest.json").write_text(
                json.dumps(frozen,sort_keys=True))
            recovered=[{"id":r[0],"results":{},"execution_order":[]} for r in selected]
            with (patch.object(runner,"checked_images",return_value={}),
                  patch.object(runner,"attestation",return_value=truth),
                  patch.object(runner,"cohort_rows",return_value=selected),
                  patch.object(runner,"recover",return_value=recovered),
                  patch.object(runner,"run_case",side_effect=AssertionError)):
                report=runner._run(data,output,self.images,"/fork","base",
                                   proof_file,jobs=1,timeout=1800,
                                   limit=None,resume=True)
            assert report["cases_attempted"]==400
            rows=(output/"results.jsonl").read_text().splitlines()
            self.assertEqual(len(rows),400)
            self.assertEqual(len({json.loads(x)["id"] for x in rows}),400)
            audit=json.loads((output/"resume_history.jsonl").read_text())
            import hashlib
            self.assertEqual(audit["prior_results_sha256"],
                             hashlib.sha256(prior.encode()).hexdigest())
            self.assertEqual(audit["recovered_cases"],400)

    def test_preflight_bounds_and_missing_fork_sha_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "jobs"):
                runner.run(root, root, self.images, root, "base",
                           root, jobs=11)
            with self.assertRaisesRegex(ValueError, "development"):
                runner.run(root, root, self.images, root, "base",
                           root, limit=401)


if __name__=="__main__":
    unittest.main()
