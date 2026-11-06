#!/usr/bin/env python3
"""Evaluate signed-power PSI, its real zeros, and its local minima.

Read whitespace- or comma-separated finite p_i from standard input.  The
constant n includes zero entries.  Requires only the Python standard library.
"""

import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
import json
import re
import sys


class PrecisionError(ValueError):
    """A root cannot be reliably distinguished at the chosen precision."""


def values_from_stdin(source):
    text = "\n".join(line.split("#", 1)[0] for line in source)
    tokens = [s for s in re.split(r"[\s,]+", text) if s]
    if not tokens:
        raise ValueError("expected at least one number on stdin")
    values = []
    for token in tokens:
        try:
            v = Decimal(token)
        except InvalidOperation as exc:
            raise ValueError(f"invalid number: {token!r}") from exc
        if not v.is_finite():
            raise ValueError(f"nonfinite input is not supported: {token!r}")
        values.append(v)
    return values


def grouped_terms(values):
    """Return increasing [(ln(|p|), net-sign-count)] pairs."""
    groups = Counter()
    for p in values:
        if p:
            groups[abs(p)] += 1 if p > 0 else -1
    result = []
    for magnitude, coefficient in sorted(groups.items()):
        if not coefficient:
            continue
        base = magnitude
        result.append((base.ln(), Decimal(coefficient)))
    return result


def normalized_value(terms, x):
    """Exponentially rescaled value, with the same sign and zeros as the sum."""
    largest = max(lam * x for lam, _ in terms)
    return sum((coef * (lam * x - largest).exp() for lam, coef in terms), Decimal(0))


def sign(value, scale=None):
    if scale is not None and abs(value) <= scale:
        return 0
    return (value > 0) - (value < 0)


def value_sign(terms, x):
    if x.is_infinite():
        return sign(terms[0 if x.is_signed() else -1][1])
    return sign(normalized_value(terms, x))


def critical_sign(terms, x):
    # A tangency is invisible to sign-change bisection. Critical points are
    # isolated to half the available digits so their squared root error is
    # below this precision-relative zero threshold. Near-multiple roots can
    # still require --precision to distinguish from an exact tangency.
    from decimal import getcontext
    threshold = Decimal(10) ** (12 - getcontext().prec)
    magnitude = sum((abs(c) for _, c in terms), Decimal(0))
    return sign(normalized_value(terms, x), threshold * magnitude)


def bracket(terms, left, right, left_sign, right_sign):
    """Turn infinite interval endpoints into finite sign-changing endpoints."""
    low = left if left.is_finite() else (min(Decimal(-1), right - 1) if right.is_finite() else Decimal(-1))
    high = right if right.is_finite() else (max(Decimal(1), low + 1) if low.is_finite() else Decimal(1))
    for _ in range(256):
        if value_sign(terms, low) == left_sign and value_sign(terms, high) == right_sign:
            return low, high
        if not left.is_finite() and value_sign(terms, low) != left_sign:
            low = low * 2 if low < 0 else low - max(Decimal(1), abs(low))
        if not right.is_finite() and value_sign(terms, high) != right_sign:
            high = high * 2 if high > 0 else high + max(Decimal(1), abs(high))
    raise PrecisionError("failed to bracket a root; increase --precision")


def bisect(terms, low, high, tolerance):
    sl = value_sign(terms, low)
    if sl == 0:
        return low
    if value_sign(terms, high) == 0:
        return high
    for _ in range(512):
        mid = (low + high) / 2
        sm = value_sign(terms, mid)
        if sm == 0 or high - low <= tolerance:
            return mid
        if sm == sl:
            low = mid
        else:
            high = mid
    raise PrecisionError("root could not be isolated to the requested precision")


def roots_of_sum(terms, tolerance):
    """Recursively isolate all real roots of a nonzero exponential sum.

    Divide by its smallest exponential, differentiate, and recurse; the
    derivative loses one term. Between successive derivative roots, the
    divided function is monotone, so each sign change has exactly one root.
    """
    if len(terms) <= 1 or all(sign(a) == sign(terms[0][1]) for _, a in terms):
        return []
    minimum = terms[0][0]
    shifted = [(lam - minimum, coef) for lam, coef in terms]
    derivative = [(lam, coef * lam) for lam, coef in shifted[1:]]
    critical = roots_of_sum(derivative, tolerance)
    boundaries = [Decimal("-Infinity"), *critical, Decimal("Infinity")]
    signs = [value_sign(shifted, x) if x.is_infinite() else critical_sign(shifted, x) for x in boundaries]
    roots = list(x for x, s in zip(boundaries[1:-1], signs[1:-1]) if s == 0)
    for i in range(len(boundaries) - 1):
        if signs[i] * signs[i + 1] < 0:
            lo, hi = bracket(shifted, boundaries[i], boundaries[i + 1], signs[i], signs[i + 1])
            roots.append(bisect(shifted, lo, hi, tolerance))
    roots.sort()
    return [r for i, r in enumerate(roots) if i == 0 or r - roots[i - 1] > tolerance]


def compute(values, digits=9, precision=65):
    if precision < digits + 20:
        raise ValueError("--precision must exceed --digits by at least 20")
    with localcontext() as ctx:
        ctx.prec = precision
        terms = grouped_terms(values)
        n = Decimal(len(values))
        psi = {
            "0": sum((Decimal(sign(p)) for p in values), Decimal(0)) / n,
            "1": sum((Decimal(sign(p)) * abs(p) for p in values if p), Decimal(0)) / n,
            "2": sum((Decimal(sign(p)) * abs(p)**2 for p in values if p), Decimal(0)) / n,
        }
        if not terms:
            return psi, "0", [], True
        maximum_sign = sign(terms[-1][1])
        if terms[-1][0] < 0:
            infinity = "0"
        elif terms[-1][0] == 0:
            infinity = Decimal(terms[-1][1]) / n
        else:
            infinity = "+inf" if maximum_sign > 0 else "-inf"
        tolerance = Decimal(10) ** (-(precision // 2))
        roots = roots_of_sum(terms, tolerance)
        return psi, infinity, roots, False


def local_minima(values, precision=65):
    """Find finite local minima and minimizing limits at either end of R.

    Returned (r, Psi(r)) pairs use Decimal for finite coordinates/values,
    "+inf"/"-inf" for infinite coordinates or divergent limits, and "R"
    when every real r minimizes a constant Psi. Infinite endpoints describe
    infima approached along that tail, not attained values.
    """
    with localcontext() as ctx:
        ctx.prec = precision
        terms = grouped_terms(values)
        n = Decimal(len(values))
        derivative = [(lam, coefficient * lam) for lam, coefficient in terms
                      if lam]
        if not derivative:
            return [("R", sum((coefficient for _, coefficient in terms),
                              Decimal(0)) / n)]

        tolerance = Decimal(10) ** (-(precision // 2))
        stationary = roots_of_sum(derivative, tolerance)
        # Between successive derivative zeros the sign is constant.
        # The signs at both infinities come from the extreme exponential.
        directions = [value_sign(derivative, Decimal("-Infinity"))]
        for left, right in zip(stationary, stationary[1:]):
            midpoint = (left + right) / 2
            direction = value_sign(derivative, midpoint)
            if direction == 0:
                raise PrecisionError("cannot distinguish adjacent stationary points")
            directions.append(direction)
        directions.append(value_sign(derivative, Decimal("Infinity")))
        if not stationary and directions[0] != directions[-1]:
            raise PrecisionError("failed to isolate a stationary point")

        def tail_value(positive):
            lam, coefficient = terms[-1] if positive else terms[0]
            grows = lam > 0 if positive else lam < 0
            if grows:
                return "+inf" if coefficient > 0 else "-inf"
            return coefficient / n if lam == 0 else Decimal(0)

        result = []
        if directions[0] > 0:
            result.append(("-inf", tail_value(False)))
        for index, r in enumerate(stationary):
            # Derivative zeros with no - to + transition are not minima.
            if directions[index] < 0 and directions[index + 1] > 0:
                value = sum((coefficient * (lam * r).exp()
                             for lam, coefficient in terms), Decimal(0)) / n
                result.append((r, value))
        if directions[-1] < 0:
            result.append(("+inf", tail_value(True)))
        return result


def format_decimal(value, digits):
    if not value:
        return "0"
    # Significant figures, with enough precision for magnitudes near zero.
    return format(value, f".{digits}g")


def json_decimal(value, digits):
    value = format_decimal(value, digits)
    try:
        result = float(value)
    except OverflowError:
        return value
    if (not (float("-inf") < result < float("inf"))) or (result == 0 and Decimal(value) != 0):
        return value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit ASCII-only JSON (infinities are strings)")
    parser.add_argument("--digits", type=int, default=10, help="Significant figures in output (default: 10)")
    parser.add_argument("--precision", type=int, default=65, help="Decimal working precision (default: 65)")
    args = parser.parse_args(argv)
    if not 1 <= args.digits <= 40:
        parser.error("--digits must be between 1 and 40")
    if args.precision < args.digits + 20:
        parser.error("--precision must exceed --digits by at least 20")
    if args.precision > 300:
        parser.error("--precision must not exceed 300")
    try:
        numbers = values_from_stdin(sys.stdin)
        psi, infinity, roots, identically_zero = compute(numbers, args.digits, args.precision)
        mins = local_minima(numbers, args.precision)
    except (ValueError, InvalidOperation) as exc:
        parser.error(str(exc))
    if args.json:
        output = {
            "psi": {key: json_decimal(value, args.digits) for key, value in psi.items()},
            "psi_at_positive_infinity": json_decimal(infinity, args.digits) if isinstance(infinity, Decimal) else infinity,
            "zeros": "R" if identically_zero else [json_decimal(x, args.digits) for x in roots],
            "mins": [
                {"r": json_decimal(r, args.digits) if isinstance(r, Decimal) else r,
                 "psi": json_decimal(value, args.digits)
                        if isinstance(value, Decimal) else value}
                for r, value in mins
            ],
        }
        print(json.dumps(output, ensure_ascii=True, allow_nan=False, indent="\t"))
    else:
        def human(value):
            return str(value).replace("-", "−").replace("inf", "∞")

        for power, val in psi.items():
            print(f"Ψ({power}) = {human(format_decimal(val, args.digits))}")
        print(f"Ψ(+∞) = {human(infinity)}")
        label = "{ r : Ψ(r) = 0 } = "
        if identically_zero:
            print(label + "ℝ")
        elif not roots:
            print(label + "∅")
        else:
            zeros = ", ".join(human(format_decimal(x, args.digits)) for x in roots)
            print(label + "{ " + zeros + " }")
        print("mins:")
        for r, value in mins:
            if r == "R":
                print(f"  Ψ(r) = {human(format_decimal(value, args.digits))} (all r ∈ ℝ)")
            else:
                argument = format_decimal(r, args.digits) if isinstance(r, Decimal) else r
                output = format_decimal(value, args.digits) if isinstance(value, Decimal) else value
                print(f"  Ψ({human(argument)}) = {human(output)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
