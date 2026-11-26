use super::{Hits, K};
use std::collections::{HashMap, HashSet};

/// Contig loci anchored by the sampled 31-mers of both mates.
pub(super) fn loci(mates: [&[u8]; 2], hits: &Hits) -> HashMap<usize, HashSet<usize>> {
    let mut matched = HashMap::<usize, HashSet<usize>>::new();
    for read in mates {
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
    matched
}
