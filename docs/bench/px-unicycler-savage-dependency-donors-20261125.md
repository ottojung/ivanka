# PX Unicycler / SAVAGE source-attested donor dependencies (2026-11-25)

Status: **source evidence complete; binary attestations blocked**. Source-only
work: no OCI build, no live container, no registry activation, no frozen MiCall
edit, no cfe-lab push.

Machine-readable evidence: `px-unicycler-savage-dependency-donors-20261125.json`.
Reproducer: `benchmarks/assembler_bench/verify_px_dependency_donors.py`
(SHA-256 `b63d4588b3867f12952c4a0d1b0169b6fcace1fda415efd9123ae645ec29c354`).
Verification output: `px-unicycler-savage-dependency-verification-20261125.json`
(**PASS 20/20**).

## Exact donor pins

| Dependency | Exact source | Version | Source SHA-256 | Redistribution |
|---|---|---|---|---|
| `spades-core` | `https://github.com/ablab/spades` tag `v3.15.5` → `896694ce5c7a9050a6ffa9fccc950a4cd9f04363` | `assembler/VERSION` = 3.15.5 | `9848b69a3a6bab4621eb82b71cac6ed96b111c4109c754e283596e9fa3184b1b` (15,310,638 B) | GPL-2.0-only (`assembler/LICENSE`); ship source + notices; bundled `ext/` licences apply. **Not** GPL-3.0. |
| `python2.7` | `https://www.python.org/ftp/python/2.7.18/Python-2.7.18.tgz`; cpython tag `v2.7.18` → `41ca0e7833977c2475722ccc3dd5c16865d96dc1` | `Include/patchlevel.h` = 2.7.18 | python.org `da3080e3b488f648a3d7a4560ddee895284c3380b11d6de75edb986526b9a814` (17,539,408 B); GitHub mirror `aa3822dc1615ccaf88352f1c4f2e5687d708be9a45c4c1c93cec64ee123dbec7` (17,517,628 B) | PSF-2.0, GPL-compatible; retain PSF notice. |
| `scipy` (SAVAGE runtime) | PyPI sdist 1.2.3 — last release accepting Python 2.7 (1.3.0 requires `>=3.5`) | 1.2.3 | `ecbe6413ca90b8e19f8475bfa303ac001e81b04ec600d17fa7f816271f7cca57` (23,335,997 B) | BSD. |

Both upstream tags were re-read with `git ls-remote` on 2026-11-25T19:31Z and
matched the pinned commits. All four archives were byte-verified from the
cache at `/workspace/ivanka-exploratory-ten-20261121/dependency-evidence-cache-20261125`.

## Donor build paths (recipes only — NOT executed; require guard + slot)

- SPAdes: `git clone … /opt/spades-src && git checkout 896694ce… && cd assembler &&
  PREFIX=/opt/spades ./spades_compile.sh -j2` → `/opt/spades/bin/spades.py` +
  `/opt/spades/bin/spades-core`. The binary SHA-256 must be produced by a
  guarded donor job; nothing is inferred.
- Python 2.7: verify `Python-2.7.18.tgz`, `./configure --prefix=/opt/python27 &&
  make -j2 && make install`, then install `scipy-1.2.3.tar.gz` into the same
  prefix → `/opt/python27/bin/python2.7` + importable scipy. Record exact
  `--version` output and binary SHA-256 from a guarded donor job. The earlier
  apt `python2.7 python-scipy` Dockerfile path is **not** source-attested.

## Adapter pins and minimal source-only builds

Frozen baseline: MiCall master `8458f9e5d34c39a6694b1fb6a40e055d7ce89553`;
frozen parent image `sha256:da795bbb…50a23ad` (`localhost/micall:minimal-8458f9e5-ivanka-20261117`).

- Unicycler: tool `1429301e…` (GPL-3.0-or-later), adapter branch
  `bench/minimal-8458f9e5-unicycler-20261123` @ `5ad7874fe193043fa378063efc123018bff546da`,
  direct child of frozen master. Adapter files `benchmark_assembler.py`
  (`3848b444…bdc0`, 1,389 B) and `denovo.py` (`7294ebb5…7c39`, 2,493 B) match
  the pinned git objects and the staged copies byte-for-byte. Native module
  `cpp_functions.so` = `293f840641afaf17ef8b73858ecc7418553c453958bfece305f658223f2dc668`.
- SAVAGE: tool `24e4d9fc…` (GPL-3.0), adapter branch
  `bench/frozen-8458f9e5-savage-20261123` @ `0919ffa97f609b6f0b650ce834f0fc79822f18e5`,
  direct child of frozen master. Adapter files `benchmark_assembler.py`
  (`687bdbbe…b919`, 1,243 B) and `denovo.py` (`7a5be8d7…eedb`, 2,487 B) match.
  Native `ViralQuasispecies` = `199d97b7330df213f0adf99aaebb8f74d59806dfe90379f15dea28f0aa0c6590`.
  `quick-cliques` was not attested by the donor; do not claim it.

Minimal adapter-only build/test (host, no container): `py_compile` of all four
adapter files plus an AST check that each `assemble(first, second, seeds)`
accepts but never passes the seed/reference argument to the tool CLI, that
`-1/-2` (Unicycler) and `-p1/-p2` (SAVAGE) are the only read inputs, and that
`--ref`/`--count_strains` are absent. All checks PASS. Both adapter diffs
against frozen master contain only allowlisted adapter paths — no clinical
MiCall source was touched.

Reproduce:

```
cd <this repo>
python3 benchmarks/assembler_bench/verify_px_dependency_donors.py --online \
  --out docs/bench/px-unicycler-savage-dependency-verification-20261125.json
```

## Concrete remaining execution blockers

1. **No spades-core hash.** `px_frozen_ten_attestation.json` labels
   `cpp_functions.so` as "Unicycler/SPAdes core"; it is only Unicycler's C++
   module. Correct that label before any Unicycler image claim.
2. **No python2.7 hash.** Frozen parent lacks python2.7; source-built donor
   binary hash and version output still missing.
3. **Common crash-safe guard not deployed.** PR473/PR474 source-reviewed,
   PR478 source-only validated; merge/deploy are owner/operator actions.
   PR488 (`1ba3a968`) and PR489 (`fa9173d9`) merged; aLx owns cutover.
4. **Worker slot held.** `.global-worker.lock` held by the PX cohort
   supervisor; one guarded worker only. Need STOP + lock handoff.
5. **Admission must be remeasured.** Handoff measured 38,317,387,776 B free
   (dry-run PASS); an earlier progress file measured 22,510,690,304 B free
   (fail closed). Re-run `df -B1 /workspace` and `admit()`; keep the
   34,359,738,368 B reserve and 1 GiB reservation.
6. **No images/pilots.** No Unicycler or SAVAGE receipts/images; no paired
   pilots. Registry activation stays with aLx.

Next: after guard deployment and slot grant, run one guarded donor job per
missing binary, record hashes/versions, then build adapter-only images from
the existing frozen parent (no duplicate base image) and only then run paired
pilots. Never promote the registry, edit frozen MiCall, or push to cfe-lab.
