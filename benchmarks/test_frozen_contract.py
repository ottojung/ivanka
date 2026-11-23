"""Frozen MiCall identity and source-level rejection tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from assembler_bench.frozen_contract import COMMIT, verify_images, verify_source

ROOT = Path("/workspace/micall-frozen-seven-20261117")
SOURCE = Path("/workspace/micall-immutable-source-8458f9e5-20261123")
REVERT = Path("/workspace/micall-p0-dedup-boundary-20261122")


class FrozenSourceTests(unittest.TestCase):
    def test_original_source_required_for_new_runs(self):
        if not SOURCE.is_dir():
            self.skipTest("owner frozen source checkout unavailable")
        self.assertEqual(verify_source(SOURCE), COMMIT)
        self.assertEqual(verify_source(REVERT, require_commit=False), COMMIT)
        with self.assertRaisesRegex(ValueError, "exactly frozen"):
            verify_source(REVERT)

    def test_changed_common_source_is_rejected(self):
        with (
            patch("assembler_bench.frozen_contract.subprocess.check_output",
                  return_value="0" * 40),
            self.assertRaisesRegex(ValueError, "tree differs"),
        ):
            verify_source("/tmp/untrusted")

    def test_original_manifest_and_source_attestation(self):
        if not ROOT.is_dir():
            self.skipTest("owner original results unavailable")
        self.assertEqual(verify_images(ROOT)["baseline_commit"], COMMIT)

    def test_manifest_mutation_fails_before_any_run(self):
        if not ROOT.is_dir():
            self.skipTest("owner original results unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "minimal-images.json"
            dest.write_bytes((ROOT / dest.name).read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                verify_images(tmp)


if __name__ == "__main__":
    unittest.main()
