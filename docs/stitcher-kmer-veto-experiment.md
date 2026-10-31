# Experimental: canonical k-mer preservation in referenceless stitching

This isolated experiment modifies the **candidate** MiCall stitcher, not cached IVA controls.

A candidate overlap/path merge is rejected if it eliminates any canonical
31-mer from the contigs consumed by that merge; short input contigs must
survive as an exact substring in at least one orientation. This may retain
biologically meaningful minority alleles and avoid consensus-chimera
damage, at the potential cost of more remapping references.

Source patcher: `benchmarks/patch_micall_stitcher_kmer_veto.py` (fails
closed if the pinned MiCall source changes). `benchmarks/Containerfile.stitcher-kmer-veto`
derives from the existing pinned Ivanka/MiCall candidate image. Both
candidate sources and complete image IDs must be recorded.

This is **not validated**, and is NOT the desired unconditionally capped
contig selection. Only build the isolated image and compare genuine
cached-IVA full MiCall outputs on relevant HCV/V3 samples first. Check
per-sample score, full arm time, raw-to-stitched read-supported k-mer
retention and potential phase/chimeric effects before proposing a merge.
Do not run a 198-sample qualification or change gates for this experiment.
