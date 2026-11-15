"""Hermetic source/identity tests; never require private HXB2 FASTQs in CI."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from expanded import coherent_mixed_screen as screen


def cases():
    return [
        (f"{family}-s{i:03d}", Path(f"/fake/{family}-s{i:03d}"),
         {"family": family})
        for family in screen.FAMILIES for i in range(16)
    ]


class MixedSourceTests(unittest.TestCase):
    def test_frozen_two_family_set_is_complete(self):
        with patch.object(screen, "cohort_rows", return_value=cases()):
            selected = screen.inputs()
        self.assertEqual(len(selected), 32)
        self.assertEqual(len({x[0] for x in selected}), 32)
        for family in screen.FAMILIES:
            self.assertEqual(sum(c[2]["family"] == family for c in selected), 16)

    def test_missing_mixed_sample_refuses_a_partial_gate(self):
        with patch.object(screen, "cohort_rows", return_value=cases()[:-1]):
            with self.assertRaisesRegex(ValueError, "all 32"):
                screen.inputs()

    def test_duplicate_mixed_identity_is_rejected(self):
        erroneous = cases()
        erroneous[-1] = erroneous[0]
        with patch.object(screen, "cohort_rows", return_value=erroneous):
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                screen.inputs()

    def test_freeze_rejects_changed_original_source(self):
        with tempfile.TemporaryDirectory() as directory:
            pilot = Path(directory)
            frozen = {
                "rust_commit": screen.IVANKA_COMMIT,
                "fork_commit": screen.FORK_COMMIT,
                "ivanka_image_id": screen.IMAGE,
                "common_image": screen.BASE,
                "common_commit": screen.COMMON_COMMIT,
                "release_qualified": False,
            }
            (pilot / "run_manifest.json").write_text(json.dumps(frozen))
            with patch.object(screen, "PILOT", pilot), patch.object(
                    screen, "commit", side_effect=ValueError("dirty source")):
                with self.assertRaisesRegex(ValueError, "dirty source"):
                    screen.freeze()

    def test_invalid_image_cannot_replay_without_manifest(self):
        self.assertEqual(len(screen.IMAGE), 64)
        self.assertEqual(len(screen.FORK_COMMIT), 40)
        self.assertNotEqual(screen.FORK_COMMIT, screen.IVANKA_COMMIT)


if __name__ == "__main__":
    unittest.main()
