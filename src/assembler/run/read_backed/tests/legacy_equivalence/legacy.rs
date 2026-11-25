use super::{Hits, Reads, K};
use std::collections::{HashMap, HashSet};

/// Original union-of-loci pair rule; strand annotations are deliberately ignored.
pub(crate) fn legacy(
    contigs: &[Vec<u8>],
    reads: &Reads,
    hits: &Hits,
) -> (Vec<Vec<u32>>, Vec<usize>) {
    let mut depth = contigs
        .iter()
        .map(|s| vec![0; s.len().saturating_sub(K - 1)])
        .collect::<Vec<_>>();
    let mut pairs = vec![0usize; contigs.len()];
    for oriented in reads.seqs.chunks_exact(4).take(80_000) {
        let mut matched = HashMap::<usize, HashSet<usize>>::new();
        for read in [&oriented[0], &oriented[2]] {
            if read.len() < K {
                continue;
            }
            for pos in (0..=read.len() - K).step_by(2) {
                if let Some(locations) = hits.get(&read[pos..pos + K]) {
                    for &(candidate, locus, _) in locations {
                        matched.entry(candidate).or_default().insert(locus);
                    }
                }
            }
        }
        for (candidate, loci) in matched {
            if loci.len() < 2 {
                continue;
            }
            pairs[candidate] += 1;
            for locus in loci {
                depth[candidate][locus] += 1;
            }
        }
    }
    (depth, pairs)
}
