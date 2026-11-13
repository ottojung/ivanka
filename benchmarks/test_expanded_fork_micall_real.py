"""Fork physical-198 comparisons cannot substitute old baselines or partials."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from expanded import fork_micall_real as runner
from expanded.adapters import ASSEMBLERS
from expanded.real_matrix import MANIFEST


class ForkRealRunnerTests(unittest.TestCase):
    def setUp(self):
        self.images={name:f"{n+1:x}"*64
                     for n,name in enumerate(ASSEMBLERS)}

    def test_fresh_manifest_pins_dedicated_attestation_verifier_sources(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            data=root/"data"
            data.mkdir()
            (data/"manifest.tsv").write_text("frozen-manifest")
            attestation=root/"att.json"
            attestation.write_text("{}")
            with patch.object(runner,"validate_real",return_value=MANIFEST):
                report=runner.source_manifest(
                    data,self.images,attestation,"a"*64,None,
                    [name for name in ASSEMBLERS if name!="iva"])
            for name in ("image_source_attestation.py",
                         "dedicated_image_attestation.py",
                         "fork_image_attestation.py"):
                self.assertIn(name,report["source_files_sha256"])

    def test_all_six_tools_are_required_for_full_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            data=root/"reads"
            data.mkdir()
            (data/"manifest.tsv").write_text("sample\ns1\n")
            with self.assertRaisesRegex(ValueError,"real 198 cohort"):
                runner.validate_real(data,None)
            with patch.object(runner,"digest",return_value=MANIFEST):
                with self.assertRaisesRegex(ValueError,"original unique"):
                    runner.validate_real(data,None)

    def test_pinned_198_source_refuses_unknown_development_sample(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"manifest.tsv").write_text(
                "sample\n"+"".join(f"p{i}\n" for i in range(198)))
            with patch.object(runner,"digest",return_value=MANIFEST):
                self.assertEqual(runner.validate_real(root,None),MANIFEST)
                with self.assertRaisesRegex(ValueError,"development"):
                    runner.validate_real(root,"not-in-cohort")

    def test_all_original_paired_micall_pipeline_flags_survive(self):
        for name in ASSEMBLERS:
            if name=="iva":continue
            argv=runner.command(name,jobs=10,sample="case")
            self.assertIn("--mode",argv)
            self.assertIn("--parallel-arms",argv)
            self.assertIn("--all-projects",argv)
            self.assertIn("--diagnostic-90-floor",argv)
            self.assertIn("--sample-time-limit",argv)
            self.assertEqual(argv[-2:],["--sample","case"])
            self.assertNotIn("--import-iva-from",argv)
            self.assertNotIn("--resume-from",argv)
            if name=="ivanka":
                self.assertNotIn("--candidate-assembler",argv)
            else:
                self.assertIn("--candidate-assembler",argv)

    def test_one_case_one_tool_is_explicitly_never_qualified(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            data=root/"truth"
            data.mkdir()
            (data/"manifest.tsv").write_text("sample\nsample\n")
            proof=root/"proof.json"
            proof.write_text("{}")
            output=root/"new_run"
            def simulated(argv,**kwargs):
                target=Path(kwargs["env"]["IVANKA_PODMAN_RESULTS"])
                (target/"results.jsonl").write_text(
                    '{"status":"finished","sample":"simulated"}\n')
                self.assertIn("--mode",argv)
                self.assertEqual(kwargs["env"][
                    "IVANKA_FORK_IMAGE_MAP"],
                    str(output/"source_verified_images.json"))
                return Mock(returncode=0)
            with (patch.object(runner,"checked_images",return_value={}),
                  patch.object(runner,"validate_real",return_value=MANIFEST),
                  patch.object(runner,"subprocess") as sub):
                sub.run.side_effect=simulated
                outcome=runner.run(
                    data,output,self.images,"/fork","base",proof,
                    jobs=1,sample="sample",selected=["ivanka"])
            self.assertEqual(outcome["status"],"ATTEMPTED_NOT_QUALIFIED")
            self.assertFalse(outcome["all_six_candidate_runs_attempted"])
            self.assertIn("ivanka",outcome["tools"])
            self.assertEqual(len(outcome["tools"]),1)
            frozen=json.loads((output/"run_manifest.json").read_text())
            self.assertFalse(frozen["qualified"])
            self.assertEqual(frozen["selected_sample"],"sample")
            self.assertEqual(frozen["images"],self.images)

    def test_invalid_tool_or_worker_refused(self):
        with self.assertRaisesRegex(ValueError,"worker"):
            runner.run(".",".",self.images,".","base",".",jobs=11)
        with self.assertRaisesRegex(ValueError,"duplicate"):
            runner.run(".",".",self.images,".","base",".",
                       selected=["ivanka","ivanka"])
        with self.assertRaisesRegex(ValueError,"unknown"):
            runner.run(".",".",self.images,".","base",".",
                       selected=["iva"])


if __name__=="__main__":
    unittest.main()
