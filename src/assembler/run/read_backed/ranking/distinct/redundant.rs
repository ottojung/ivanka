use super::{PairLinks, Statistics};

/// A second nearly full-length path backed by the same pairs is not independent.
/// This is a conservative diagnostic of shared fragments, not proof of phase.
pub(super) fn competing(a: usize, b: usize, lengths: &[Vec<u8>], links: &PairLinks) -> bool {
    let shortest = lengths[a].len().min(lengths[b].len()) as u128;
    let longest = lengths[a].len().max(lengths[b].len()) as u128;
    if shortest * 10 < longest * 9 {
        return false;
    }
    let own = links.get(&(a, a)).copied().unwrap_or(0) as u128;
    let ab = links.get(&(a, b)).copied().unwrap_or(0) as u128;
    let ba = links.get(&(b, a)).copied().unwrap_or(0) as u128;
    // Both cross directions count the same original fragment at most twice.
    own >= 3 && (ab + ba) * 5 >= own * 8
}

/// Do not let very sparse alternatives displace a similarly sized major path.
/// This is an abundance heuristic, not a declaration that the allele is absent.
pub(super) fn weak_alternative(
    i: usize,
    j: usize,
    contigs: &[Vec<u8>],
    stats: &Statistics,
) -> bool {
    let shorter = contigs[i].len().min(contigs[j].len()) as u128;
    let longer = contigs[i].len().max(contigs[j].len()) as u128;
    let representative = stats.pairs[j] as u128;
    shorter * 10 >= longer * 9
        && representative >= 30
        && (stats.pairs[i] as u128) * 5 < representative
        && stats.coverage[i] <= stats.coverage[j]
}

/// Both competing original molecules and sparse alternative support matter.
pub(crate) fn not_independent(
    i: usize,
    j: usize,
    contigs: &[Vec<u8>],
    links: &PairLinks,
    stats: &Statistics,
) -> bool {
    competing(i, j, contigs, links) || weak_alternative(i, j, contigs, stats)
}
