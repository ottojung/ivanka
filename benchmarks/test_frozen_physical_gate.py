"""The frozen clinical 198-case objective is checked without reruns."""
import unittest
from pathlib import Path

from assembler_bench.frozen_physical_gate import analyze

ROOT = Path("/workspace/micall-frozen-seven-20261117")


class FrozenPhysicalGateTests(unittest.TestCase):
    def test_original_score_and_runtime_blockers_are_explicit(self):
        if not ROOT.is_dir():
            self.skipTest("owner original MiCall archive unavailable")
        p = analyze(ROOT)
        self.assertEqual(p["physical_cases"], 198)
        self.assertEqual(len(p["floor_failures"]), 1)
        self.assertEqual(p["floor_failures"][0]["candidate"], 102.0)
        self.assertEqual(p["floor_failures"][0]["best_available"], 179.0)
        self.assertFalse(p["qualification_pass"])
        self.assertEqual(p["rivals"]["abyss"]["paired"], 106)
        self.assertEqual(p["rivals"]["abyss"]["runtime_psi"]["psi0"], 0.0)
        self.assertFalse(
            p["rivals"]["abyss"]["runtime_psi"]["positive_all_nonnegative"])
        for name in ("iva", "haploflow", "megahit", "spades", "velvet"):
            self.assertTrue(p["rivals"][name]["score_psi"]["positive_all_nonnegative"])
            self.assertTrue(p["rivals"][name]["runtime_psi"]["positive_all_nonnegative"])


if __name__ == "__main__":
    unittest.main()
