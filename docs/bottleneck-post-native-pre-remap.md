# Bottleneck: post-native pre-remap stage (referenceless stitcher)

## Evidence

Authentic sample `73109AMIDI-MidHCV_S87` MiCall log:
- `Running de novo assembly` at 23:01:07
- Ivanka native Rust `Assembled 16 contigs in 9.563s` by 23:01:16.725
- `Running remap` not until 23:05:01.362 → **~224.6s gap**
- IVA internal time on same sample: 233.9s

## Root cause (MiCall source: `/workspace/qai-repo/repos/MiCall/micall/drivers/sample.py:run_denovo`)

After native assembly completes, `run_denovo` performs these steps before `Running remap`:

1. `csv_to_fasta` (merged_contigs_csv → merged_contigs_fasta)
2. `concatenate_files` (unstitched + merged → combined)
3. `fasta_to_csv` (combined → unstitched_contigs_csv)
4. **`run_referenceless_stitcher()`** — calls `build_read_index` (reads all FASTQs) then `referenceless_contig_stitcher` (combinatorial path search)
5. `fasta_to_csv` (stitched → stitched_contigs_csv)

The referenceless stitcher is the dominant cost. It runs:
- `stitch_consensus_overlaps`: O(n²) per cycle × up to N cycles, where n = number of combined contigs (typically 16+16=32)
- `o2_loop`: O(n³) greedy pair-merge until no more combinations
- Each `try_combine_contigs` call performs overlap computation + read-index validation (`check_merged_sequence_support`)

## Optimization assessment

The stitcher already caches overlaps (`get_overlap_cache`) and limits alternatives (`intrapolate_number_of_alternatives`). The combinatorial search is intrinsic to the algorithm. Safe output-preserving optimizations (e.g., reducing `MAX_ALTERNATIVES` or adding early termination) risk changing stitched contig output and downstream scores.

## Conclusion

No defensible in-container optimization identified without risk of altering stitched output / minority haplotypes. The bottleneck is the referenceless stitcher's combinatorial path search, which is already cached and bounded. Recommend profiling with per-stage timing instrumentation before attempting algorithmic changes.
