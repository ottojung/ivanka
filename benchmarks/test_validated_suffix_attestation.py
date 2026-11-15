"""Experimental aliases never satisfy the canonical seven-image release gate."""
import unittest
from unittest.mock import patch

from assembler_bench import dedicated_image_attestation as attest


class BranchIdentityTests(unittest.TestCase):
    def test_production_verifier_cannot_choose_an_alias(self):
        with patch.object(attest, "_verify", return_value={}) as internal:
            attest.verify({}, {}, "base")
            internal.assert_called_once_with({}, {}, "base")

    def test_experimental_alias_is_explicit_and_never_qualifies(self):
        with patch.object(attest, "_verify", return_value={}) as internal:
            attest.verify_diagnostic({}, {}, "base", "-validated-20261115")
            internal.assert_called_once_with(
                {}, {}, "base", "-validated-20261115")

    def test_no_distance_alias_is_explicitly_diagnostic_only(self):
        with patch.object(attest, "_verify", return_value={}) as internal:
            attest.verify_diagnostic({}, {}, "base", "-unlinked-20261115")
            internal.assert_called_once_with(
                {}, {}, "base", "-unlinked-20261115")

    def test_rejects_arbitrary_branch_suffixes(self):
        for suffix in ("", "-test", "-validated-20261114", "../../main"):
            with self.subTest(suffix=suffix), self.assertRaisesRegex(
                    ValueError, "unsupported experimental"):
                attest.verify_diagnostic({}, {}, "base", suffix)


if __name__ == "__main__":
    unittest.main()
