# Source-only PX image engineering recipes

These files are **plans and fixes**, not build evidence. They carry no image
digest, native binary hash attestation, pilot result or measured outcome.
Only the four already-certified explorers (SKESA, patched IDBA-UD, Fermi-lite,
Minia) have genuine images and paired physical/synthetic proofs.

The recipes fix or document the exact blockers found in guarded attempts:

- `soapdenovo2-nopic.patch`: the pinned `Makefile` links bundled non-PIC
  `libbam.a` with Debian's default PIE, producing `R_X86_64_32` relocation
  errors. The patch adds a link-only `LINK_FLAGS=-no-pie` to the top-level
  recipes so sub-directory C objects keep their original compilation and C
  linkage.
- `ray-rayplatform-c8d9fe2.json`: the pinned `ray` revision needs `RayPlatform`
  as a sibling source tree. The independent pin
  `c8d9fe2e1347be299f2e74dd8a0fc278b5a02e16` in `sebhtml/RayPlatform` supplies
  the missing headers.
- `tadpole-minimal-jre.json`: a full Debian JRE in one layer over the 5.79 GB
  frozen parent breaches the 8 GiB cumulative cap. The plan uses a pinned
  minimal `jlink` runtime and a trimmed, hash-verified BBTools tree.
- `native-requirements.json`: exact adapter/source pins, license evidence and
  native build requirements for SOAPdenovo2, Unicycler, PenguiN and SAVAGE.

Every later build must still use the guarded `exploratory_runtime.cli`: one
worker, >=32 GiB free, <=20 GiB cumulative project plus OCI, <=4 GB container
memory, <=2400 s, and only paired reads — never truth, a panel or a reference
in the assembler environment. `python3 benchmarks/test_px_experimental_recipes.py`
validates the pins, patch shape and resource bounds without running Podman.
