"""Regression tests over the committed native A/B byte-equivalence evidence."""

from __future__ import annotations

import json
import pathlib
import unittest

REPORT = pathlib.Path(__file__).with_name("native-byte-equivalence-report.json")


class NativeByteEquivalenceEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT.read_text())

    def test_all_sixteen_ultradeep_cases_are_triple_byte_identical(self) -> None:
        cases = self.report["cases"]
        self.assertEqual(len(cases), 16)
        self.assertEqual(
            [case["case"] for case in cases],
            [f"ultradeep-s{index:03d}" for index in range(16)],
        )
        for case in cases:
            with self.subTest(case=case["case"]):
                self.assertTrue(case["base_eq_frozen"])
                self.assertTrue(case["cand_eq_frozen"])
                self.assertTrue(case["cand_eq_base"])
                self.assertEqual(len(case["cand_sha"]), 64)

    def test_candidate_native_runtime_is_not_slower(self) -> None:
        cases = self.report["cases"]
        base = sum(case["base_s"] for case in cases)
        candidate = sum(case["cand_s"] for case in cases)
        self.assertLess(candidate, base * 1.10)
        self.assertGreater(base, 0)

    def test_binaries_are_pinned(self) -> None:
        self.assertEqual(
            self.report["base_source_commit"],
            "12d8c72f01f305b7f81db26193ec5fc213ba55bf",
        )
        self.assertEqual(
            self.report["candidate_source_commit"],
            "94a58bbbf0ab1bf518534a82f00f3c8611face2a",
        )


if __name__ == "__main__":
    unittest.main()
