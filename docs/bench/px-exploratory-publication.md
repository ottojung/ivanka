# Public reporting of the ten PX explorers

The ten experimental assemblers in
`benchmarks/assembler_bench/exploratory_candidates.json` are **not
qualifying**. They are reported in a separate section of the Assembler Bench
site and never enter the frozen seven-way Ψ matrices, the 198-sample gate,
the 464-sample gate or any release claim.

## Data flow

1. `exploratory_policy.checked()` reads the private registry and admits only
   the pinned ten-tool roster with unchanged resource policy and source,
   adapter and image evidence.
2. `exploratory_publication.build()` exports only public identifiers, pin
   digests, receipt-verification flags and receipt-bound per-sample rows.
3. `exploratory_publication.publish()` validates the whole site snapshot
   before atomically replacing `site/bench/data/exploratory-candidates.json`.
   No frozen result file is opened for write.
4. `site/bench/exploratory.js` renders the roster. It shows source pins and
   honest stage labels; it computes no ranking, mean or Ψ value.

## Honesty rules enforced in code

- `source-pinned` candidates have `image_sha256: null`, no receipts and an
  empty sample list. The UI states that no image or benchmark exists.
- An image digest is published only with a source-bound image receipt.
  A pilot or benchmark stage additionally needs its own content-hashed
  receipt. A stage label without its receipt is rejected.
- Per-sample rows are accepted only from a file whose SHA-256 is recorded in
  the matching receipt for that exact tool, source, adapter and image. Rows
  use public aliases `PX-R###` (physical) or `PX-H###` (synthetic). Failed
  arms carry a failure reason and no score or runtime.
- The public snapshot contains no `psi`, no dominance matrix, no per-explorer
  score/mean/runtime aggregate and no private path or sample identifier.

## Commands

Validate the committed public snapshot:

    PYTHONPATH=benchmarks python3 -m benchmarks.assembler_bench.exploratory_publication --check

Regenerate it from the registry (no receipts or results are supplied):

    PYTHONPATH=benchmarks python3 -m benchmarks.assembler_bench.exploratory_publication

After a genuine admitted pilot, publish its receipt-bound per-case file;
repeat `--results` for additional cohorts:

    PYTHONPATH=benchmarks python3 -m benchmarks.assembler_bench.exploratory_publication \
      --results skesa=/path/to/skesa-physical-cases.json \
      --results skesa=/path/to/skesa-synthetic-cases.json

The registry must already show the corresponding promoted stage and receipts;
the publisher never promotes a tool on its own. A changed results file fails
the receipt digest check.

## Tests

    PYTHONPATH=benchmarks python3 -m pytest -q benchmarks/test_exploratory_publication.py
    PYTHONPATH=benchmarks python3 -m benchmarks.assembler_bench.site_build --output /tmp/px-pages-preview
    node --check site/bench/exploratory.js
