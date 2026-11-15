"""Provisional seven-image pilots cannot silently become release evidence."""
import tempfile
import unittest
from pathlib import Path

from expanded import experimental_common_seven as pilot


class ExperimentalSourceGateTests(unittest.TestCase):
    def test_case_set_is_distinct_and_includes_negative_controls(self):
        self.assertEqual(len(set(pilot.CASES)), len(pilot.CASES))
        self.assertIn("clonal-s013", pilot.CASES)
        self.assertIn("minority_30pct-s010", pilot.CASES)
        self.assertIn("adapter_tails-s013", pilot.CASES)

    def test_manifest_always_disqualifies_provisional_branches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cohort.json").write_text("original HXB2 cohort")
            (root / "attestation.json").write_text("provisional")
            m = pilot.manifest(root, {"ivanka": "pinned"},
                               root / "attestation.json", "source-sha")
            self.assertIs(m["qualified"], False)
            self.assertIs(m["release_qualified"], False)
            self.assertIs(m["canonical_branch_qualification"], False)
            self.assertEqual(m["status"], "DIAGNOSTIC_ONLY_NOT_QUALIFIED")

    def test_timeout_cannot_be_extended(self):
        with self.assertRaisesRegex(ValueError, "1800"):
            pilot.run(Path("not-started"), Path("no-data"),
                      Path("not-attested"), timeout=1801)


if __name__ == "__main__":
    unittest.main()
