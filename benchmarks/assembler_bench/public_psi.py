"""Neutral all-pairs observed-subset Ψ derived from public case measurements.

The private acceptance algorithm is reused unchanged, but the public layer
supplies metric-specific availability: a genuine alignment score may be
compared even when this assembler has no comparable in-container runtime.
Missing runtime stays no-data; wall-clock launcher time is never substituted.
"""
import math

from .psi_matrix import matrix as _private_matrix

PUBLIC_FIELDS = frozenset((
    "schema", "tools", "expected_samples", "observed_samples", "direction",
    "metrics", "interpretation"))


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def public_rows(run):
    """Rows whose arm status reflects each metric's own measured evidence."""
    rows = []
    for number, sample in enumerate(run.get("samples", [])):
        arms = {}
        for tool in run["tools"]:
            score = sample.get("score", {}).get(tool)
            runtime = sample.get("seconds", {}).get(tool)
            failed = tool in sample.get("failures", [])
            aligned = _number(score) and not failed
            timed = _number(runtime) and not failed
            arms[tool] = {
                # An alignment-only pilot is a real observation for alignment;
                # its missing runtime must not be read as a fast result.
                "status": "success" if aligned or timed else "failed",
                "score": score if aligned else None,
                "seconds": runtime if timed else None,
                "diagnostics": sample.get("diagnostics", {}).get(tool, {})}
        rows.append({"id": sample.get("alias", str(number)), "results": arms})
    return rows


def public_matrix(run):
    """Recompute all-pairs Ψ for exactly this cohort's roster, vocabulary-free."""
    expected = run.get("expected_sample_count", run.get("sample_count", 0))
    grid = _private_matrix(public_rows(run), run["tools"],
                           expected=expected, eligible=False)
    result = {key: grid[key] for key in PUBLIC_FIELDS if key in grid}
    result["tools"] = list(run["tools"])
    return result
