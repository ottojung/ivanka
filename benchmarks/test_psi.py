"""Standalone tests for benchmarks/psi.py (no third-party dependencies)."""

import contextlib
import io
import json
from decimal import Decimal
import subprocess
import sys
import unittest

import psi


class PsiTests(unittest.TestCase):
    def calculate(self, numbers):
        return psi.compute([Decimal(str(x)) for x in numbers])

    def test_values_and_limit(self):
        values, limit, roots, all_real = self.calculate([2, -1, 0, 0])
        self.assertEqual(values, {"0": Decimal(0), "1": Decimal("0.25"), "2": Decimal("1.25")})
        self.assertEqual(limit, "+inf")
        self.assertEqual(len(roots), 1)
        self.assertAlmostEqual(float(roots[0]), 0)
        self.assertFalse(all_real)

    def test_two_roots_opposite_sides_of_zero(self):
        # 2*(2**r)*(2**r - 1/2)*(2**r - 2), exact roots -1 and +1.
        _, _, roots, _ = self.calculate([1] * 2 + [-3] * 5 + [7] * 2)
        self.assertEqual(len(roots), 2)
        self.assertAlmostEqual(float(roots[0]), -1, places=8)
        self.assertAlmostEqual(float(roots[1]), 1, places=8)

    def test_tangent_zero_without_sign_change(self):
        # 2**r * (2**r - 3)**2, double root log2(3).
        _, _, roots, _ = self.calculate([1] * 9 + [-3] * 6 + [7])
        self.assertEqual(len(roots), 1)
        self.assertAlmostEqual(float(roots[0]), 1.584962500721156, places=8)

    def test_two_positive_roots(self):
        _, limit, roots, _ = self.calculate([1] * 5 + [-3] * 5 + [7])
        self.assertEqual(limit, "+inf")
        self.assertEqual(len(roots), 2)
        self.assertLess(0, roots[0])
        self.assertLess(roots[0], roots[1])

    def test_no_finite_roots_and_negative_dominance(self):
        values, limit, roots, _ = self.calculate([-4, -1, 0])
        self.assertAlmostEqual(float(values["0"]), -2 / 3)
        self.assertEqual(limit, "-inf")
        self.assertEqual(roots, [])

    def test_exact_cancellation_is_identically_zero(self):
        values, limit, roots, all_real = self.calculate([1, -1, 1, -1, 0])
        self.assertTrue(all_real)
        self.assertEqual(limit, "0")
        self.assertEqual(roots, [])
        self.assertTrue(all(v == 0 for v in values.values()))

    def test_all_zero(self):
        self.assertTrue(self.calculate([0, 0])[3])

    def test_scientific_notation_and_comments(self):
        v = psi.values_from_stdin([" 1e0, -2.0 # line comment", "0 3\n"])
        self.assertEqual(v, [1, -2, 0, 3])
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            psi.values_from_stdin(["1 nan"])
        with self.assertRaisesRegex(ValueError, 'expected at least one'):
            psi.values_from_stdin([" # empty"])

    def test_json_ascii_only_and_valid_infinities(self):
        result = subprocess.run([sys.executable, psi.__file__, '--json'], input='1 -3\n', text=True, capture_output=True, check=True)
        self.assertTrue(result.stdout.isascii())
        self.assertIn('\n\t"psi": {', result.stdout)
        self.assertIn('\n\t\t"0":', result.stdout)
        data = json.loads(result.stdout)
        self.assertEqual(data['psi']['0'], 0)
        self.assertEqual(data['psi_at_positive_infinity'], '-inf')
        self.assertEqual(data['zeros'], [0])
        self.assertNotIn('negative_infinity_is_limit_only', data)
        self.assertNotIn('NaN', result.stdout)

    def test_human_output_uses_unicode_symbols(self):
        result = subprocess.run([sys.executable, psi.__file__], input="1 1 -2\n",
                                text=True, capture_output=True, check=True)
        self.assertIn("Ψ(0) =", result.stdout)
        self.assertIn("Ψ(+∞) = −∞", result.stdout)
        self.assertIn("{ r : Ψ(r) = 0 } = { 1.709511291 }", result.stdout)
        self.assertNotIn("\\", result.stdout)

    def test_human_identically_zero_uses_real_numbers_symbol(self):
        result = subprocess.run([sys.executable, psi.__file__], input="1 -1\n",
                                text=True, capture_output=True, check=True)
        self.assertIn("{ r : Ψ(r) = 0 } = ℝ", result.stdout)

    def test_empty_zero_set_uses_empty_set_symbol(self):
        for args in ([], ["--json"]):
            result = subprocess.run([sys.executable, psi.__file__, *args],
                                    input="1 2 3\n", text=True, capture_output=True, check=True)
            if args:
                self.assertEqual(json.loads(result.stdout)["zeros"], [])
                self.assertTrue(result.stdout.isascii())
            else:
                self.assertIn("{ r : Ψ(r) = 0 } = ∅", result.stdout)
                self.assertNotIn("−∞", result.stdout)

    def test_all_real_zero_set_json_is_ascii(self):
        result = subprocess.run([sys.executable, psi.__file__, "--json"],
                                input="1 -1\n", text=True, capture_output=True, check=True)
        self.assertTrue(result.stdout.isascii())
        self.assertEqual(json.loads(result.stdout)["zeros"], "R")

    def test_invalid_input_nonzero_exit(self):
        r = subprocess.run([sys.executable, psi.__file__, '--json'], input='foo', text=True, capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('invalid number', r.stderr)
        self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()
