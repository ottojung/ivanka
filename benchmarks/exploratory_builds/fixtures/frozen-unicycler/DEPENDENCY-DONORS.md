# Unicycler dependency donor evidence (source-only, 2026-11-25)

This branch is `bench/minimal-8458f9e5-unicycler-20261123` plus one evidence
file. It is a direct child of frozen MiCall master
`8458f9e5d34c39a6694b1fb6a40e055d7ce89553`; no clinical source is changed and
no image, registry or pilot is claimed here.

## Tool pin

- Upstream: `https://github.com/rrwick/Unicycler` @
  `1429301eb24df9162f3c9386e8522f942594ae42` (GPL-3.0-or-later).
- Adapter commit: `5ad7874fe193043fa378063efc123018bff546da`.
- Native module: `cpp_functions.so` SHA-256
  `293f840641afaf17ef8b73858ecc7418553c453958bfece305f658223f2dc668`.

## SPAdes donor dependency (spades.py / spades-core)

Short-read Unicycler is a SPAdes optimiser; it calls external `spades.py`.
The `cpp_functions.so` hash above is **not** a SPAdes core hash.

- Source: `https://github.com/ablab/spades`, tag `v3.15.5` →
  `896694ce5c7a9050a6ffa9fccc950a4cd9f04363` (verified by `git ls-remote`
  2026-11-25T19:31Z; `assembler/VERSION` = `3.15.5`).
- Byte-pinned archive: `spades-v3.15.5.tar.gz` SHA-256
  `9848b69a3a6bab4621eb82b71cac6ed96b111c4109c754e283596e9fa3184b1b`,
  15,310,638 B.
- Licence: GPL-2.0-only (`assembler/LICENSE`). Redistributable with
  corresponding source and notices; bundled `ext/` licences also apply.
  Do not relabel SPAdes as GPL-3.0.
- Donor path (NOT executed; needs guard deployment + free slot):
  `git clone … /opt/spades-src && git checkout 896694ce… && cd assembler &&
  PREFIX=/opt/spades ./spades_compile.sh -j2` → `/opt/spades/bin/spades.py`,
  `/opt/spades/bin/spades-core`.
- Binary SHA-256: **not attested**. Must be produced by a guarded donor job;
  fail closed on mismatch. No image may be built before this exists.

Full cross-tool evidence and the 20/20 source-only verification output are on
`ottojung/ivanka` branch
`px/attest-unicycler-savage-dependency-donors-20261125`.
