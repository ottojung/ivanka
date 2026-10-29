# Alpha reporting

Use `python benchmarks/summarize.py --results <full-MiCall-results-directory>`
to view the actual full-MiCall runner's `summary-<invocation>.json` verdicts.
The command accepts `--invocation ID` for a fail-closed CI exit code and
`--json` for structured output.

**Current qualification requires all 20 frozen inputs** to finish both IVA
and Riva MiCall arms in one invocation under the **40-minute global limit**.
Never combine results from multiple runs or use cached IVA as proof of a
both-arm qualification. The report checks hashes, samples, timing, and the
runner's authoritative `full_alpha_pass` flag. Reporting an unsuccessful
run does not make it qualify.
