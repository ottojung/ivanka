# Read-backed, reference-blind disjoint components — candidate (2026-11-23)

**Not qualified.** Original seven MiCall images and all 198+464 historical
checkpoints remain immutable. Only the candidate Rust executable changes;
the common MiCall source MUST remain frozen. Nothing here changes the
198-case, strict Psi(r)>0 for all r>=0, seven-way acceptance requirement.

The pinned native assembler (Ivanka source 84838353, image da795bbd)
already generated both HCV and 550-nt V3 read-backed paths
in hcv_v3_15pct-s000, but its default output selected **only one**
contig. The lost short component had been visible among its native paths;
this was not a deficit of the first 1000 seed candidates.

The candidate preserves the existing best path then considers additional
contigs in deterministic read-evidence order. Each must have >=128
original-read-pair hits, >=128 covered 31-mers, >=1/8 of the primary's
independent pair support, and >=75% new canonical 31-mers (minimum 128).
No reference, original/IVA score, hidden truth, or known sample identity
participates in admission. Output stays bounded to 16 contigs, including
all tiles. All existing circle repair and read-backed tiling apply unchanged.

Evidence from *isolated nonqualifying* executions:

| Frozen dataset diagnostic | Earlier native output | Candidate native output |
| --- | --- | --- |
| HCV+V3, 15%, sample 000 | 9635 nt only | 9635 + 550 nt |
| HCV+V3, 30%, sample 000 | 9632 nt only | 9632 + 550 nt |
| coverage hole, sample 000 | 4437 nt only | 4437 + 4145 nt |
| HCV+HIV, 15%, sample 000 | 9632 nt only | 9632 + 9577 nt |

Physical R042 63902A-V3-3-V3LOOP_S39 was also run through the
**unchanged frozen MiCall image**, overlaying only the Rust candidate
binary; because the binary was built under Guix, the isolated pilot
read-only-mounted /gnu/store for its dynamic loader. That is not a
qualifying runtime environment. Final 33-reference MAX local alignment
was **102 -> 102**, a documented non-improvement, not a passing P0 gate.

Native pilots had a 120s timeout and 4GB address-space limit. The
single physical MiCall pilot used the 2400s/4GB container bounds and
a >=24GiB disk floor. Output and SHA receipts live separately under
/workspace/ivanka-p0-diagnostics-native-frozen-20261123/.
Do not run the large 198/464 qualification until the new native source
is built as an independently attested dedicated Ivanka image with an
unchanged common MiCall; preserve all old successful results and
re-run only source-affected future Ivanka arms.
