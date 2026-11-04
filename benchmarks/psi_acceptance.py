"""Strict PSI qualification, reusing the standalone PSI solver."""
from decimal import Decimal, InvalidOperation, localcontext

from psi import grouped_terms, roots_of_sum, value_sign


def summarize(values):
    """Check Psi(r)>0 for all r>=0, including r=0; fail closed on uncertainty."""
    try:
        with localcontext() as ctx:
            ctx.prec = 80
            data = [Decimal(str(value)) for value in values]
            if not data or any(not value.is_finite() for value in data):
                raise ValueError("Nonfinite or empty PSI cohort")
            n = Decimal(len(data))
            gains = sum(value > 0 for value in data)
            losses = sum(value < 0 for value in data)
            moments = {
                "psi0": Decimal(gains - losses) / n,
                "psi1": sum((Decimal(1 if p > 0 else -1) * (abs(p))
                              for p in data if p), Decimal(0)) / n,
                "psi2": sum((Decimal(1 if p > 0 else -1) * (abs(p)) ** 2
                              for p in data if p), Decimal(0)) / n,
            }
            formatted = {key: float(value) for key, value in moments.items()}
            if any(Decimal(str(formatted[k])).is_infinite() or
                   (not formatted[k] and moments[k])
                   for k in moments):
                raise ValueError("PSI moment cannot be represented as a float")
            result = dict(formatted, gains=gains, losses=losses,
                          ties=len(data)-gains-losses,
                          positive_all_nonnegative=False,
                          zeros_nonnegative=None,
                          psi_at_positive_infinity="0")
            terms = grouped_terms(data)
            if not terms:
                result["zeros_nonnegative"] = "R>=0"
                return result
            result["psi_at_positive_infinity"] = (
                "0" if terms[-1][0] < 0
                else float(terms[-1][1] / n) if terms[-1][0] == 0
                else "+inf" if terms[-1][1] > 0 else "-inf")
            # If the majority already fails, or the largest uncancelled
            # magnitude is a regression, all-axis positivity is impossible.
            if moments["psi0"] <= 0 or terms[-1][1] < 0:
                return result

            # Tail-dominance certificate: every signed count above every
            # magnitude threshold is nonnegative. O(n log n), no roots needed.
            tail = Decimal(0)
            dominates = True
            for _, count in reversed(terms):
                tail += count
                if tail < 0:
                    dominates = False
                    break
            if dominates:
                result["positive_all_nonnegative"] = True
                result["zeros_nonnegative"] = []
                return result

            # Any negative value is a conclusive counterexample. Find cheap
            # witnesses before attempting the much costlier full root search.
            trial = [Decimal("0.5"), Decimal("1.5"), Decimal("2.5")]
            trial += [Decimal(i) for i in (1, 2, 3, 4, 5, 6, 8, 12,
                                           16, 24, 32, 48, 64, 96,
                                           128, 192, 256, 384, 512, 768,
                                           1024, 2048, 4096)]
            for r in trial:
                if value_sign(terms, r) <= 0:
                    result["negative_witness_r"] = float(r)
                    return result

            # Otherwise isolate ALL finite real zeros (including tangencies).
            # A nearly-zero negative root is treated as a failure, not a pass.
            roots = roots_of_sum(terms, Decimal("1e-35"))
            boundary_guard = Decimal("1e-15")
            nonnegative = [float(r) for r in roots if r >= -boundary_guard]
            result["zeros_nonnegative"] = nonnegative
            result["positive_all_nonnegative"] = not nonnegative
            return result
    except (InvalidOperation, OverflowError, ArithmeticError) as exc:
        raise ValueError("Unresolved PSI") from exc
