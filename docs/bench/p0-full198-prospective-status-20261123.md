# Physical P0 status: authentic 198, all-r cross-version diagnostic, IVA retesting

Verified on marceline-dev, November 23, 2026, 03:15 UTC. **This is NOT a seven-way or clinical-release qualification certificate.**

## All 198 authentic future-source Ivanka executions are complete

The draft common MiCall native/G2P exact-contig correction is [ottojung/MiCall PR #22](https://github.com/ottojung/MiCall/pull/22) at commit a6c8195d95076325a07661f7f625a86361dfed45. Original frozen seven-assembler runs and images were not modified.

- All **128/128 source-affected physical** executions succeeded: 125 ordinary cases and three preselected controls.
- All **70/70 source-unique physical** cases were genuinely timed under the corrected source: 69 ordinary cases and one preselected control. Their combined FASTA and final consensus stayed byte-identical to the frozen source, but previous runtime was **not** reused. All 69 ordinary scratch directories were archived losslessly and SHA verified. The unique-case controller finished successfully November 23 at 02:15 UTC.
- All inputs, outputs, source commits, runtime provenance and wall/memory budgets were checked. Limits remain **2400 seconds wall, 4,000,000,000 bytes sampled peak RSS**, with one P0 worker and the original physical disk reserve.

The read-only 33-reference panel audit SHA256 **87e71bf74ae90bac5807f62a0e9399e5d00ac126b246a2a082183d2383d179a6** is at /workspace/ivanka-p0-prospective-allprojects-20261122/p0-full198-crossversion-historical-psi-20261123T0300Z.json. It rehashed and reused all 125 prior scores and evaluated only 73 previously unscored cases; **no assembly was rerun**. The panel SHA256 is 018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8.

**Provisional ≥90% alignment floors: 198/198 against historical IVA, and 198/198 against the best available successful historical comparator.** Score and runtime signed-power Ψ are positive for **all real exponents r ≥ 0** on all six available historical paired-success subsets:

| Historical comparator | Paired cases | Mean alignment Ψ(1) | Mean runtime saved (s) Ψ(1) | Strict all-r score+runtime positive |
|---|---:|---:|---:|---|
| IVA | 198 | 4.081 | 112.454 | Yes |
| Haploflow | 171 | 16.269 | 265.720 | Yes |
| MEGAHIT | 188 | 28.069 | 168.847 | Yes |
| ABySS | 106 | 8.368 | 114.141 | Yes |
| SPAdes | 130 | 23.739 | 402.880 | Yes |
| Velvet | 157 | 113.688 | 149.730 | Yes |

**These are CROSS-VERSION only, because the historical rivals used the old common MiCall preprocessing.** Missing original comparator arms remain unavailable, not counted as wins. Even positive all-r on those subsets does not certify a fair updated seven-way gate.

For posthoc scoring performance, [Ivanka PR #392](https://github.com/ottojung/ivanka/pull/392) merged a mathematically identical local-alignment SIMD matrix that includes unresolved consensus symbol X. There is no altered objective, score threshold or reference/truth-driven assembly. 37 regression tests and six subtests passed; 90 random scalar-versus-SIMD alignments and real X-masked control score 579 agree.

**Independent installed-image MiCall source-parity check (November 23, 03:24 UTC):** inspected both immutable exact frozen IVA and Ivanka OCI image IDs with separate read-only, network-isolated non-benchmark Python containers; SHA-256-hashed ALL installed MiCall site-package Python files. IVA contains **177** files; Ivanka contains **178**; exactly **176 shared MiCall Python files are byte-identical**. The **only changed common source file** is *core/denovo.py* (the assembler-specific interface), and the **only extra Ivanka source file** is *core/benchmark_assembler.py* (the assembler adapter). There are no missing IVA-only files or other differences in shared MiCall Python sources. Common-file deterministic SHA map: **7c3784bdc3c33959efe25da9608dc919ccb20dabfa96eacd67d3d1499f15419c**. The exact installed-package audit receipt is **/workspace/ivanka-p0-prospective-allprojects-20261122/p0-installed-image-common-source-parity-20261123T0325Z.json**, SHA-256 **fcfff4083487883507fc571f59a351c3920f4282ada4f3d3bbdff13a6f01b0**, with two full per-image hash manifests retained alongside. GitHub's source-commit comparison independently corroborates that other changes are assembler adapter, tests and image packaging metadata. Both prospective runners overlay the same corrected MiCall common Python source files; this establishes **shared installed MiCall Python code parity except expected assembler choice**. It does NOT certify that native binaries, all third-party dependencies, or other image layers are identical, and does not bypass the pending authentic 198-pair strict all-r or seven-way gate.

## Same-prospective-source IVA real 198-case testing is underway

A genuine **new** IVA cohort runs with the same corrected common MiCall source files overlaid read-only onto the independently pinned original IVA OCI image. The original frozen IVA cases are never overwritten or substituted. Pending further audit of the full image source diff, this is a **shared-common-source comparison**, not yet a formal byte-identical-base release assertion.

- Live S6 service: /run/service/ivanka-p0-updated-micall-iva; source-pinned Python controller: /workspace/ivanka-p0-prospective-allprojects-20261122/continue_future_iva_physical_p0.py SHA256 **354763b0c5c5195b6e021579d90268d661bb19ab9ac89457e5083fe1d6d00519**.
- Separate source-attested actual IVA runner SHA256 **7aad2acce485266220560e23cd48024092c80f0529cdf8e814ce6f386b46e370**, separately losslessly archiving cases with SHA256 **c686b185e55d2bc7369ad983235f4be63188b620ccfb7abb50848a1424d08f05**.
- The original IVA OCI ID is **16afbb25642dae3ce9e09eeaf22ddc3c41ecf02f71fadef910494ef564d39fd9**, and both prospective arms use MiCall patch SHA a6c8195d95076325a07661f7f625a86361dfed45 for sample.py and unique_contigs.py. Input hashes, all-project processing, 2400s/4GB, P0 disk floor plus 128× paired FASTQ reservation, one worker, failure receipts and scratch archives are preserved.
- An actual updated IVA R042 pilot scored **179** against corrected Ivanka **179** (both original scores **102**), IVA took **11.075 seconds**, Ivanka **10.793 seconds**. The important R042 correction is shared downstream, not an Ivanka-only gain.
- The first **26** same-source-timed paired cases were posthoc evaluated with a hash-validated incremental scorer. Their 90% score floor passes 26/26 and score Ψ is positive, but **runtime Ψ is negative** (20 losses, six wins, mean Ivanka 1.471s slower). Initial samples were ordered by FASTQ size and are unrepresentative; **this is an early warning, not a 198-case verdict**. One source-affected case had a 24.275s relative runtime loss (IVA 39.920, Ivanka 64.195). Preserve and investigate the evidence.
- The incremental scorer is at /workspace/ivanka-p0-prospective-allprojects-20261122/score_future_version_iva_incremental.py SHA256 **a435ec7749b12ba77f7ced479ddd741911d080099b1dd759ff003936df1dc371**. It independently rehashes old scores and only posthoc scores newly completed IVA outputs; its output is always incomplete/nonqualifying until **198/198** valid same-source pairs.

**Next:** finish new IVA 198 real-run source attestation and check same-version alignment and runtime Ψ for all r≥0. If failed, identify general reference-blind improvements and rerun only prospective affected cases with source changes. Full seven-way qualification still additionally needs valid rival arms under comparable common source. Common MiCall PR #22 stays draft until the scientific gate truly passes.

**P0 direct phase-timing diagnosis, November 23 at 03:23 UTC (33 genuine corrected-source paired samples):** Independently parsed timestamps and original native output FASTA from losslessly preserved scratch archives, with every original FASTQ/source/result receipt SHA checked. In **30 paired archived native outputs**, mean Ivanka native contigs **6.37**, IVA **1.57**. Across all **33 valid paired output/timing cases**, IVA assembly itself is **2.13 seconds slower** than Ivanka on average, yet IVA's subsequent MiCall remap/stitch stage is **12.37 seconds faster**, leaving total internal runtime **12.33 seconds faster**. The largest remap/stitch difference was **44.05 seconds in IVA's favor**. Independently SHA-attested, purely read-only phase diagnostic: /workspace/ivanka-p0-prospective-allprojects-20261122/p0-sameversion-latency-phases-20261123T0322Z.json, SHA256 **1414846f0589e82014d82437aff91a1e3d73ee4cf0b3aa9a410c433ce559194b**. One supported sample generated 14 Ivanka-native contigs in about **0.2 seconds** versus 2 native IVA contigs; its overall Ivanka time **64.195s** vs IVA **39.920s**. This establishes downstream remap/stitch as the likely optimization target, **not causal proof that particular contigs can safely be removed**. All 33 were chosen for completion by ascending original compressed paired FASTQ size and are not representative of 198; no arbitrary contig cap or reference-guided selector is authorized. Focused parallel, source-only Rust investigation must preserve sample-derived seeds and independently supported ≥15%-abundance HIV/HCV haplotypes and produce negative tests before any source modification or prospective rerun. A separate Antonina source-analysis agent was started; the live IVA runner stays undisturbed.

## Founder priority and other resource constraints

P0 physical checks first; **P1 synthetic 464-case acceptance only after physical P0**, PX exactly ten extra **NONQUALIFYING** tool adapters in parallel only when disk conditions permit, P2 physical exact-coverage/depth/clips/concordance diagnostics after core, and P3 original rival failure repair LAST.

PX ten source-only adapters exist but no valid new OCI images or genuine MiCall pilots. A full common MiCall experimental image builder exceeded the strict 8GiB storage footprint; eight abandoned external Buildah work containers were isolated and removed, recovering 8.744GB, with exact receipts. Hard PX policy remains **≥32GiB free, ≤8GiB total added exploration storage, at most one worker**, 2400s and 4GB measured. Do not retry that inherently oversized build until source-attested smaller build design/hard quota.

The original seven frozen OCI manifest still has SHA256 **9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f**, with the historical 4634 terminal seven-arm observations immutable.
