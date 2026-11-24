use super::{matched, Hits, Reads, Statistics, K};
use std::collections::HashMap;

/// Count each distinct observed read-pair sequence once per contig.
///
/// Byte-identical observations are collapsed without claiming that they came
/// from the same source molecule (UMIs would be required for that claim).
/// Breadth and depth therefore reflect the diversity of observed fragments;
/// the raw observation count is retained only as an exact tie-break, so a
/// genuinely abundant population still benefits from its extra observations.
/// This requires no reference, family label, or abundance threshold.
pub(crate) fn count(contigs: &[Vec<u8>], reads: &Reads, hits: &Hits) -> Statistics {
    let mut depth = contigs
        .iter()
        .map(|seq| vec![0; seq.len().saturating_sub(K - 1)])
        .collect::<Vec<_>>();
    let mut pairs = vec![0; contigs.len()];
    let mut raw_pairs = vec![0; contigs.len()];

    // One entry per distinct observed pair sequence; value is its frequency.
    let mut copies = HashMap::<(&[u8], &[u8]), usize>::new();
    for oriented in reads.seqs.chunks_exact(4).take(80_000) {
        *copies.entry((&oriented[0], &oriented[2])).or_insert(0) += 1;
    }

    let mut pair_masks = Vec::new();
    for oriented in reads.seqs.chunks_exact(4).take(80_000) {
        // `remove` yields the copy count once and skips later copies.
        let Some(duplicates) = copies.remove(&(&oriented[0], &oriented[2])) else {
            continue;
        };
        let matched = matched::loci([&oriented[0], &oriented[2]], hits);
        let mut mask = 0u16;
        for (candidate, loci) in matched {
            if loci.len() < 2 {
                continue;
            }
            mask |= 1 << candidate;
            pairs[candidate] += 1;
            raw_pairs[candidate] += duplicates;
            for locus in loci {
                depth[candidate][locus] += 1;
            }
        }
        pair_masks.push(mask);
    }
    let coverage = depth
        .iter()
        .map(|d| d.iter().filter(|&&v| v >= 3).count())
        .collect();
    Statistics {
        depth,
        pairs,
        raw_pairs,
        coverage,
        pair_masks,
    }
}
