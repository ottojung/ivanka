# Reference-based MiCall remap (`micall-remap`) execution audit

Status: **source-only implementation and audit**. No image build, no MiCall
launch, no pilot/cohort run and no acceptance effect are claimed here. This is
the execution counterpart of Intent 017 / PR547; the additive display registry
and qualification-isolation view live in the parallel display change.

## Frozen base invocation (audited from bytes, not handoffs)

Common clinical master `8458f9e5d34c39a6694b1fb6a40e055d7ce89553`, tree
`4174e1cd850352788f7de5fe6cd66f12fbe27a70`.
`micall/drivers/sample.py` SHA-256
`8c4e4f130dd0eede5df0adba1c6842afd6ff6731ab64af4188a0b6cb91baf82c`;
packaged `micall/projects.json` SHA-256
`f5a5cfeb99c1b8f5b497cd7f416846b49141640de2a6b4b12293a3307c1790cd`.

In `analyze.py`, `--denovo` is `store_true`; it sets `RunInfo.is_denovo`, which
is passed as `use_denovo`. `Sample.process()` takes `run_mapping()`
(preliminary map + remap) when false and only then calls
`process_post_assembly(prefix="")`; the `prefix="unstitched_"` pass exists
solely in the de-novo branch. Therefore the reference-based analogue is the
ordinary command with **only** `--denovo` omitted. The timer entrypoint,
`--keep_scratch`, `--bad_cycles_csv /results/bad_cycles.csv`, `--all_projects`,
`--network=none`, `--cpus=2`, `--memory=4000000000` and the 2400 s wall cap are
unchanged. `MICALL_DENOVO_ASSEMBLER=ivanka` in the image environment is not a
mode selector; the CLI flag is.

Image reuse is honest and unbuilt: image ID
`da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad`, digest
`sha256:52e6bed1b52e2cb4c21cdde850b86e82caa96f05b82271978e9cae34305d5eff`.
No synthetic truth, HXB2 panel, hidden directory or historical result is
mounted into the reconstruction workflow.

## Mount resolution (operator directive, 22:38:58Z)

The old guarded launcher required exactly three mounts and hard-coded
`/reads/R1.fastq.gz` and `/reads/R2.fastq.gz`; binding individual originals
would have required four mounts, while binding a physical sample directory
would expose historical unstitched CSVs and stats. Resolved by **option (1)**:
`remap_runner.isolate_reads` creates a fresh directory whose only two entries
are hard links to the attested originals, keeping their original basenames.
Hard links are regular files, so no data is copied and no symlink can reach
outside the mount. `verify_isolated_reads` fails closed unless the directory
contains exactly those two names and both SHA-256 pins match. The
`micall_tail` read basenames are parametrized to those original names; this is
not a second mode difference — denovo and remap tails still differ by exactly
the single `--denovo` token. All other fail-closed checks (mount targets,
forbidden path components, numeric ceilings, retry budget, receipt fields)
are unchanged, and the default pinned names keep existing callers intact.

## Output identity and missingness

Mapping mode still writes `conseq.csv`, `nuc.csv`, `coverage_summary.csv`,
`genome_coverage.csv` and the alignment CSVs; final-MAX score, alignment,
coverage and runtime stay comparable. It does not write the de-novo contig
input, `nuc_detail`/`amino_detail`, `conseq_region` or any `unstitched_*`
output. Those metrics are `null` in `diagnostics` and named in `unavailable`
with an explicit not-applicable reason; no zero, contig or timing is
fabricated. Exact coverage is computed from the final MAX consensus in both
modes and remains comparable.

Peak RAM is ended, sampled whole-container process-tree RSS only, with
`kernel_enforcement: false`. The attested method/version/scope fields travel
with the receipt; launcher-process-group bytes are never promoted to the
comparable metric.

The `reference.panel_sha256` pin
`018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8` is the
immutable 33-reference **post-hoc scoring** panel. It is provenance for
measurement only and is never mounted or used for candidate selection. The
reconstruction reference is the frozen packaged `projects.json` identified
separately above. These two identities are deliberately distinct in every
receipt.

## Run identity, receipt and rows

Each attempted case has a distinct `run_id`
(`remap-<cohort>-<stamp>-<token>`), `attempt_id` and immutable receipt digest
(`ivanka.remap-diagnostic.receipt.v1`, canonical JSON SHA-256). The delivery
uses `ivanka.remap-diagnostic.rows.v1` with the display-bound fields `mode`,
`denovo`, `image_sha256`, `frozen_master_commit` and `invocation_sha256`, and
carries `qualification_claim: NONE`. Input manifests are derived only from the
original read-pair digests, never from truth genomes or scoring panels.

The diagnostic runner never imports a process launcher and never mutates a
public/private decision artifact. The receiver's `qualification_view` strips
the arm from those artifacts; the opt-in merge is the only route to display.

## Capacity blocker and validation

Measured free space was `32,334,376,960` bytes, below the shared
`32 * 1024**3 = 34,359,738,368` byte floor by about 2.03 GiB. `capacity_decision`
therefore reports `capacity_admitted: false` and `executed: false`; even above
the floor it still requires independent review and the exclusive shared slot.
No build or run was attempted.

Source validation at this branch head: `PYTHONPATH=benchmarks python3 -m
pytest -q benchmarks/test_remap_runner.py benchmarks/test_guarded_canary_launcher.py`
— 25 passed, 1 skipped (the skipped test runs when the parallel display module
is present; a non-skipping local test asserts the five display-bound fields,
and a temporary cross-check against the display author's actual module passed
all checks). No Rust source changed, so the Rust line/tree and formatting gates
are unaffected.
