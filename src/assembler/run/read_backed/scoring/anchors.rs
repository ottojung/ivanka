use super::{Hits, K};
use std::collections::{HashMap, HashSet};

/// Loci and strand observations for one original mate on each candidate.
/// The booleans record forward-strand and reverse-strand matches respectively.
pub(crate) type Mate = HashMap<usize, (HashSet<usize>, bool, bool)>;

/// Index hits carry their strand, so no reference or truth input is consulted.
pub(crate) fn anchors(hits: &Hits, read: &[u8], found: &mut Mate) {
    if read.len() < K {
        return;
    }
    for pos in (0..=read.len() - K).step_by(2) {
        if let Some(locations) = hits.get(&read[pos..pos + K]) {
            for &(candidate, locus, forward) in locations {
                let mate = found.entry(candidate).or_default();
                mate.0.insert(locus);
                if forward {
                    mate.1 = true;
                } else {
                    mate.2 = true;
                }
            }
        }
    }
}

pub(crate) fn loci(a: &Mate, b: &Mate, candidate: usize) -> HashSet<usize> {
    let mut found = HashSet::new();
    for mate in [a, b] {
        if let Some(evidence) = mate.get(&candidate) {
            found.extend(evidence.0.iter().copied());
        }
    }
    found
}

/// A fragment links a candidate when both mates anchor distinct loci in opposite directions.
pub(crate) fn linked(a: &Mate, b: &Mate, candidate: usize) -> bool {
    let (Some(x), Some(y)) = (a.get(&candidate), b.get(&candidate)) else {
        return false;
    };
    let span = x.0.iter().any(|p| y.0.iter().any(|q| p != q));
    span && ((x.1 && y.2) || (x.2 && y.1))
}
