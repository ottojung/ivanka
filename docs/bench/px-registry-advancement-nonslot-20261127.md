# V9ro PX NON-SLOT registry evidence advancement (2026-11-27)

Owner: `agent-3jQaV1X67UgBZ2bB4UeEay-inherited` | host: `marceline-dev` (`hostname` verified
before any action) | repository: `https://github.com/ottojung/ivanka.git` (SSH and HTTPS
`ls-remote refs/heads/main` both returned `a0f6cdeea80583c3825c2ce1e5bfd3e7ee10835a`).

This is Ivanka work on the authorized host. No Viche / billy-dev work, no shared checkout
edited, no scheduler-provisioned worktree. All repository work is in a fresh
`--no-hardlinks` isolated clone under
`isolated clone (path withheld)` on the new topic branch
`agent/3jQaV1X67UgB-v9ro-registry-evidence-20261127`.

Every terminal handoff and the 23:15Z registry-advancement comment were treated as
unverified claims and re-derived from live durable artifacts. Nothing in this change is a
live mutation: no worker, STOP/slot/lease/supervisor/s6 action; no physical or synthetic
case started or interrupted; no frozen 198/464 data, frozen OCI image, IVA cache, original
MiCall output, receipt, live registry or published history touched. The single shared slot
is owned by another agent; this agent does not contend with it.

## 1. Re-derived live state (read-only)

| Fact | Verified value |
|---|---|
| Post-cutover attestation | `ready=true`, `blockers=[]`, `kernel_enforcement=false` |
| Watchdog code root / head | `guard root (path withheld)` @ `165a86b38c0bc29b4f8e0281a39ca59b909a6563` |
| Supervisor control root / head | `control root (path withheld)` @ `b8720600c9f10e71472b2b55210badeabc257a81` |
| Global worker lock | present, **locked** |
| Active lease | exactly one: `soapdenovo2-1795822263147226741` (observed during verification) |
| Live registry | `private-frozen-ten-pilot-registry-20gib-20261124.json`, sha256 `98de47a3eb76b45d3c09b4f3aa62a299b57f67b30642c18541a062c2dc720a7a` |
| Receipt index | `receipts/index.json`, sha256 `dffbc61e2acfa4d8f8e98e7e410165fabe8a2f0fd8b74577b27e8de0c98f9c2b`, **459 entries**, 459/459 indexed files byte-hash-matched |
| Workspace free | ~59.9 GiB, above the independent 32 GiB reserve |

The sole armed worker is genuinely continuing balanced physical execution (the receipt
index grew from 453 at the prior handoff to 459). Because the exclusive slot is held and
no idle-boundary grant exists for this agent, the reviewed registry migration fails closed
at `supervisor_idle` / `clear_lease` / `global_lock` / `STOP` gates. **No live apply was
attempted.**

## 2. Which tools are genuinely benchmarked vs still blocked

The live registry records seven tools at `status=pilot` with a pinned image and a canonical
paired pilot receipt, and three at `status=source-pinned` with `image_sha256=null` and no
pilot. This is confirmed by the genuine case receipts in the live index:

| Tool | Registry status | Terminal case receipts (success / failure) | Image digest |
|---|---|---|---|
| SKESA | pilot | 107 / 18 (125) | `ed0770eec1d6e7ca9…` |
| IDBA-UD | pilot | 32 / 24 (56) | `36ae5c23a20e86cf…` |
| Minia | pilot | 47 / 9 (56) | `d218919d19ac1e05…` |
| Ray | pilot | 53 / 3 (56) | `ef26acf721268212…` |
| Tadpole | pilot | 49 / 7 (56) | `c736c0c3607002a0…` |
| SOAPdenovo2 | pilot | 31 / 24 (55) | `bac9c5c1b45ea8e9…` |
| Fermi-lite | pilot | 50 / 5 (55) | `3cfc23c8b1bd7311…` |
| **PenguiN** | **source-pinned** | 0 / 0 in case index; genuine paired pilot receipt exists (below) | `458ff3d095ecf7db…` |
| Unicycler | source-pinned | 0 / 0 | none |
| SAVAGE de novo | source-pinned | 0 / 0 | none |

Genuine failures are preserved, not relabelled, retried or replaced with proxy zeros. All
case receipts carry `qualifying:false` and `terminal:true`. Exact per-tool counts, source
pins and adapter heads are in `px-registry-advancement-nonslot-20261127/evidence.json`.

## 3. PenguiN: source/image/pilot ready but not yet recorded — advancement verified

PenguiN is the only tool that is genuinely source-, image- and pilot-ready while still
recorded as `source-pinned` in the live registry. Every link below was independently
re-derived from durable artifacts (source attestation in the repo, the image receipt, the
paired pilot receipt, the native ELF on disk, and the bound podman store):

| Evidence | Exact value | Source of re-derivation |
|---|---|---|
| Source repo / pin | `https://github.com/soedinglab/plass` @ `ac83d8fa2fd315738afe675609a3dea05837cfea` | `px_frozen_ten_attestation.json` + live registry |
| Adapter branch / head | `bench/frozen-8458f9e5-penguin-20261123` @ `8e7c55a3ebcaa4584cb09b1ac743bb5320bd1257` | attestation + `adapter_branch_commits` |
| Native ELF | `a175c7af8bed75b9add8229b30ee57380eaa4ffb67e351a8f5e91e43584bec0a` | sha256 of retained `native/penguin-image/penguin` matches attestation and image receipt |
| OCI image | `sha256:458ff3d095ecf7db1b3622b56dafb9eec0947f2c3e567fcc3da3ea69f7dba924` | image receipt; `podman image exists` against the bound store (path withheld) returned rc=0 |
| Image receipt | `5ab7651c768aa29da9346cd5fa51a89d5d14ff757fbdff23e16eefbf6e7af7c1` | recomputed sha256; identical to live `receipts/image-penguin-….json` |
| Paired pilot receipt | `37d24d30b5e96c9faa51ab7f9f29d8f1e29d4fa5eadc80690c158a7d8881a6bc` | recomputed sha256 of durable `proposed-receipts/pilot-penguin-paired-canonical-proposed-20261126.json` |
| Physical run | `success`, alias `PX-R053`, CID `39b57480d6faf49c2e866f3e5232527a3a2f0326146ee2ccc13c1aafb6e09a01`; run receipt `55d4644a894eabb84b19e0aa51c32c91c0913c155c7ff226d4c8112601e33a0a` | durable `run-penguin-1795549407618791948.json`, exit 0, paired reads, `conseq.csv` retained |
| Synthetic run | `failure`, alias `PX-H452`, bound CID `eb36474e8bf4d188cf5041bdd4d46dbb1e44fa8d448008076538429088ccf9c4`, exit 137; run receipt `0b25a697ea39cca8dff9ac26951807786a98428fa135c73dc8359809276f92c2` | durable `run-penguin-1795554882243416925.json`; exact-CID teardown, container removed |
| Physical combined read digest | `f971b40df8e14d1ba4d499d60065badc64fb7ba6afb11d45ddf6c3e8b385039e` | recorded in paired pilot receipt |
| Synthetic combined read digest | `9411cc4e9464b629cd6e23461615d4e98972dacb5932f17a6f2017b5cf477013` | recorded in paired pilot receipt |
| Candidate registry | `af634259fb68f90cc4acf4987ee5cd5068eae9578e559c80ba62925d24d41b7d` | recomputed sha256; changes **only** the PenguiN row (`source-pinned` -> `pilot`), keeps `qualifying:false`, ten-tool roster, frozen manifest, 32 GiB floor, 2400 s / 4 GB policy |
| Reviewed migration | `14bc3abb8948a5afb9b8774bc0bac8af63ec22cefb490014a0a7bf9251db1cd1` | recomputed sha256 of `migrate_penguin_pilot.py` (22/22 + 12/12 tests in durable logs) |

Honest failure reason (synthetic, recorded verbatim in the receipt): the native Penguin
`nuclassemble` produced 1355 contigs in 7.87 s; the frozen referenceless stitcher tripped
the 3.7e9 userspace sampled-RSS soft guard and exited 137 (SIGTERM->SIGKILL); no final MAX
was produced (`stitched_contigs.fasta` empty). `kernel_enforcement=false`; the
3,701,882,880 B figure is **sampled process-tree RSS at soft trip**, not a kernel hard cap
and not a scored RSS. A later manual-followup receipt
(`19b5403066bfce99fd5b5a765b71e645db5e5f3e86de182393f52bf0b4cf6242`) proves exact-CID
teardown but is explicitly *not* a pilot arm and *not* scored.

**Failure classification (from the repo's own taxonomy):** `INFRASTRUCTURE_FAILURE_REASONS`
is `disk_stop`, `measurement_unavailable`, `identity_lost`, `binding_unavailable`; the
single extra attempt is authorized only after two exhausted infrastructure attempts.
The PenguiN synthetic trip is guard-limited (equivalent to `observed_rss_limit`), was
attempt 1 of a historical paired pilot, and is not a cohort arm — so it is **terminal, not
recoverable by authorized retry**. A re-run would be a new pilot arm requiring a named
slot, not a retry, and must never be reported as a scored measurement. Exact-CID teardown
is proved by the manual followup and is not itself a pilot arm.

There is **no score, no proxy zero and no scoring attestation** for PenguiN. The candidate
keeps `qualifying:false` and `seven_way_psi_release_inclusion:false`. Residual gap, recorded
not masked: the historical launcher did not retain the raw argv/mount table, so
`argv_sha256` cannot be independently recomputed.

## 4. Unicycler and SAVAGE de novo — precise blockers, no advancement

Both remain `status=source-pinned`, `image_sha256=null`, with no paired pilot. Advancing
either would require inventing evidence.

- **Unicycler**: source `1429301eb24df9162f3c9386e8522f942594ae42` (adapter head
  `5ad7874fe193043fa378063efc123018bff546da`); SPAdes tag v3.15.5 =
  `896694ce5c7a9050a6ffa9fccc950a4cd9f04363`; retained native `cpp_functions.so` =
  `293f840641afaf17ef8b73858ecc7418553c453958bfece305f658223f2dc668` (NOT spades-core).
  Missing: `SPADES_CORE_SHA256` from an independently reviewed armed build, an attested
  image, and a paired pilot. The operator ruling rejects Debian `3.15.5+dfsg-2` version
  equivalence. Source-only adapter verification is `status=PASS`, `scope=source-only`, no
  OCI build / no live container.
- **SAVAGE de novo**: source `24e4d9fc35ef6a93e336949a9a8f98ed4ceef362` (adapter head
  `0919ffa97f609b6f0b650ce834f0fc79822f18e5`); donor prebuilt `ViralQuasispecies` =
  `199d97b7330df213f0adf99aaebb8f74d59806dfe90379f15dea28f0aa0c6590` is a host-built
  artifact, not an in-container rebuild. Missing: `VIRAL_QUASISPECIES_BUILD_SHA256` and
  `QC_BINARIES_BUILD_SHA256` from a reviewed armed build, an attested image, and a paired
  pilot.

**Concrete prerequisites re-verified (read-only):** exact-commit fetches from the public
upstreams confirmed `rrwick/Unicycler@1429301e…`, `ablab/spades@896694ce…` (tag v3.15.5),
`HaploConduct/HaploConduct@24e4d9fc…` and `soedinglab/plass@ac83d8fa…`. The reviewed build
plans require `SPADES_BINARY_SHA256` (Unicycler) and build-attested
`VIRAL_QUASISPECIES_BUILD_SHA256` plus `QC_BINARIES_BUILD_SHA256` (SAVAGE); the corrected
recipes fail closed on those gates and on the pinned CPython 2.7.18 / NumPy 1.16.6 /
SciPy 1.2.3 donor archives (NumPy must be staged by the operator). No live image build is
permitted until a reviewed armed build guard attests those digests. Machine-readable
detail is in `evidence.json`; no separate report is introduced.

## 5. Artifacts on this branch

- `docs/bench/px-registry-advancement-nonslot-20261127.md` — this report.
- `docs/bench/px-registry-advancement-nonslot-20261127/evidence.json` — machine-readable
  per-tool pins, adapter heads, digests, case-receipt counts and the typed verdict.
- `docs/bench/px-registry-advancement-nonslot-20261127/penguin-advancement-descriptor.json`
  — **public-safe, content-addressed** advancement record: artifact basenames and SHA-256
  digests only, no host paths, no private identifiers, no credentials. **Not applied live.**
- The raw candidate registry (sha256 `af634259…`) and the reviewed migration/verifier
  scripts (sha256 `14bc3abb…` / `b1ac72b7…`) are **deliberately withheld** from this public
  branch: they carry absolute host paths. They stay at the owner's private durable location
  and must be used through the reviewed migration only at a granted idle boundary.
- Sections 2-4 and `evidence.json` now carry the concrete upstream pin checks, exact build
  prerequisites for Unicycler/SAVAGE, and the typed PenguiN failure classification; no
  additional report is introduced.

## Verdict

`needs-integration` (registry advancement prepared and verified, not applied live).
Seven tools have genuine case receipts and are already recorded as NONQUALIFYING pilots;
PenguiN is source/image/pilot ready and its verified advancement is published here for
review; Unicycler and SAVAGE remain blocked by missing build-attested dependencies. All ten
assemblers remain **NONQUALIFYING** and never enter seven-way acceptance. V9ro stays OPEN
until the full intended cohort has valid terminal evidence and the verified advancement is
applied by the slot owner at a reviewed idle boundary.
