# Assembler Bench — public evidence and publication contract

**Status:** public, privacy-safe report implementation for the original
198-sample MiCall benchmark and the disqualified historical synthetic
diagnostic. The **expanded seven-way gate is not qualified**. The new
HXB2-derived 400-case cohort is now generated with pinned, replayable
ancestry; integrated seven-assembler MiCall execution, validated numeric
gates and a public result for this cohort remain mandatory work under
Intents 006–008.

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

## Verified incomplete HXB2 MiCall snapshots on Pages

Assembler Bench now supports source-attested, privacy-safe publication of
partial *real MiCall* seven-assembler HXB2 results. It retains the old
original-198 gate PASS and ineligible historical random-genome synthetic
data as distinct runs. No unfinished HXB2 run is a seven-way PASS.

An export includes only complete per-case checkpointed records: all seven
immutable tool identities, correct original paired-read provenance,
replay-verified HXB2 ancestry, pinned benchmark source and timer hashes,
and independently checked final MiCall output SHA256. Public results
contain anonymous H001-style sample aliases, family tags, actual final
dominant-consensus known-truth score, in-container monotonic MiCall time,
and explicit failures. Missing/failed arms have null scores and runtimes,
not fabricated zero-score competitor losses. Protected filenames, paths,
truths and patient metadata never appear.

To add a versioned snapshot, run this on the trusted benchmark host:

    PYTHONPATH=benchmarks python3 -m benchmarks.assembler_bench.hxb2_preview \
      /workspace/ivanka-hxb2-seven-way-400-full-20261112 \
      --public-json site/bench/data/runs.json

The exporter appends an immutable run identifier based on the number
of completed seven-arm cases and refuses duplicates or altered proof.
A reviewed Git commit publishes the static data through the existing
GitHub Pages workflow. Do not auto-sync private working directories.

Check with the publication and HXB2 preview unittest modules, the
site builder, node --check on site/bench/app.js, and independent page
access. No partial result can certify either all-r signed-power gate.

## Neutral metrics, CIGAR soft clipping and pairwise PSI

[Intent 009](../intents/009-neutral-metrics-and-pairwise-dominance.md)
makes Assembler Bench a **general framework for comparing arbitrary
MiCall-integrated assemblers**, not an Ivanka-only contest. The dashboard
has a selector for **both** assembler axes and a directed **A×B Ψ matrix**
covering alignment, runtime and their joint strict all-exponent result.
A cell is dominant only when its full cohort is present and the independent
all-r numerical prover certifies strict Ψ(r)>0 for every r≥0.
Incomplete, ineligible and unresolved relationships are never guessed
from averages or intermediate Ψ(0/1/2) points. Pairwise ordering is not
assumed transitive. The original real 198-sample result provides a
proven 2×2 example, whereas the partial seven-tool HXB2 preview correctly
has **no certified dominance edges**.

MiCall's existing `nuc.csv` soft-clip aggregate and the **read-alignment
CIGAR** metrics are different measurements. The instrumented synthetic
runner now records both for every executed arm, successful or failed:
mapped/unmapped primary read records, secondary/supplementary placements,
MAPQ, matched/inserted/deleted bases, soft-clipped reads/events/bases,
left/right clipping, clipped-read fraction, clipped bases per 1,000 mapped
read bases, and clip events per 1,000 primary mapped reads. It also retains
the existing MiCall Q15-depth, breadth, concordance, contig and other
diagnostics, with explicit source stage and missing denominators.
The measurements are descriptive, **never replacement numerical gates**.

The published static `mapping-diagnostics.json` contains **one
independently checked, complete seven-assembler HXB2 clonal example**,
not the full cohort. Its 23 selected metrics are previewed across all
seven tools; source SAM hashes, known timing/score/image identities, and
the actual hidden-truth validation are checked before export. All
original read identifiers, FASTQs, local paths, per-read alignment
records and patient data stay off Pages. The data remain clearly
`INCOMPLETE` with respect to the 400-case and 598-case requirements.
Historical physical-198 data without retained SAMs are **unavailable**,
not imputed to zero.

The private benchmark host can prepare the versioned public artifacts:

```sh
PYTHONPATH=benchmarks python -m benchmarks.assembler_bench.publication \
  --real-jsonl /private/physical198/results.jsonl \
  --certificate /private/physical198/qualification-independent.json \
  --synthetic-jsonl /private/legacy400/orientation-corrected-diagnostics.jsonl \
  --output /tmp/bench-original-public.json

PYTHONPATH=benchmarks python -m benchmarks.assembler_bench.public_dominance \
  /tmp/bench-original-public.json --output site/bench/data/runs.json

PYTHONPATH=benchmarks python -m benchmarks.assembler_bench.public_metrics \
  /private/hxb2-micall-run/clonal-s000 \
  --public-json site/bench/data/runs.json \
  --out site/bench/data/mapping-diagnostics.json
```

The production public `site_build` validator independently recomputes
the pairwise Ψ matrix, checks all seven per-tool soft-clip counts against
their denominators, rejects falsified density/proof statuses and any
sensitive path or identifier, and checks relative Pages asset links.

## Fork-only MiCall source and build provenance

[Intent 010](../intents/010-upstream-micall-read-only.md) permanently
prohibits any push, branch/tag write or pull request to
`github.com/cfe-lab/MiCall`. Read-only upstream research is fine.
[Intent 011](../intents/011-ottojung-micall-fork-provenance.md) requires
all actual assembler integrations and every MiCall runtime image
to come from **`github.com/ottojung/MiCall` at exact immutable commits**,
with public links to those full fork SHAs.
The current published images **do not yet have verified fork-build
attestations**, so the dashboard explicitly labels them historical
or unverified. The fork guard rejects upstream/unknown write targets
and moving branch/invalid commit URLs. Existing historical numeric
results are preserved but do not satisfy the new image provenance
condition until a genuinely fork-built, requalified run exists.
