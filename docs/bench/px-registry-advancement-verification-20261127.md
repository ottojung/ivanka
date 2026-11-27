# V9ro PX non-slot verification and registry-advancement increment (2026-11-27)

Agent: s6E0GIuQVzKz6iL96ybsxA-psoas | host: marceline-dev (verified `hostname`) |
repository: https://github.com/ottojung/ivanka.git | no Viche/billy-dev work, no
shared checkout edited. All work in `/tmp/opencode/s6E0GIuQVzKz6iL96ybsxA-psoas-v9ro-20261127/`.

Scope: read-only live verification plus a prepared, policy-verified registry
advancement artifact. No cutover, STOP/s6 action, supervisor down/up, second
worker, frozen-data edit, receipt mutation, live registry apply, pilot launch or
site edit. Ten additional assemblers remain NONQUALIFYING; V9ro stays OPEN.

## 1. Remote / pin re-derivation (claims treated as unverified)

- `git ls-remote origin refs/heads/main` = `76b80da081f212031a3997362621812a91017a94`.
  Fresh `--no-hardlinks` clone; main has nine "Publish neutral cohort-owned
  Assembler Bench results" commits after the handoffs' `cb867bcf` (latest
  `76b80da0` at 2026-11-27T23:07:02Z).
- Attested watchdog root `/workspace/ivanka-guard-pr535-staged-20261127` @
  `165a86b38c0bc29b4f8e0281a39ca59b909a6563`, s6 pid 235018, `drifted_modules=[]`.
- Attested supervisor control root `/workspace/ivanka-px-control-cutover` @
  `b8720600c9f10e71472b2b55210badeabc257a81`, s6 pid 420698, `drifted_modules=[]`.
- Live registry `private-frozen-ten-pilot-registry-20gib-20261124.json`,
  sha256 `98de47a3eb76b45d3c09b4f3aa62a299b57f67b30642c18541a062c2dc720a7a`
  (unchanged, equals proposal's bound value).
- `attest(phase=post_cutover)` from the clean clone: `ready=true`, `blockers=[]`,
  `kernel_enforcement=false` (guard code records userspace-observed enforcement
  only; cgroup2 mount is read-only). All four run-script pins byte-match.

## 2. Exclusive slot state (why no contention / no live apply)

- Exactly one `px_execution --supervise --armed` supervisor (pid 420698) holds
  the global worker lock; one active lease `soapdenovo2-1795820551288327359`;
  one live podman arm `px-soapdenovo2-64987e5897399075`, CID
  `7b03930943ef404f…`, image `bac9c5c1…`, `--memory=4000000000`, `--network=none`,
  `--cpus=2`, `--timeout 2400`, sample 63954A, output `soapdenovo2-PX-R055`.
- No active STOP sentinel (only historical `STOP.resolved-*`). Watchdog ALIVE
  pid 235018, fresh at `at_utc=1795821042.38`.
- Workspace free `68,282,183,680` B (~63.6 GiB), above the independent 32 GiB
  reserve (34,359,738,368 B). Per-arm 2400 s / 4,000,000,000 B sampled RSS retained.
- Conclusion: the exclusive runtime slot is verifiably held by the single armed
  worker. Per the delegation I did not contend; no second worker, no STOP/s6
  change, no live apply. The reviewed PenguiN migration fails closed at
  `verify_supervisor_idle` / lock / clear-lease gates while an arm is live.

## 3. Genuine physical execution continues (verified, not re-run)

- Receipt index `receipts/index.json`: 453 entries, sha256
  `a9ac991f10e8ef3e6b365880afc7f819c929546dcd6f639c4f099c6c85029758`;
  453/453 indexed receipt files present and byte-hash-matching (index grew from
  441 at the 22:26Z handoff, so the sole worker is still producing receipts).
- Fresh terminal receipts verified by index hash (examples): ray PX-R055
  success 532,172,800 B; idba-ud PX-R055 success 381,800,448 B; tadpole PX-R055
  failure 259,469,312 B; minia PX-R055 failure 259,031,040 B; soapdenovo2 PX-R054
  failure 3,710,316,544 B. Genuine failures preserved, not relabelled or retried.

## 4. Registry advancement candidate — PenguiN (source-pinned -> pilot, NONQUALIFYING)

Prepared, byte-exact and policy-verified; NOT applied live (see section 2).
All evidence independently re-derived with the repo's own policy module.

- Source: `soedinglab/plass @ ac83d8fa2fd315738afe675609a3dea05837cfea`.
- Adapter: `bench/frozen-8458f9e5-penguin-20261123 @ 8e7c55a3ebcaa4584cb09b1ac743bb5320bd1257`.
- Native ELF: `a175c7af8bed75b9add8229b30ee57380eaa4ffb67e351a8f5e91e43584bec0a`
  (source attestation `px_frozen_ten_attestation.json` and image receipt agree).
- Image: `sha256:458ff3d095ecf7db1b3622b56dafb9eec0947f2c3e567fcc3da3ea69f7dba924`;
  `podman --root /workspace/ivanka-exploratory-podman-20261121/store image exists`
  returned 0 (exact image present in the bound store).
- Image receipt `receipts/image-penguin-frozen-8458f9e5-8e7c55a3.json`, sha256
  `5ab7651c768aa29da9346cd5fa51a89d5d14ff757fbdff23e16eefbf6e7af7c1`.
- Paired pilot receipt
  `proposed-receipts/pilot-penguin-paired-canonical-proposed-20261126.json`,
  sha256 `37d24d30b5e96c9faa51ab7f9f29d8f1e29d4fa5eadc80690c158a7d8881a6bc`.
  Physical `success` (exit 0, paired reads, `conseq.csv` retained); synthetic
  `failure` (guard soft trip, 3,701,882,880 B sampled, `kernel_enforcement=false`).
  No score, no proxy zero, no scoring attestation, no seven-way inclusion.
- Read-pair provenance recomputed offline from the original FASTQ files:
  physical combined
  `f971b40df8e14d1ba4d499d60065badc64fb7ba6afb11d45ddf6c3e8b385039e`;
  synthetic (ultradeep-s003) combined
  `9411cc4e9464b629cd6e23461615d4e98972dacb5932f17a6f2017b5cf477013`.
- Candidate registry
  `/workspace/px-penguin-admission-20261126/proposed-registry-penguin-pilot-20261126.json`,
  sha256 `af634259fb68f90cc4acf4987ee5cd5068eae9578e559c80ba62925d24d41b7d`;
  it changes only the PenguiN row (`source-pinned` -> `pilot` plus image/pilot
  evidence), keeps `qualifying:false`, ten-tool roster, frozen manifest, 32 GiB
  floor, 2400 s / 4 GB policy and the original blockers.
- Reviewed migration `migrate_penguin_pilot.py`, sha256
  `14bc3abb8948a5afb9b8774bc0bac8af63ec22cefb490014a0a7bf9251db1cd1`
  (22/22 + 12/12 tests in the digest-fix logs). Operator ruling for
  NONQUALIFYING pilot readiness is recorded in `PENGUIN_ADMISSION_PROPOSAL_20261126.md`.
- My independent run of `verify_penguin_proposal.py` (6 tests) against the clean
  clone's policy module: **6/6 OK**, including `checked()` acceptance of the
  candidate with a temporary combined provenance root, honest failure fields,
  read-pair digests, lease teardown with exact CID, and recorded raw-argv gap.
- Residual gap recorded, not masked: raw argv/mount table was not retained by
  the historical launcher, so argv_sha256 cannot be recomputed independently.
- Apply blocker (precise): reviewed migration requires supervisor idle, clear
  lease, acquirable global lock and no STOP; all fail closed while the sole
  worker runs PX-R055. No operator-granted idle boundary or named slot exists
  for this agent. Therefore the candidate is prepared/verified, not applied.

## 5. Unicycler and SAVAGE de novo — no legitimate advancement evidence

Both remain `status=source-pinned`, `image_sha256=null`, no paired pilot.
Advancing either would require inventing binary/image digests or measurements.

- Unicycler: source `1429301eb24df9162f3c9386e8522f942594ae42`; SPAdes tag
  v3.15.5 = `896694ce5c7a9050a6ffa9fccc950a4cd9f04363`; native
  `cpp_functions.so` = `293f840641afaf17ef8b73858ecc7418553c453958bfece305f658223f2dc668`
  (NOT spades-core). Missing: `SPADES_CORE_SHA256` from an independently
  reviewed armed source-compile build. Operator ruling retains the exact
  upstream pin and rejects Debian `3.15.5+dfsg-2` version equivalence.
  No image, no physical/synthetic pilot.
- SAVAGE de novo: source `24e4d9fc35ef6a93e336949a9a8f98ed4ceef362`; donor
  prebuilt `ViralQuasispecies` = `199d97b7330df213f0adf99aaebb8f74d59806dfe90379f15dea28f0aa0c6590`
  is a host-built artifact, not an in-container rebuild. Missing:
  `VIRAL_QUASISPECIES_BUILD_SHA256` and `QC_BINARIES_BUILD_SHA256` from a
  reviewed armed build (quick-cliques tree `4b41a2ba…`). NumPy 1.16.6
  `e5cf3fdf…` attestation is metadata-plus-one-time-recomputation, not a
  retained artifact. No image, no paired pilot.

## Verdict

Typed: `partial / needs-integration`. Live pin chain, single-worker invariant,
single-worker receipts and reserve are verified. PenguiN registry advancement is
prepared and fully verified but not applied because the exclusive slot is held
and no idle-boundary grant exists. Unicycler/SAVAGE cannot be advanced without
fabricating evidence. V9ro stays OPEN; all ten assemblers NONQUALIFYING.
