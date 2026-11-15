"""Guard against accidental promotion of mixed-strain diagnostics."""
import unittest
from unittest.mock import patch

from expanded import coherent_mixed_screen as screen


class MixedSourceTests(unittest.TestCase):
    def test_frozen_two_family_set_is_complete(self):
        cases = screen.inputs()
        self.assertEqual(len(cases), 32)
        self.assertEqual(len({x[0] for x in cases}), 32)
        for family in screen.FAMILIES:
            self.assertEqual(sum(c[2]["family"] == family for c in cases), 16)

    def test_freeze_rejects_changed_original_source(self):
        with patch.object(screen, "commit", side_effect=ValueError("dirty source")):
            with patch.object(screen, "output", return_value="{}"):
                with self.assertRaises(ValueError):
                    screen.freeze()

    def test_invalid_image_cannot_replay_without_manifest(self):
        self.assertEqual(len(screen.IMAGE), 64)
        self.assertEqual(len(screen.FORK_COMMIT), 40)
        self.assertNotEqual(screen.FORK_COMMIT, screen.IVANKA_COMMIT)


if __name__ == "__main__":
    unittest.main()
