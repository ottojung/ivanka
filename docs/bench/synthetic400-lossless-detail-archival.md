# Lossless HXB2-v2 synthetic400 MiCall detail archival

The **six original non-Ivanka assemblers** (IVA, Haploflow, MEGAHIT,
ABySS, SPAdes, Velvet) must finish their 198 physical MiCall attempts
before any of the 2,400 synthetic MiCall arms are admitted. The
synthetic comparator's source pin is
`d4a60b39328dfee6f2cb0b05f0d01bdd8a42ba8b`; no changing Ivanka
binary may be tested in either first-pass comparator dataset.

This benchmark-only maintenance utility is a **separate independent
source**. It does not change the fixed synthetic runner, MiCall source,
image IDs, source HXB2-derived FASTQs, hidden truth, 1800-second
timings, recorded scores or original `results.jsonl` journal.

Its source attestation checks the full immutable preflight bytes
(SHA256 `1788ec6864535583d68199f365f242fed67fb8db904aa54ee52711c9425cb66f`),
the exact six immutable source images ledger (SHA256
`93a30fd1cc8fdcb15a6e8c46d5dcacbdee39d44cb690cf9109cc30aad807b145`),
the resulting exact synthetic400 `run_manifest.json`, all 400
HXB2-v2 sample identities, original cohort manifest and individual
per-sample mate identity, source-subtree provenance, hidden truth
validation, and individually saved independent MiCall execution JSON.
It independently verifies the final MAX `conseq.csv` and stored
truth score before and after every archive.

After **a successful, durably journaled, age-verified** arm is frozen
for three minutes, ten named verbose CSVs may be compressed into
`checkpointed_details.tar.gz`, with original file SHA256, byte size,
mode and time recorded in `checkpointed_details.proof.json`.
Every other original file and coverage-map item is hashed and verified
before and after archival; the archive is fully decompressed, checked,
fsynced, and atomically installed before the redundant original CSV
copies can be retired. Every action is fsynced separately for
crash recovery.

**Never** archive or delete a failed/unknown arm, original FASTQ,
original hidden truth, original journal, final `conseq.csv`,
`nuc.csv`, `remap_counts.csv`, exact coverage, MiCall timing, logs,
coverage maps, full execution evidence or any OCI image. The ten
verbose optional CSVs remain precisely reconstructable.

A separately named restored directory can be populated and hash
verified using `--restore-arm 'EXACT_SAMPLE/assembler' --restore-to
/your/empty/path`. Restoration never edits original results.
Any importer that requires the original verbose CSV paths directly
must restore or archive-read them first. MiCall's original success
scores, metric JSON, and benchmark checkpoint validation do not
require the verbose files after the original extraction.

## After the physical comparator completion marker

```sh
ionice -c3 nice -n19 python3 -m benchmarks.maintenance.synthetic_detail_archive \
 --results /workspace/ivanka-comparators-400-20261116/results \
 --cohort /workspace/ivanka-hxb2-depth10000-400-v2-20261114 \
 --images /workspace/ivanka-maintenance-20261115/comparator-priority-20261116/comparator-images-built.json \
 --preflight /workspace/ivanka-maintenance-20261115/comparator-priority-20261116/synthetic400-prelaunch.source-check.r3.json \
 --audit /workspace/ivanka-maintenance-20261115/verified-synthetic-comparator-detail-archive-20261116 \
 --max-new 24 --loop --interval-seconds 90
```

Run as an independently supervised low-priority foreground process;
its supervisor's prerequisite gate must require the 1,188-arm original
physical comparator `attempt-finished.json` marker before launching.
Its own output is a separate archive, proof and action journal, not a
new MiCall execution or a benchmark requalification.

Synthetic first-pass failures remain failed; Podman ambiguity is
not biological inferiority. The separately proposed Podman wait
improvement must never be inserted into running fixed MiCall images
or retroactively modify original failed samples. Ivanka changes
and full seven-way qualification remain gated until the original
non-Ivanka physical198 and synthetic400 attempts complete.
