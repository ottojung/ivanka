use super::{anchor, Hits, PairLinks, Reads};

/// Mate links are observations, not distinct PCR-origin molecules.
pub(crate) fn links(reads: &Reads, hits: &Hits) -> PairLinks {
    let mut support = PairLinks::new();
    for mates in reads.seqs.chunks_exact(4).take(80_000) {
        if let (Some(a), Some(b)) = (anchor(&mates[0], hits), anchor(&mates[2], hits)) {
            *support.entry((a, b)).or_default() += 1;
        }
    }
    support
}
