use super::byte_index::ByteHits;
use super::{Reads, K};
use std::collections::{HashMap, HashSet};

pub(super) type Stats = (Vec<Vec<u32>>, Vec<usize>, Vec<usize>, Vec<u16>);

// Original pairwise HashMap/HashSet formulation, reproduced verbatim.
pub(super) fn count(contigs: &[Vec<u8>], reads: &Reads, hits: &ByteHits) -> Stats {
    let mut depth = contigs
        .iter()
        .map(|seq| vec![0u32; seq.len().saturating_sub(K - 1)])
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
    (depth, pairs, coverage, pair_masks)
}
