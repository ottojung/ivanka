# Alpha reporting

The current qualification compares **all 20 real samples** through the full
IVA/Riva MiCall pipeline in the same invocation, scoring all final MAX
consensus contigs against a fixed panel of pinned HIV, V3, HCV and HLA-B
references. Each sample must pass the 95% best-reference-score threshold
within its **own 1,200-second (20-minute) limit**. The whole batch has no
global 40-minute limit.

Use `python benchmarks/summarize.py --results RESULTS_DIR` for invocation
reports, and `--invocation ID` for fail-closed CI status. Partial samples,
missing reference hashes, mixed invocations, cached IVA and incomplete
MiCall outputs never establish a full-alpha pass.
