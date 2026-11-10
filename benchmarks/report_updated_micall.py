"""Read-only human report for new-MiCall physical IVA/Ivanka comparisons.

Only qualify_updated_micall.py may establish the full numerical gate.
Partial cohort PSI and all optional diagnostic PSI are explicitly nonqualifying.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from psi_acceptance import summarize


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as reader:
        for chunk in iter(lambda: reader.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def valid_pair(record):
    if record.get("status") != "finished" or record.get("failed") is not False:
        return False
    try:
        x = record["best_contig_acceptance"]
        return (record["iva"]["exit_code"] == 0
                and record["ivanka"]["exit_code"] == 0
                and all(finite_positive(v) for v in (
                    x["iva_score"], x["ivanka_score"],
                    record["iva"]["seconds"], record["ivanka"]["seconds"])))
    except (KeyError, ValueError, TypeError):
        return False


def format_number(x):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        if math.isinf(x):
            return "+∞" if x > 0 else "−∞"
        return f"{x:,.5g}" if math.isfinite(x) else "n/a"
    return str(x)


def clean(x):
    return str(x).replace("|", "/").replace("\n", " ").replace("\r", " ")


def render(records, digest, expected=198, strict=None, diagnostics=None):
    terminal = [r for r in records if r.get("status") != "started"]
    valid = [r for r in terminal if valid_pair(r)]
    excluded = [r for r in terminal if not valid_pair(r)]
    align = [r["best_contig_acceptance"]["ivanka_score"] -
             r["best_contig_acceptance"]["iva_score"] for r in valid]
    runtime = [r["iva"]["seconds"] - r["ivanka"]["seconds"] for r in valid]
    names = [r.get("sample") for r in terminal]
    duplicate = len(set(names)) != len(names)
    invocation = set(r.get("invocation") for r in terminal)
    image_ids = {
        arm: {r[arm].get("image_id") for r in valid}
        for arm in ("iva", "ivanka")
    }
    provenance_shape_ok = (not duplicate and len(invocation) == 1
                           and all(len(image_ids[arm]) == 1 for arm in image_ids))
    strict_ok = bool(strict and strict.get("results_jsonl_sha256") == digest
                     and strict.get("valid_pairs") == expected
                     and strict.get("samples_found") == expected
                     and strict.get("samples_expected") == expected
                     and strict.get("identical_micall_base_layers_verified") is True
                     and strict.get("original_fastq_sha256_verified") is True
                     and not strict.get("errors") and provenance_shape_ok)
    gate_passed = (strict_ok and not excluded and len(valid) == expected
                   and strict["real_data_numeric_gate_pass"] is True)
    if gate_passed:
        decision = "NUMERIC GATE PASSED — biological release NOT authorized"
    elif strict and strict.get("errors"):
        decision = "STRICT EVALUATOR REJECTED THE COHORT"
    elif strict_ok:
        decision = "NUMERIC GATE FAILED"
    else:
        decision = "NOT ATTESTED — do not claim qualification"
    lines = [
        "# Ivanka new-MiCall physical cohort report", "",
        "**Status: " + decision + "**", "",
        "Only two qualifying metrics: final MAX alignment and in-container",
        "runtime over 198 real samples. Both require signed-power Ψ(r)>0",
        "for every real r≥0, together with the unchanged 90% alignment floor,",
        "runtime limit and independently verified provenance.",
        "",
        "## Physical evidence", "",
        "| Item | Value |", "| --- | ---: |",
        f"| Started rows | {sum(r.get('status') == 'started' for r in records)} |",
        f"| Terminal rows | {len(terminal)} |",
        f"| Successful paired rows | {len(valid)} |",
        f"| Failed or incomplete terminal rows | {len(excluded)} |",
        f"| Expected real samples | {expected} |",
        f"| Duplicate terminal sample IDs | {duplicate} |",
        f"| Single invocation / images | {provenance_shape_ok} |",
        "",
        "Invocations: " + clean(", ".join(sorted(str(x) for x in invocation))),
        "Results SHA-256: " + digest,
    ]
    for arm in ("iva", "ivanka"):
        lines.append(arm.upper() + " images: " +
                     clean(", ".join(sorted(str(x) for x in image_ids[arm]))))
    lines += [
        "", "## Two qualifying metrics (subset scores descriptive only)", "",
        "| Metric | Wins / losses / ties | Ψ(0) | Ψ(1) | Ψ(2) | All nonnegative r? |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for name, deltas in (("Final MAX alignment, Ivanka−IVA", align),
                         ("Runtime seconds, IVA−Ivanka", runtime)):
        try:
            x = summarize(deltas) if deltas else None
            vals = (f"{x['gains']} / {x['losses']} / {x['ties']}"
                    if x else "n/a")
            lines.append("| " + name + " | " + vals + " | " +
                         " | ".join(format_number(x.get(k) if x else None)
                                    for k in ("psi0", "psi1", "psi2")) +
                         " | " +
                         str(x["positive_all_nonnegative"] if x else "n/a") + " |")
        except (ValueError, ArithmeticError, OverflowError) as exc:
            lines.append("| " + name + " | Solver failed: " + clean(exc) +
                         " | | | | |")
    # A strict positive Ψ(0) requires more runtime wins than losses.
    # Assign every not-yet-valid pair an imaginary future win; if even that
    # cannot beat already observed losses, rejection is mathematically final.
    runtime_wins = sum(delta > 0 for delta in runtime)
    runtime_losses = sum(delta < 0 for delta in runtime)
    maximum_additional_wins = max(0, expected - len(valid))
    if runtime_wins + maximum_additional_wins <= runtime_losses:
        lines += [
            "",
            "**Mathematical runtime no-go:** even crediting every remaining",
            f"not-yet-valid sample as an Ivanka win gives at most",
            f"{runtime_wins + maximum_additional_wins} wins against",
            f"{runtime_losses} observed losses, so strict Ψ(0)>0",
            "cannot be reached by this candidate. No new score threshold",
            "or missing-sample imputation was introduced.",
        ]
    lines += ["", "A positive partial PSI never qualifies an incomplete cohort.",
              "Any failed sample prevents the 198-sample physical gate.", "",
              "## Failed or excluded samples", ""]
    if excluded:
        lines += ["| Sample | Status | IVA exit | Ivanka exit | Sample time (s) |",
                  "| --- | --- | ---: | ---: | ---: |"]
        for r in excluded:
            lines.append("| " + " | ".join([
                clean(r.get("sample", "unknown")), clean(r.get("status")),
                format_number(r.get("iva", {}).get("exit_code")),
                format_number(r.get("ivanka", {}).get("exit_code")),
                format_number(r.get("total_seconds"))]) + " |")
    else:
        lines.append("No failed terminal records.")
    if strict and strict.get("errors"):
        lines += ["", "Strict attestation errors:", ""]
        lines += ["- " + clean(err) for err in strict["errors"][:60]]
        if len(strict["errors"]) > 60:
            lines.append(f"- {len(strict['errors']) - 60} additional errors")
    for name, diffs in (("Alignment", align), ("Runtime", runtime)):
        lines += ["", "## Ten most harmed samples — " + name, "",
                  "| Sample | Signed improvement |", "| --- | ---: |"]
        for delta, record in sorted(zip(diffs, valid),
                                    key=lambda pair: pair[0])[:10]:
            lines.append("| " + clean(record["sample"]) + " | " +
                         format_number(delta) + " |")
    lines += ["", "## Additional metrics (diagnostic only)", ""]
    if diagnostics is None:
        lines.append("No optional diagnostic PSI supplied.")
    else:
        lines += [
            f"Diagnostic terminal rows: {diagnostics.get('samples_seen', 'unknown')}.",
            f"Successful diagnostic pairs: {diagnostics.get('successful_paired_samples', 'unknown')}.",
            "",
            "| Optional metric | Paired | Missing | Ψ(0) | Ψ(1) | Ψ(2) | All r≥0? |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for metric, entry in sorted(diagnostics.get("metrics", {}).items()):
            x = entry.get("psi") or {}
            fields = [metric, entry.get("paired_samples"),
                      len(entry.get("missing_samples", [])),
                      x.get("psi0"), x.get("psi1"), x.get("psi2"),
                      x.get("positive_all_nonnegative")]
            lines.append("| " + " | ".join(
                clean(format_number(y)) for y in fields) + " |")
        lines += ["", "Optional diagnostics never certify data provenance and",
                  "must not influence the two numerical acceptance decisions."]
    lines += ["", "## Biological validity and unresolved uncertainty", "",
              "More contigs may multiply mapped depth without adding molecules.",
              "Higher alignment to a reference panel does not verify true",
              "minority-haplotype phase. Check genuine Q15 original read pairs,",
              "unsupported recombinants, mapping saturation, region shifts,",
              "independent genotype truth and synthetic known-truth controls.",
              "The report is a read-only rendering; no real data are changed.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_jsonl", type=Path)
    parser.add_argument("--strict-qualification", type=Path)
    parser.add_argument("--diagnostic-psi", type=Path)
    parser.add_argument("--expected-samples", type=int, default=198)
    parser.add_argument("--output", required=True, type=Path)
    a = parser.parse_args(argv)
    if a.expected_samples < 1:
        parser.error("sample count must be positive")
    with a.results_jsonl.open() as source:
        records = [json.loads(line) for line in source if line.strip()]
    strict = (json.loads(a.strict_qualification.read_text())
              if a.strict_qualification else None)
    diagnostics = (json.loads(a.diagnostic_psi.read_text())
                   if a.diagnostic_psi else None)
    report = render(records, sha256(a.results_jsonl),
                    expected=a.expected_samples, strict=strict,
                    diagnostics=diagnostics)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("x", encoding="utf-8") as dest:
        dest.write(report)


if __name__ == "__main__":
    main()
