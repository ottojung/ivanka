mod scan;
mod spans;
mod statistics;
pub(super) use super::{index::Hits, Reads, K};
pub(super) use statistics::Statistics;
pub(super) use std::collections::{HashMap, HashSet};

/// Count each original read pair once per contig, irrespective of hit count.
pub(super) fn count(contigs: &[Vec<u8>], reads: &Reads, hits: &Hits) -> Statistics {
    let mut depth = contigs
        .iter()
        .map(|seq| vec![0; seq.len().saturating_sub(K - 1)])
        .collect::<Vec<_>>();
    let (mut pairs, mut spans) = (vec![0usize; contigs.len()], vec![Vec::new(); contigs.len()]);
    let mut pair_masks = Vec::new();
    let mut exclusive_masks = Vec::new();
    for oriented in reads.seqs.chunks_exact(4).take(80_000) {
        let (matched, exclusive) = scan::pair_loci(hits, &oriented[0], &oriented[2]);
        let mut mask = 0u16;
        for (candidate, loci) in matched {
            if loci.len() < 2 {
                continue;
            }
            mask |= 1 << candidate;
            pairs[candidate] += 1;
            spans[candidate].push(spans::extremes(&loci));
            for locus in loci {
                depth[candidate][locus] += 1;
            }
        }
        let mut exclusive_mask = 0u16;
        for (candidate, loci) in exclusive {
            if loci.len() >= 2 {
                exclusive_mask |= 1 << candidate;
            }
        }
        pair_masks.push(mask);
        exclusive_masks.push(exclusive_mask);
    }
    let coverage = spans::coverage(&depth);
    Statistics {
        depth,
        pairs,
        coverage,
        pair_masks,
        exclusive_masks,
        spans,
    }
}
