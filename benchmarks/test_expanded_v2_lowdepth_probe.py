"""Pilot cannot weaken the original 400-case seven-arm qualification."""
import unittest

from expanded.v2_lowdepth_probe import (
    SAMPLES, only_changed, pinned_manifest,
)
from expanded.adapters import ASSEMBLERS
from unittest.mock import patch


class LowDepthProbeTests(unittest.TestCase):
    @staticmethod
    def rows():
        return [(name, None, {"pairs": 5000}) for name in SAMPLES]

    def test_selects_exactly_the_sixteen_changed_input_cases(self):
        original = self.rows()
        self.assertEqual([row[0] for row in only_changed(reversed(original))],
                         list(SAMPLES))
        with self.assertRaises(ValueError):
            only_changed(original[:-1])
        with self.assertRaises(ValueError):
            only_changed([*original[:-1],
                          (SAMPLES[-1], None, {"pairs": 2500})])

    def test_refuses_v1_and_missing_image_provenance(self):
        images = {tool: "a" * 64 for tool in ASSEMBLERS}
        proof = {"schema": "ivanka.hxb2_truth_validation.v2",
                 "cohort_sha256": "b" * 64, "valid": True}
        with patch("expanded.v2_lowdepth_probe.digest",
                   return_value="c" * 64):
            result = pinned_manifest(proof, images, "/unused", "d" * 64)
        self.assertEqual(result["qualification"], "NOT_EVALUATED")
        self.assertEqual(result["expected"], 16)
        self.assertEqual(set(result["images"]), set(ASSEMBLERS))
        with self.assertRaises(ValueError):
            pinned_manifest({**proof, "schema":
                             "ivanka.hxb2_truth_validation.v1"},
                            images, "/unused", "d" * 64)
        with self.assertRaises(ValueError):
            pinned_manifest(proof, {"iva": "a" * 64}, "/unused", "d" * 64)


if __name__ == "__main__":
    unittest.main()
