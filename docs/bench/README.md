# Assembler Bench — public evidence and publication contract

**Status:** public, privacy-safe report implementation for the original
198-sample MiCall benchmark and the disqualified historical synthetic
diagnostic. The **expanded seven-way gate is not qualified**. The new
HXB2-derived synthetic cohort and integrated seven-assembler comparisons
remain mandatory work under Intents 006–008.

## Source-of-truth and safety

The public static site lives at `site/bench/`, published under GitHub Pages
`/bench/`. All assets use relative URLs, so the site works under the
`/ivanka/bench/` GitHub project prefix or a custom root `/bench/`.
The public data are stored in `site/bench/data/runs.json`; its small
schema, independent certificate binding, alias-only sample reporting and
build validation are implemented in `benchmarks/assembler_bench/`.

The committed real 198 result was exported only from a complete
source-attested fresh MiCall run and its separately checked independent
qualification JSON. Input digest mismatches and incomplete numerical
qualification cause the exporter to fail. The exporter copies a strict
numeric allowlist and assigns nonidentifying `R001`…`R198` aliases
**without exporting original file names, paths, patient identifiers,
QNAMEs, or source mappings**. Private alias-to-input mapping, raw
FASTQs, original per-arm paths and individual protected metadata remain
off GitHub. The existing original 198 result is represented precisely
as a verified **original two-assembler pass**; its status never
masquerades as expanded seven-assembler qualification.

The legacy 400-case synthetic result is explicitly **ineligible**:
arbitrary random nucleotide genomic truth violates Intent 008; its
per-family alignment scores are descriptive and its timing was not
validly isolated from truth scoring. The viewer withholds that invalid
runtime, displays all reported failures, and prevents a misleading
all-exponent Ψ certificate. It is historical evidence only.

## Reproduce the public export (private data stays on the bench host)

```sh
python3 -m benchmarks.assembler_bench.publication \
  --real-jsonl /private/physical198/results.jsonl \
  --certificate /private/physical198/qualification-independent.json \
  --synthetic-jsonl /private/legacy400/orientation-corrected-diagnostics.jsonl \
  --output site/bench/data/runs.json
```

Before commit, independently inspect public data and run:

```sh
PYTHONPATH=benchmarks python3 -m unittest -q benchmarks.test_assembler_bench_publication
python3 -m benchmarks.assembler_bench.site_build --output /tmp/ivanka-pages-artifact
node --check site/bench/app.js
```

The build **rejects** unexpected private paths and file names, duplicate
or unsafe aliases, missing assets, ineligible runs mislabeled as passes,
and absent independent certificates. It never fetches private material
from GitHub Actions. Pages only publishes pre-vetted static artifacts
that are committed under `site/bench/`.

The publication workflow uploads `_site/bench/` to GitHub Pages. A
successful GitHub Action is not by itself a numerical or biological
passing benchmark; publication must be checked at the actual public URL.
Source hashes, image identities, separate cohort scores, error accounting,
and independent strict Ψ verdicts must be preserved for new runs.
