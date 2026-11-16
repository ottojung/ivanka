use super::PairLinks;

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
