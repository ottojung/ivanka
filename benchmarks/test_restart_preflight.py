"""The restart gate must not confuse smoke success with owner authorization."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expanded import restart_preflight as gate
from expanded import real_progress_bridge
from expanded.adapters import ASSEMBLERS

IMAGES={name:f"{i+1:x}"*64 for i,name in enumerate(ASSEMBLERS)}
OTHER=tuple(name for name in ASSEMBLERS if name!="iva")

class RestartAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.kwargs={
            "root":self.root,"images":IMAGES,
            "sources":{name:self.root/name for name in ASSEMBLERS},
            "attestation_file":self.root/"att.json",
            "real_data":self.root/"real",
            "synthetic_data":self.root/"synth",
            "synthetic_smoke":self.root/"smoke-synthetic",
            "targeted_smoke":self.root/"smoke-targeted",
            "real_smoke":self.root/"smoke-real",
            "exact_synthetic":self.root/"exact-synth",
            "exact_real":self.root/"exact-real",
            "min_free_bytes":1,
        }

    def assess(self, master=gate.BASE):
        with (patch.object(gate,"runner_revision",return_value={"commit":"f"*40}),
              patch.object(gate,"ensure_images",return_value={"status":"ok"}),
              patch.object(gate,"physical_attestation",return_value={"sample_count":198}),
              patch.object(gate,"attestation",return_value={"valid":True}),
              patch.object(gate,"ensure_synthetic_smoke",return_value={"arms":7}),
              patch.object(gate,"ensure_targeted_smoke",return_value={"arms":21}),
              patch.object(gate,"verify_physical_smoke",return_value={"arms":12}),
              patch.object(gate,"ensure_exact_smoke",return_value={"arms":9}),
              patch.object(gate,"git_master",return_value=master)):
            return gate.assess(**self.kwargs)

    def test_all_technical_checks_do_not_authorize_expensive_cohort(self):
        report=self.assess()
        self.assertEqual(report["blockers"],[])
        self.assertEqual(report["status"],
                         "TECHNICALLY_READY_PENDING_OWNER_AUTHORIZATION")
        self.assertFalse(report["benchmark_started"])
        self.assertTrue(report["requires_owner_authorization"])

    def test_wrong_fork_master_blocks(self):
        report=self.assess("b"*40)
        self.assertEqual(report["status"],"BLOCKED")
        self.assertTrue(any("baseline:" in item for item in report["blockers"]))

    def test_low_free_space_blocks_full_relaunch(self):
        self.kwargs["min_free_bytes"]=2**62
        report=self.assess()
        self.assertEqual(report["status"],"BLOCKED")
        self.assertTrue(any("storage:" in item for item in report["blockers"]))

    def test_missing_complete_smoke_blocks_instead_of_fabricating_pass(self):
        with (patch.object(gate,"runner_revision",return_value={}),
              patch.object(gate,"ensure_images",return_value={}),
              patch.object(gate,"physical_attestation",return_value={}),
              patch.object(gate,"attestation",return_value={"valid":True}),
              patch.object(gate,"ensure_synthetic_smoke",side_effect=ValueError("bad")),
              patch.object(gate,"ensure_targeted_smoke",return_value={}),
              patch.object(gate,"verify_physical_smoke",return_value={}),
              patch.object(gate,"ensure_exact_smoke",return_value={}),
              patch.object(gate,"git_master",return_value=gate.BASE)):
            report=gate.assess(**self.kwargs)
        self.assertEqual(report["status"],"BLOCKED")
        self.assertTrue(any("synthetic_seven_arm_smoke" in item
                            for item in report["blockers"]))

    def test_runner_revision_rejects_dirty_unpublished_source(self):
        with patch.object(gate.subprocess,"check_output",
                          return_value=" M benchmarks/expanded/foo.py"):
            with self.assertRaisesRegex(ValueError,"uncommitted"):
                gate.runner_revision(self.root)
        def fake(argv,**kwargs):
            if "status" in argv:
                return ""
            if "branch" in argv:
                return "bench/reliable-relaunch-20261116"
            if "rev-parse" in argv:
                return "a"*40
            if "get-url" in argv:
                return "https://github.com/ottojung/ivanka.git"
            if "ls-remote" in argv:
                return "b"*40+" refs/heads/bench/reliable-relaunch-20261116"
            raise ValueError(argv)
        with patch.object(gate.subprocess,"check_output",side_effect=fake):
            with self.assertRaisesRegex(ValueError,"not published"):
                gate.runner_revision(self.root)

    def test_scoped_real_smoke_refuses_legacy_invalid_attempt(self):
        root=self.root/"smoke-real"
        root.mkdir()
        (root/"INVALID_SCOPE.json").write_text('{"invalid":true}')
        with self.assertRaisesRegex(ValueError,"invalidated"):
            real_progress_bridge.verify_physical_smoke(root,IMAGES)

    def test_scoped_smoke_requires_all_six_and_no_more_samples(self):
        root=self.root/"smoke-real"
        root.mkdir()
        example={"schema":real_progress_bridge.SCHEMA,"images":IMAGES,
                 "selected_tools":list(OTHER),"selected_sample":"s1"}
        (root/"run_manifest.json").write_text(json.dumps(example))
        (root/"execution_manifest.json").write_text(json.dumps({}))
        (root/"attempt_summary.json").write_text(json.dumps({}))
        with self.assertRaisesRegex(ValueError,"missing a comparator"):
            real_progress_bridge.verify_physical_smoke(root,IMAGES)
        example["selected_sample"]=None
        (root/"run_manifest.json").write_text(json.dumps(example))
        with self.assertRaisesRegex(ValueError,"precisely one"):
            real_progress_bridge.verify_physical_smoke(root,IMAGES)

if __name__=="__main__":
    unittest.main()
