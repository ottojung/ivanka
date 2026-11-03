"""Resumed historical samples are diagnostics, not a single 198-run qualification."""


def enforce_single_invocation(report, reused_count):
    """Never claim milestone success after combining separate executions.

    Reusing authenticated MiCall data is scientifically useful for
    diagnostics, but the frozen 198-sample milestone demands one complete,
    uninterrupted physical invocation with internally comparable timings.
    """
    if type(reused_count) is not int or reused_count < 0:
        raise ValueError("Invalid reused sample count")
    report["resumed_diagnostic_only"] = reused_count > 0
    if reused_count:
        report["milestone198_pass"] = False
        errors = report.setdefault("milestone198_errors", [])
        if "reused_records_not_single_invocation" not in errors:
            errors.append("reused_records_not_single_invocation")
    return report
