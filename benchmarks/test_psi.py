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
        self.assertEqual(values, {"0": Decimal(0), "1": Decimal("0.25"), "2": Decimal("0.75")})
        self.assertEqual(limit, "+inf")
        self.assertEqual(len(roots), 1)
        self.assertAlmostEqual(float(roots[0]), 0)
        self.assertFalse(all_real)

    def test_two_roots_opposite_sides_of_zero(self):
        # 2*(2**r)*(2**r - 1/2)*(2**r - 2), exact roots -1 and +1.
        _, _, roots, _ = self.calculate([2] * 2 + [-4] * 5 + [8] * 2)
        self.assertEqual(len(roots), 2)
        self.assertAlmostEqual(float(roots[0]), -1, places=8)
        self.assertAlmostEqual(float(roots[1]), 1, places=8)

    def test_tangent_zero_without_sign_change(self):
        # 2**r * (2**r - 3)**2, double root log2(3).
        _, _, roots, _ = self.calculate([2] * 9 + [-4] * 6 + [8])
        self.assertEqual(len(roots), 1)
        self.assertAlmostEqual(float(roots[0]), 1.584962500721156, places=8)

    def test_two_positive_roots(self):
        _, limit, roots, _ = self.calculate([2] * 5 + [-4] * 5 + [8])
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

    def test_infinity_limit_when_all_magnitudes_are_below_one(self):
        _, limit, _, _ = self.calculate([Decimal("0.25"), Decimal("-0.5")])
        self.assertEqual(limit, "0")

    def test_infinity_limit_when_maximum_magnitude_is_one(self):
        _, limit, _, _ = self.calculate([1, 1, Decimal("-0.25")])
        self.assertAlmostEqual(float(limit), 2/3)

    def test_no_offset_in_moments(self):
        moments, _, _, _ = self.calculate([Decimal("0.5"), Decimal("-2"), 0])
        self.assertEqual(moments["1"], Decimal("-0.5"))
        self.assertEqual(moments["2"], Decimal("-1.25"))

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
        self.assertIn("{ r : Ψ(r) = 0 } = { 1.", result.stdout)
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
                self.assertIn("mins:", result.stdout)

    def test_all_real_zero_set_json_is_ascii(self):
        result = subprocess.run([sys.executable, psi.__file__, "--json"],
                                input="1 -1\n", text=True, capture_output=True, check=True)
        self.assertTrue(result.stdout.isascii())
        self.assertEqual(json.loads(result.stdout)["zeros"], "R")

    def test_minima_include_stationary_and_divergent_tail(self):
        # -t(t-1)^2, t=2**r: minimum at t=1/3, then -infinity.
        minima = psi.local_minima([Decimal(x) for x in [-2, 4, 4, -8]])
        self.assertEqual(len(minima), 2)
        self.assertAlmostEqual(float(minima[0][0]), -1.584962500721156, places=8)
        self.assertAlmostEqual(float(minima[0][1]), -1/27, places=8)
        self.assertEqual(minima[1], ("+inf", "-inf"))

    def test_minima_include_left_asymptotic_limit(self):
        # t(t-1)^2 has a local minimum at t=1 and approaches zero at -infinity.
        minima = psi.local_minima([Decimal(x) for x in [2, -4, -4, 8]])
        self.assertEqual(len(minima), 2)
        self.assertEqual(minima[0], ("-inf", Decimal(0)))
        self.assertAlmostEqual(float(minima[1][0]), 0, places=8)
        self.assertAlmostEqual(float(minima[1][1]), 0, places=8)

    def test_minima_at_both_tails_and_finite_point(self):
        cases = [
            ([2], [("-inf", Decimal(0))]),
            ([-2], [("+inf", "-inf")]),
            ([Decimal("0.5")], [("+inf", Decimal(0))]),
            ([Decimal("-0.5")], [("-inf", "-inf")]),
            ([1, 1, -1], None),
            ([0, 0], [("R", Decimal(0))]),
        ]
        for values, expected in cases:
            with self.subTest(values=values):
                actual = psi.local_minima([Decimal(x) for x in values])
                if expected is None:
                    self.assertEqual(actual[0][0], "R")
                    self.assertAlmostEqual(float(actual[0][1]), 1/3)
                else:
                    self.assertEqual(actual, expected)
        mins = psi.local_minima([Decimal("0.5"), Decimal(2)])
        self.assertEqual(len(mins), 1)
        self.assertAlmostEqual(float(mins[0][0]), 0, places=8)
        self.assertAlmostEqual(float(mins[0][1]), 1, places=8)

    def test_two_finite_local_minima_and_left_limit(self):
        # t(t-1)^2(t-2)^2 has two distinct interior minima.
        magnitudes = [(2, 4), (4, -12), (8, 13), (16, -6), (32, 1)]
        values = [Decimal(magnitude) * (1 if count > 0 else -1)
                  for magnitude, count in magnitudes
                  for _ in range(abs(count))]
        minima = psi.local_minima(values)
        self.assertEqual(len(minima), 3)
        self.assertEqual(minima[0], ("-inf", Decimal(0)))
        self.assertAlmostEqual(float(minima[1][0]), 0, places=8)
        self.assertAlmostEqual(float(minima[2][0]), 1, places=8)
        self.assertLess(abs(float(minima[1][1])), 1e-25)
        self.assertLess(abs(float(minima[2][1])), 1e-25)

    def test_finite_limit_at_positive_infinity(self):
        # 1 + 0.5**r decreases to 1, but never attains it.
        minima = psi.local_minima([Decimal(1), Decimal("0.5")])
        self.assertEqual(minima, [("+inf", Decimal("0.5"))])

    def test_stationary_inflection_is_not_minimum(self):
        # t(t-1)^3 = t**4 - 3*t**3 + 3*t**2 - t.
        # The stationary point t=1 is not an extremum.
        values = [Decimal(-2)] + [Decimal(4)] * 3 + [Decimal(-8)] * 3 + [Decimal(16)]
        mins = psi.local_minima(values)
        # One finite minimum exists where t=1/4, not at t=1.
        finite = [r for r, v in mins if isinstance(r, Decimal)]
        self.assertEqual(len(finite), 1)
        self.assertAlmostEqual(float(finite[0]), -2, places=8)
        self.assertTrue(all(abs(float(r)) > 0.1 for r in finite))

    def test_minima_json_and_human(self):
        inp = "-2 4 4 -8\n"
        human = subprocess.run([sys.executable, psi.__file__], input=inp,
                               text=True, capture_output=True, check=True).stdout
        self.assertIn("mins:\n  Ψ(−1.584962501) = −0.03703703704\n  Ψ(+∞) = −∞", human)
        json_result = subprocess.run([sys.executable, psi.__file__, "--json"],
                                     input=inp, text=True, capture_output=True, check=True)
        self.assertTrue(json_result.stdout.isascii())
        data = json.loads(json_result.stdout)
        self.assertAlmostEqual(data["mins"][0]["r"], -1.584962501, places=8)
        self.assertEqual(data["mins"][1], {"r": "+inf", "psi": "-inf"})
        self.assertEqual(data["zeros"], [0])

    def test_invalid_input_nonzero_exit(self):
        r = subprocess.run([sys.executable, psi.__file__, '--json'], input='foo', text=True, capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('invalid number', r.stderr)
        self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()
