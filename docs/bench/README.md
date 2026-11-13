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
node --check site/bench/subjects.js
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

## Single-metric ranking and preservation of partial evidence

The first comparison section ranks **all MiCall assemblers by any one
selected metric**, not merely alignment or runtime. The unified
metric selector includes all 23 published CIGAR, mapping, depth,
concordance and contig diagnostic quantities alongside final MiCall
alignment and runtime. Visitors can order higher or lower, even for
descriptive quantities without an intrinsically beneficial direction.
The ordering is based on observed arithmetic mean, with numeric ties
broken alphabetically for deterministic display. Every ranked value
shows its own measured-case count and denominator; a missing metric
is **unavailable**, not scored as zero. A one-case diagnostic is
displayed as one of 400, never silently treated as the cohort mean.

The same selected metric drives the per-assembler chart, unit and
denominator explanation, detailed coverage table, per-case A/B
comparisons, sorting, and CSV export. Both the metric and numeric
direction can be shared via URL parameters. These numeric rankings
and observations are useful for exploring a running benchmark but
are **not** the strict all-exponent Ψ qualification.

The multiple-checkbox **Ψ-dominance matrix comes after the
single-metric rankings and case-level comparisons**. Every matrix cell gives the actual **YES / NO / ? / —** answer
for "Does row A strictly Ψ-dominate column B on ALL checked subjects?"
The cell never displays partial win counts or a numeric score in place
of the result. A YES requires an independent full-cohort all-r proof
for each checked metric; NO requires an independent disproof;
? denotes incomplete or unresolved evidence; — denotes the diagonal.
A legend spells out each state. Where signed-power
certification is unavailable, verified observed pairwise wins/losses,
ties, sample counts and mean advantages remain visible as descriptive
results **in the evidence panel and cell drill-down**, not as matrix
verdicts. A failed third assembler does not erase valid individual
MiCall outputs for the other two tools. Full-cohort qualification is
disclosed once in the page notice; incompleteness must never conceal
usable measurements or imply false dominance.

## Neutral metrics, CIGAR soft clipping and pairwise PSI

[Intent 009](../intents/009-neutral-metrics-and-pairwise-dominance.md)
makes Assembler Bench a **general framework for comparing arbitrary
MiCall-integrated assemblers**, not an Ivanka-only contest. The dashboard
has a selector for **both** assembler axes and a directed **A×B Ψ matrix**
with a searchable **checkbox list** for alignment, runtime and the
entire diagnostic catalog. Multiple selected subjects form a strict
all-r conjunction. For diagnostics, visitors explicitly choose whether
higher or lower is preferred; such a preference is not proof of biological
superiority. Every selected subject appears in the per-cell evidence.
The initial two-subject selection is alignment plus runtime.
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

The selected diagnostic metric now has its **own definition, unit,
source stage, denominator, comparison caveat, graph, and table**.
Selecting a different metric replaces the displayed measurements
instead of leaving a fixed soft-clipping table. Each diagnostic
can be added directly to the matrix subjects. User choices and metric
selection can be shared through URL query parameters.

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

## Independent fork-built OCI source and executable attestation

The builder-owned labels and a successfully built container do not, by
themselves, prove provenance. Before a fresh seven-way source-compliant
benchmark, independently verify *all seven* immutable MiCall image IDs:

    python3 -m benchmarks.assembler_bench.fork_image_attestation \
      --fork-checkout /path/to/clean/ottojung-MiCall \
      --base-image <full-image-sha256> \
      --images /path/to/all-seven-full-immutable-image-IDs.json \
      --output /private/verified-image-attestation.json

The private checkout must have the correct ottojung/MiCall origin, an
exact full commit SHA, and no tracked or untracked changes. The validator
rechecks the common-base OCI layers, the source labels, every assembler
binding, and the *installed* hashes of MiCall's committed dispatch
modules and each candidate's actual required executables. It also
requires a native Rust Ivanka ELF and the separately pinned IVA
samtools 1.3.1 compatibility executable. Missing or mutable image
references and mismatched source or tool bits fail closed.

The output includes exact source commit links under
https://github.com/ottojung/MiCall/tree/<40-character-SHA> and the
binary/source/image hashes for independent reproducibility. Keep
private sample FASTQs and all individual read identifiers outside the
public site. This attestation qualifies only source integrity; it
**does not** certify final MiCall alignment, runtime, any synthetic
truth, or the 598-case enhanced benchmark. A complete run must still
pass every earlier scientific and strict all-exponent PSI gate.
