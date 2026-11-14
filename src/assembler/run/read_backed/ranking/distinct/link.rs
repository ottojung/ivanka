use super::PairLinks;

/// Accept a separate fragment only with genuine paired-mate observations.
pub(super) fn mate_linked(i: usize, picked: &[usize], links: &PairLinks) -> bool {
    if links.get(&(i, i)).copied().unwrap_or(0) >= 3 {
        return true;
    }
    picked.iter().any(|&j| {
        links.get(&(i, j)).copied().unwrap_or(0) + links.get(&(j, i)).copied().unwrap_or(0) >= 3
    })
}
