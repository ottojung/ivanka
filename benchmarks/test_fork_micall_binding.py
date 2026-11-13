"""Real-case fork mode must not provide a bypass around source attestation."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from fork_micall_binding import (
    VARIABLES, check, requested, require_fresh_micall_mode,
)
from podman_full_micall import (
    verify_ivanka_image_binding, verify_micall_image_pair,
)


class ForkBindingTests(unittest.TestCase):
    def test_incomplete_environment_refused_before_old_verification(self):
        env={VARIABLES[0]: "/some/file"}
        with self.assertRaisesRegex(ValueError,"partial"):
            requested(env)
        self.assertFalse(requested({}))
        self.assertTrue(requested(dict.fromkeys(VARIABLES, "source")))

    def test_both_candidate_types_require_exact_image_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            images={"ivanka": "a"*64,"iva":"b"*64,"spades":"c"*64}
            attested={
                "source_commit": "f"*40,
                "source_url": "https://github.com/ottojung/MiCall/tree/"+"f"*40,
                "images": {name: {"image_sha256":sha}
                           for name,sha in images.items()},
            }
            attest=root/"proof.json"
            pins=root/"images.json"
            attest.write_text(json.dumps(attested))
            pins.write_text(json.dumps(images))
            env=dict(zip(VARIABLES, (str(attest),"/fork",str(pins),"base")))
            with patch("fork_micall_binding.verify",return_value=attested):
                info=check("a"*64,environ=env)
                self.assertEqual(info["tool"],"ivanka")
                info=check("c"*64,competitor="spades",environ=env)
                self.assertEqual(info["tool"],"spades")
                with self.assertRaisesRegex(ValueError,"differs"):
                    check("a"*64,competitor="spades",environ=env)
                with self.assertRaisesRegex(ValueError,"differs"):
                    check("not-a-sha",environ=env)
            wrong=dict(attested,source_commit="0"*40)
            with patch("fork_micall_binding.verify",return_value=wrong):
                with self.assertRaisesRegex(ValueError,"differs"):
                    check("a"*64,environ=env)

    def test_verified_fork_mode_requires_full_fresh_two_arm_run(self):
        options = dict(mode="both",parallel_arms=True,all_projects=True,
                       cache_status=False,import_iva_from=[],resume_from=[],
                       allow_missing_baseline=False)
        require_fresh_micall_mode(SimpleNamespace(**options))
        for key,value in (("mode","iva"),("parallel_arms",False),
                          ("all_projects",False),("cache_status",True),
                          ("import_iva_from",["cached"]),
                          ("resume_from",["old"]),
                          ("allow_missing_baseline",True)):
            with self.subTest(key=key):
                updated={**options,key:value}
                with self.assertRaisesRegex(ValueError,"fresh complete"):
                    require_fresh_micall_mode(SimpleNamespace(**updated))

    def test_old_historical_check_is_not_bypassed_without_all_four(self):
        with (
            patch.dict(os.environ,{VARIABLES[0]:"path"},clear=True),
            patch("fork_micall_binding.check"),
        ):
            with self.assertRaisesRegex(ValueError,"partial"):
                verify_ivanka_image_binding("a"*64)

    def test_fork_candidates_share_fork_base_not_iva_candidate_layers(self):
        env=dict.fromkeys(VARIABLES, "present")
        with (
            patch.dict(os.environ,env,clear=True),
            patch("fork_micall_binding.check") as actual,
            patch("podman_full_micall.verify_identical_micall_base",
                  side_effect=AssertionError("legacy layers compared")),
        ):
            verify_micall_image_pair("iva-digest", "ivanka-digest")
            verify_micall_image_pair("iva-digest", "spades-digest",
                                     competitor="spades")
        self.assertEqual(actual.call_count,2)
        actual.assert_any_call("ivanka-digest",competitor=None)
        actual.assert_any_call("spades-digest",competitor="spades")

    def test_legacy_base_layers_still_checked(self):
        with (
            patch.dict(os.environ,{},clear=True),
            patch("podman_full_micall.verify_identical_micall_base")
            as old,
        ):
            verify_micall_image_pair("legacy-iva","legacy-ivanka")
        old.assert_called_once_with("legacy-iva","legacy-ivanka")

    def test_explicit_attestation_binds_real_runner_without_old_ast(self):
        env=dict.fromkeys(VARIABLES,"present")
        with (
            patch.dict(os.environ,env,clear=True),
            patch("fork_micall_binding.check") as verified,
            patch("subprocess.run",side_effect=AssertionError(
                "unverified old adapter executed")),
        ):
            verify_ivanka_image_binding("a"*64,competitor="spades")
        verified.assert_called_once_with("a"*64,competitor="spades")


if __name__=="__main__":
    unittest.main()
