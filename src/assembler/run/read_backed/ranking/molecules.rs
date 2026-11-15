use super::{Hits, Reads, K};
use std::collections::{HashMap, HashSet};

pub(crate) type PairLinks = HashMap<(usize, usize), usize>;

/// Ambiguous placements never establish mate-to-component linkage.
pub(super) fn anchor(read: &[u8], hits: &Hits) -> Option<usize> {
    let mut positions = HashMap::<usize, HashSet<usize>>::new();
    if read.len() < K {
        return None;
    }
    for pos in (0..=read.len() - K).step_by(2) {
        if let Some(loci) = hits.get(&read[pos..pos + K]) {
            for &(candidate, locus) in loci {
                positions.entry(candidate).or_default().insert(locus);
            }
        }
    }
    let mut assigned = None;
    for (i, places) in positions {
        if places.len() >= 2 && assigned.replace(i).is_some() {
            return None;
        }
    }
    assigned
}

/// Record observed paired mate anchors; PCR copies need not be independent molecules.
pub(crate) fn links(reads: &Reads, hits: &Hits) -> PairLinks {
    let mut support = PairLinks::new();
    for mates in reads.seqs.chunks_exact(4).take(80_000) {
        if let (Some(a), Some(b)) = (anchor(&mates[0], hits), anchor(&mates[2], hits)) {
            *support.entry((a, b)).or_default() += 1;
        }
    }
    support
}
