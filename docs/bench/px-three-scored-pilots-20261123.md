# PX: three source-attested pilot assemblers — November 23, 2026

**Historical checkpoint.** The next verified publication includes Minia;
see [four-source-pinned pilot report](px-four-scored-pilots-20261123.md).

This is **NONQUALIFYING**, and does not change the frozen seven-image
manifest `9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f`
or any of the original 4,634 physical/synthetic attempts.

All three dedicated MiCall fork adapter branches descend from frozen commit
`8458f9e5d34c39a6694b1fb6a40e055d7ce89553`. Each candidate had a
hash-verified actual native binary, isolated OCI build, and successful physical
and synthetic MiCall pilot with final `conseq.csv` and `nuc.csv` output.
The runner checked the exact container identity and its cleanup. All scores
were computed post hoc, without exposing references or hidden truths to assembly.

| Assembler | Image SHA-256 prefix | Physical R053 score | Synthetic pilot |
| --- | --- | ---: | --- |
| SKESA | `ed0770eec1d6` | 298 | H192 mixed HCV/HIV: 4863.20 |
| IDBA-UD | `36ae5c23a20e` | 298 | H452 single-truth: 9937.75 |
| Fermi-lite | `3cfc23c8b1bd` | 298 | H452 single-truth: 9937.75 |

The physical sample is the **same source input** across all three. The
IDBA-UD and Fermi-lite synthetic pilots share the same H452 source input;
SKESA's H192 is a **different sample**, so their synthetic scores must **not**
be interpreted as a paired difference.

**Input provenance repair:** the original IDBA-UD and Fermi-lite success
receipts misnamed a digest of only read 1 as `source_input_sha256`. These
receipts are retained, but **not** used to certify paired inputs. Supplemental
versioned receipts independently verified both original R1 and R2 bytes against
the source physical MD5 and synthetic SHA-256 manifests, matched canonical
one-based public aliases R053/H452, and included new combined paired SHA-256
digests. The corrected scored receipts have SHA-256:

- IDBA-UD: `ee7137606ef3600f645b9d2c448ed0748e8c0b704aacb00293ab1e9c4818b3c0`
- Fermi-lite: `61d6ea9f38560202d25fddcdccda38e4fd920a1ea760e73b8deafd82e74c7524`
- SKESA: `9a650fa05e007c79f96b79facf41c70202fb8cb474546b591df9af82cd8e79c3`

The IDBA-UD image uses a reproducibly hash-attested upstream source patch
raising its short-sequence capacity from 128 to 512 to support the original
Illumina read lengths. Original rejected pilot attempts remain preserved.

The displayed pilot runtime is **external launcher wall time including container
startup and cleanup**, not the frozen seven's in-container monotonic timing.
The original seven-way acceptance gate and Ψ matrix exclude every PX arm.
The remaining **seven** additional image/pilot pairs are not yet verified.
No full 198-case or 464-case PX cohort is claimed complete.
