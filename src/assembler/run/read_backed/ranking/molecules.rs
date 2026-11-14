use super::{Hits, Reads, K};
use std::collections::{HashMap, HashSet};

pub(crate) type PairLinks = HashMap<(usize, usize), usize>;

/// A mate anchors only after two different read-supported k-mer loci.
fn anchors(read: &[u8], hits: &Hits) -> HashSet<usize> {
    let mut positions = HashMap::<usize, HashSet<usize>>::new();
    if read.len() < K {
        return HashSet::new();
    }
    for pos in (0..=read.len() - K).step_by(2) {
        if let Some(loci) = hits.get(&read[pos..pos + K]) {
            for &(candidate, locus) in loci {
                positions.entry(candidate).or_default().insert(locus);
            }
        }
    }
    positions
        .into_iter()
        .filter_map(|(i, places)| (places.len() >= 2).then_some(i))
        .collect()
}

/// Record observed paired mate anchors; PCR copies need not be independent molecules.
pub(crate) fn links(reads: &Reads, hits: &Hits) -> PairLinks {
    let mut support = PairLinks::new();
    for mates in reads.seqs.chunks_exact(4).take(80_000) {
        let left = anchors(&mates[0], hits);
        let right = anchors(&mates[2], hits);
        for &a in &left {
            for &b in &right {
                *support.entry((a, b)).or_default() += 1;
            }
        }
    }
    support
}
