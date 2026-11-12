use super::{index::Hits, Reads, K};
use std::collections::{HashMap, HashSet};

pub(super) struct Statistics {
    pub(super) depth: Vec<Vec<u32>>,
    pub(super) pairs: Vec<usize>,
    pub(super) coverage: Vec<usize>,
}

/// Count each original read pair once per contig, irrespective of hit count.
pub(super) fn count(contigs: &[Vec<u8>], reads: &Reads, hits: &Hits) -> Statistics {
    let mut depth = contigs
        .iter()
        .map(|seq| vec![0; seq.len().saturating_sub(K - 1)])
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
                    for &(candidate, locus) in locations {
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
    let coverage = depth
        .iter()
        .map(|d| d.iter().filter(|&&v| v >= 3).count())
        .collect();
    Statistics {
        depth,
        pairs,
        coverage,
    }
}
