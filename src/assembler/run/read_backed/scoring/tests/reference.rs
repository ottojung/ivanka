use super::{Hits, Reads, K};
use std::collections::{HashMap, HashSet};

type Depth = Vec<Vec<u32>>;
type Spans = Vec<Vec<(usize, usize)>>;
pub(super) type Stats = (Depth, Vec<usize>, Vec<usize>, Vec<u16>, Spans);

// Original pairwise HashMap/HashSet formulation, reproduced verbatim, with
// the PR458 per-pair span capture added for the integration differential.
pub(super) fn count(contigs: &[Vec<u8>], reads: &Reads, hits: &Hits) -> Stats {
    let mut depth: Vec<Vec<u32>> = contigs
        .iter()
        .map(|seq| vec![0; seq.len().saturating_sub(K - 1)])
        .collect();
    let mut pairs = vec![0usize; contigs.len()];
    let mut spans = vec![Vec::new(); contigs.len()];
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
            spans[candidate].push((
                *loci.iter().min().expect("nonempty supported loci"),
                *loci.iter().max().expect("nonempty supported loci"),
            ));
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
    (depth, pairs, coverage, pair_masks, spans)
}
