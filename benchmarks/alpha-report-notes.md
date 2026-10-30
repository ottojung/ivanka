# Alpha reporting

The current qualification compares **all 18 IVA-eligible real samples** through the full
IVA/Ivanka MiCall pipeline in the same invocation, scoring all final MAX
consensus contigs against a fixed panel of pinned HIV, V3, HCV and HLA-B
references. Each sample must pass the 95% best-reference-score threshold
within its **own 1,200-second (20-minute) limit**. The whole batch has no
global 40-minute limit.

Use `python benchmarks/summarize.py --results RESULTS_DIR` for invocation
reports, and `--invocation ID` for fail-closed CI status. Partial samples,
missing reference hashes, mixed invocations, cached IVA and incomplete
MiCall outputs never establish a full-alpha pass.

Eligibility was established by inspecting the original frozen 20 real-input
cohort: two inputs repeatedly produced **zero final MAX consensuses in
successful unmodified IVA/MiCall controls**, both with and without
the all-projects option. They are excluded *before* examining Ivanka. The private
IVANKA_DATA/iva_eligibility_evidence.json records this evidence and the
original and eligible manifest hashes; --qualify validates it. Neither a
Ivanka failure nor an IVA timeout is grounds for excluding an input.
The complete eligible 18-input cohort remains mandatory.
