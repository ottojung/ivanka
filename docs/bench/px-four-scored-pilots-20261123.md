# PX pilot evidence: four extra assemblers (2026-11-23)

**Nonqualifying, partial pilots only.** This record updates the
[three-tool checkpoint](px-three-scored-pilots-20261123.md), without modifying
any frozen original seven-tool MiCall image or any original attempt.

| Additional assembler | Actual OCI image SHA prefix | Physical R053 alignment | Synthetic H452 alignment |
|---|---|---:|---:|
| SKESA | `ed0770eec1d6` | 298 | *Different case*: H192 mixed HCV/HIV, 4863.20 |
| IDBA-UD (pinned 512-bp native patch) | `36ae5c23a20e` | 298 | 9937.75 |
| Minia | `d218919d19ac` | 298 | 9937.75 |
| Fermi-lite | `3cfc23c8b1bd` | 298 | 9937.75 |

All four completed genuine physical and synthetic MiCall runs on the same
frozen MiCall base; native tool sources, dedicated adapter branches, executable
SHA-256, image identities and final MAX outputs were separately checked.
Each canonical physical R053 run uses the same independently verified R1/R2
pair. Three synthetic H452 runs likewise share the same paired reads.
SKESA's mixed-virus H192 case **must not be compared as an H452 pairing**.

Minia source revision: `7b7239c69ecc63534a20fc0d0c2de30f0f67e31c`;
adapter commit: `ff75f0f2dca4b8b26dd8520638e4981d02484fbe`;
OCI SHA-256:
`d218919d19ac1e053e15905a222a1f05ae085d6f7e0e0e620817bd06913df08e`;
compiled native executable SHA-256:
`7903bad733d0a57f4c74b74823810581b15b0031d37c8125d283b7829d7c4023`.
Its new independently scored, paired-read canonical pilot receipt SHA-256:
`7bde32de21fc1669388a8c67bee6a0eb095e876e86d52a9ab1b6ddb525e1825a`.

**Method:** Physical final MAX posthoc local alignment against the same
33-reference panel SHA `018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8`.
Synthetic equal-weight abundant-truth score uses the frozen v2 scorer.
Reference panel and hidden truth never mounted into assembler containers.
Runtime in this exploratory view is external supervised total wall time,
including OCI setup/cleanup, and must not be identified as the frozen
original seven's in-container runtime metric. All source case IDs are private;
only verified one-based R/H cohort aliases appear in the public data.

**Completion:** 4/10 exploratory image+pilot pairs, none of the full
198-physical/464-synthetic ten-tool benchmark cohorts certified.
All PX arms remain outside the original seven-way Ψ qualification gate.
