# Unicycler / SPAdes source provenance and Debian-donor policy note (2026-11-26)

Scope: source-only documentation. No image build, no container, no frozen-MiCall
or upstream/main write, no substitution in any recipe or registry. V9ro stays
OPEN; Unicycler stays NONQUALIFYING.

## Exact pins (all independently re-derived this turn)

| Item | Exact value | Verification |
|---|---|---|
| Unicycler source commit | `1429301eb24df9162f3c9386e8522f942594ae42` | GitHub API commit lookup: author Ryan Wick, 2026-07-29T04:59:09Z, message "Add 2026 update to README", parent `ccfcc12f37fa28c333e16303d7760a9a0ba7d92e`, unsigned; changes are README-only |
| Unicycler adapter commit | `5ad7874fe193043fa378063efc123018bff546da` | `bench/minimal-8458f9e5-unicycler-20261123`, direct child of frozen master `8458f9e5…`; `px-three-tool-sourcing-20261125.json` pins exact |
| Unicycler native asset | `cpp_functions.so` SHA-256 `293f840641afaf17ef8b73858ecc7418553c453958bfece305f658223f2dc668` | cached at `native/unicycler-pinned/cpp_functions.so`; this is Unicycler's extension module, **not** SPAdes `spades-core` |
| SPAdes source commit | `896694ce5c7a9050a6ffa9fccc950a4cd9f04363` | `GET /repos/ablab/spades/git/ref/tags/v3.15.5` returns `object.sha = 896694ce…`, `object.type = commit` — exact tag-to-commit identity |
| SPAdes source archive | `spades-v3.15.5.tar.gz` SHA-256 `9848b69a3a6bab4621eb82b71cac6ed96b111c4109c754e283596e9fa3184b1b` | re-hashed in `dependency-evidence-cache-20261125/` |
| Frozen parent / master | `da795bbdbfbdd3c735c59d0ee008dae1781c68268b24298235e6b2cfe50a23ad` / `8458f9e5d34c39a6694b1fb6a40e055d7ce89553` | handoff pins, unchanged |

The earlier `px_frozen_ten_attestation.json` label "Unicycler/SPAdes core" for
`cpp_functions.so` is wrong; the donor handoff already records the correction.
The corrected Unicycler recipe in this branch checks `cpp_functions.so` against
`TOOL_BINARY_SHA256` and requires a separate, attested `SPADES_CORE_SHA256` for
`/opt/spades/bin/spades-core` (fails closed when absent).

## Debian donor: can it satisfy an explicit version policy?

Operator lead (V9ro, 17:33Z): frozen SPAdes image
`a0e7e98d143499fad423c2430aec061871015ee644b7d93d9cd0e29dc84c6c64` contains
Debian `spades 3.15.5+dfsg-2` (layer `edf8c768…`), `spades-core` SHA-256
`26e25faf6be54637d7029052f12d66019935872163cc291f3ed2ab76c1b6a13f`, matching
package md5 manifest, `VERSION 3.15.5`, wrapper `2c96c6fb…`, libexec `7962b7a3…`.

Analysis:

1. **Under the current policy: NO.** The handoff/registry pin is an *exact source
   commit* (`896694ce…`), and `exploratory_policy.checked()` requires a 40-hex
   source commit plus a source-bound image receipt. `3.15.5+dfsg-2` is a Debian
   repackaging of the 3.15.5 release: `+dfsg` removes non-free content and Debian
   applies its own patches/build flags. Equal upstream version number does **not**
   prove byte-identity with the pinned commit, and the operator explicitly
   warned that the Debian variant is not an attestation of the source commit.
2. **Only via an explicit operator policy decision.** Avoiding a duplicate SPAdes
   source compile by reusing that layer would require a recorded acceptance of
   *version-level equivalence* for this one dependency, plus complete
   package/runtime verification (`dpkg -V spades`, `VERSION`, wrapper/libexec
   hashes, `spades-core` SHA `26e25faf…`, dependency closure) and an updated
   attestation that names the package as the provenance basis. That is a policy
   change, not a silent substitution.
3. **Original SPAdes must not change.** The registry/handoff pin `896694ce…` and
   frozen upstream master `8458f9e5…` remain untouched in this branch; no image,
   layer, store or frozen MiCall file is copied or modified. If the operator
   accepts the Debian package, that decision must be recorded separately and the
   image receipt must disclose the package provenance honestly.
4. **Uncertain pin — operator action requested.** No policy acceptance exists on
   the board at the time of writing. The PX handoff asks the operator to rule
   explicitly; until then the corrected source-compile recipe is the only
   readiness artifact and the build remains gated on an attested `spades-core`.

## Non-claims

No duplicate compile avoided, no shared layer reused, no image built, no pilot
run, no registry/frozen upstream write, and no SPAdes provenance reclassified.
