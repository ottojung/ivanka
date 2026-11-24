mod statistics;
use super::{index::Hits, Reads, K};
pub(super) use statistics::Statistics;
use std::collections::{HashMap, HashSet};

/// Count each original read pair once per contig, irrespective of hit count.
pub(super) fn count(contigs: &[Vec<u8>], reads: &Reads, hits: &Hits) -> Statistics {
    let mut depth = contigs
        .iter()
        .map(|seq| vec![0; seq.len().saturating_sub(K - 1)])
        .collect::<Vec<_>>();
    let mut pairs = vec![0usize; contigs.len()];
    let mut pair_masks = Vec::new();
    for oriented in reads.seqs.chunks_exact(4).take(80_000) {
        let mut matched = HashMap::<usize, HashSet<usize>>::new();
        for read in [&oriented[0], &oriented[2]] {
            if read.len() < K {
                continue;
            }
            for pos in (0..=read.len() - K).step_by(2) {
                if let Some(locations) = hits.get(&read[pos..pos + K]) {
                    for &(candidate, locus) in locations {
                        matched.entry(candidate).or_default().insert(locus);
                    }
                }
            }
        }
        let mut mask = 0u16;
        for (candidate, loci) in matched {
            if loci.len() < 2 {
                continue;
            }
            mask |= 1 << candidate;
            pairs[candidate] += 1;
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
        coverage,
        pair_masks,
    }
}
