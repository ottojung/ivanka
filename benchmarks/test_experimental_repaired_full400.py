"""Source and release-state invariants for experimental seven-way diagnostics."""
import unittest
from unittest.mock import patch

from expanded import experimental_repaired_full400 as full


class ExperimentalFull400Tests(unittest.TestCase):
    def test_release_status_cannot_use_provisional_suffix(self):
        self.assertEqual(full.SCHEMA,
                         "ivanka.experimental.repaired_common_full400.v1")

    def test_refuse_preexisting_source_mismatch(self):
        with patch.object(full, "freeze", side_effect=ValueError(
                "frozen source mismatch")):
            with self.assertRaisesRegex(ValueError, "frozen source mismatch"):
                full.run("unused","unused","unused")


if __name__ == "__main__":
    unittest.main()
