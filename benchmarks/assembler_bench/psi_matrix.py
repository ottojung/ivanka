"""Neutral directed all-versus-all signed-power Ψ comparisons."""
import math
import sys
from pathlib import Path

# Reuse the independent all-exponent verifier, not sampled exponents.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from psi_acceptance import summarize  # noqa: E402

SCHEMA = "assembler-bench.directed-all-r-psi.v1"
METRICS = ("alignment", "runtime", "joint")


def _entry(rows, name, other, metric, expected, eligible):
    pairs = []
    for sample in rows:
        results = sample.get("results", {})
        a, b = results.get(name), results.get(other)
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        if a.get("status") != "success" or b.get("status") != "success":
            continue
        if metric.startswith("diagnostic:"):
            _, key, direction = metric.split(":")
            x = a.get("diagnostics", {}).get(key)
            y = b.get("diagnostics", {}).get(key)
        else:
            key = "score" if metric == "alignment" else "seconds"
            x, y = a.get(key), b.get(key)
            direction = "higher" if metric == "alignment" else "lower"
        if (type(x) not in (int, float) or type(y) not in (int, float)
                or not math.isfinite(x) or not math.isfinite(y)):
            continue
        pairs.append(x-y if direction == "higher" else y-x)
    observed = {"gains": sum(x > 0 for x in pairs),
                "losses": sum(x < 0 for x in pairs),
                "ties": sum(x == 0 for x in pairs),
                "mean_delta": round(math.fsum(pairs) / len(pairs), 12)
                if pairs else None}
    # This independent all-exponent proof is over the *paired observed
    # subset*, even when the complete-cohort qualification is unavailable.
    # It must never be silently promoted to a full-cohort certificate.
    subset = {"status": "no-data", "proof": None}
    if pairs:
        try:
            witness = summarize(pairs)
            subset = {"status": "dominates" if witness[
                "positive_all_nonnegative"] else "does-not-dominate",
                "proof": witness}
        except (ValueError, ArithmeticError, OverflowError):
            subset = {"status": "unresolved", "proof": None}
    base = {"status": "incomplete", "paired": len(pairs),
            "expected": expected, "proof": None, "observed": observed,
            "subset": subset}
    if not eligible or len(rows) != expected or len(pairs) != expected:
        return base
    if subset["proof"] is None:
        return {**base, "status": "unresolved"}
    # The whole source cohort and the paired subset coincide in this
    # branch, so the same signed-power proof is eligible for certification.
    return {**base, "proof": subset["proof"],
            "status": subset["status"]}


def _joint(score, runtime, expected):
    statuses = (score["status"], runtime["status"])
    if all(x == "dominates" for x in statuses):
        state = "dominates"
    elif "does-not-dominate" in statuses:
        state = "does-not-dominate"
    elif "incomplete" in statuses:
        state = "incomplete"
    else:
        state = "unresolved"
    return {"status": state, "paired": min(score["paired"], runtime["paired"]),
            "expected": expected,
            "proof": {"alignment": score["proof"], "runtime": runtime["proof"]},
            "observed": {"alignment": score["observed"],
                         "runtime": runtime["observed"]},
            "subset": {"alignment": score["subset"],
                       "runtime": runtime["subset"]}}


def matrix(rows, tools, *, expected, eligible, diagnostic_keys=()):
    """Row A versus column B; never infer transitivity or use a baseline."""
    rows, tools = list(rows), list(tools)
    if (not tools or len(tools) != len(set(tools))
            or not isinstance(expected, int) or expected < 1):
        raise ValueError("invalid assembler set or expected cohort")
    if len(rows) != len({row.get("id") for row in rows}):
        raise ValueError("duplicate sample identifier")
    # Only materialize additional proof grids when actual independently
    # sourced per-case diagnostic measurements exist. A one-case summary
    # cannot be promoted into a complete cohort's proof.
    present = {key for row in rows for result in row.get("results", {}).values()
               for key in result.get("diagnostics", {})}
    extras = tuple("diagnostic:" + key + ":" + direction
                   for key in diagnostic_keys if key in present
                   for direction in ("higher", "lower"))
    grid = {metric: {} for metric in (*METRICS, *extras)}
    for a in tools:
        for metric in grid:
            grid[metric][a] = {}
        for b in tools:
            if a == b:
                for metric in grid:
                    grid[metric][a][b] = {
                        "status": "self", "paired": 0, "expected": expected,
                        "proof": None}
                continue
            score = _entry(rows, a, b, "alignment", expected, eligible)
            runtime = _entry(rows, a, b, "runtime", expected, eligible)
            grid["alignment"][a][b] = score
            grid["runtime"][a][b] = runtime
            grid["joint"][a][b] = _joint(score, runtime, expected)
            for metric in extras:
                grid[metric][a][b] = _entry(
                    rows, a, b, metric, expected, eligible)
    return {"schema": SCHEMA, "tools": tools, "expected_samples": expected,
            "observed_samples": len(rows), "cohort_eligible": bool(eligible),
            "direction": "row-dominates-column",
            "metrics": grid,
            "interpretation": "all-r positive only; missing data is not a loss",
            "qualification_effect": "none"}
