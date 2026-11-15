"""The repaired seven-way pilot remains separate from release qualification."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench import dedicated_image_attestation as attestation
from expanded import experimental_repaired_seven as pilot


class RepairedPilotTests(unittest.TestCase):
    def test_repaired_branch_diagnostic_only(self):
        with patch.object(attestation, "_verify", return_value={}) as internal:
            attestation.verify_diagnostic({}, {}, "base", "-repaired-20261115")
            internal.assert_called_once_with(
                {}, {}, "base", "-repaired-20261115")

    def test_canonical_gate_is_not_changed(self):
        with patch.object(attestation, "_verify", return_value={}) as internal:
            attestation.verify({}, {}, "base")
            internal.assert_called_once_with({}, {}, "base")

    def test_unrecognized_pilot_branch_rejected(self):
        for suffix in ("-repaired-20261114", "-test", "", "/main"):
            with self.subTest(suffix=suffix), self.assertRaisesRegex(
                    ValueError, "unsupported experimental"):
                attestation.verify_diagnostic({}, {}, "base", suffix)

    def test_frozen_repaired_inputs_and_unqualified_results(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"cohort.json").write_text("original hxb2 v2 cohort")
            (root/"image-proof.json").write_text("repaired seven source")
            m=pilot.manifest(root, {"ivanka":"pinned"},
                             root/"image-proof.json", "runner-commit")
            self.assertFalse(m["qualified"])
            self.assertFalse(m["release_qualified"])
            self.assertFalse(m["canonical_branch_qualification"])
            self.assertEqual(m["status"],"DIAGNOSTIC_ONLY_NOT_QUALIFIED")
            self.assertEqual(m["common_micall_source_commit"],
                             "74f60e7be6248bdf5019498276036a0ebd339006")
            self.assertIn("adapter_tails-s013",m["cases"])
            self.assertIn("coverage_hole-s010",m["cases"])
            self.assertIn("coverage_hole-s012",m["cases"])

    def test_fixed_1800_second_arm_cap(self):
        with self.assertRaisesRegex(ValueError,"1800"):
            pilot.run(Path("out"),Path("data"),Path("images"),timeout=1801)


if __name__=="__main__":
    unittest.main()
